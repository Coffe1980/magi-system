"""
MAGIVoz — Sistema de Voz Bidirecional do MAGI
═══════════════════════════════════════════════
Ativa por palavra-chave → ouve → transcreve → envia ao MAGI → responde por voz (Edge TTS)

Dependências:
    pip install speechrecognition pyaudio edge-tts pygame colorama python-dotenv

Uso standalone:
    python magi_voz.py

Uso integrado (dentro do MagiSystem):
    from magi_voz import MAGIVoz
    voz = MAGIVoz(magi)
    voz.iniciar()
    voz.parar()
"""

import os
import time
import threading
import queue
import tempfile
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from colorama import Fore, Style, init as colorama_init

colorama_init(autoreset=True)
load_dotenv(Path(__file__).parent / "Projeto2.env")

# ── Constantes ────────────────────────────────────────────────────────────────
PALAVRA_ATIVACAO     = ["magi", "hey magi", "nerv", "hey nerv", "mag"]
GOOGLE_SPEECH_LANG   = "pt-BR"
EDGE_VOICE           = "pt-BR-AntonioNeural"  # Masculino natural. Alternativa: pt-BR-FranciscaNeural
SILENCIO_TIMEOUT     = 5
FRASE_MAX_SEGUNDOS   = 15
ENERGIA_MINIMA       = 50       # bem baixo para microfones fracos (padrão era 300)

def _log(nivel: str, msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    cores = {"INFO": Fore.CYAN, "WARN": Fore.YELLOW, "ERROR": Fore.RED, "OK": Fore.GREEN}
    cor = cores.get(nivel, Fore.WHITE)
    print(f"  {Fore.BLUE}[{ts}] {cor}[VOZ·{nivel}] {Fore.WHITE}{msg}")


class MAGIVoz:
    """Sistema de voz bidirecional do MAGI com Edge TTS (Microsoft, gratuito, voz natural)."""

    def __init__(self, magi=None, history=None):
        self.magi        = magi
        self._history    = history  # ConversationHistory compartilhado com a UI (pode ser None)
        self._ativo      = False
        self._mutado     = False   # microfone mutado
        self._thread     = None
        self._fila_tts   = queue.Queue()
        self._thread_tts = None
        self._sr         = None
        self._pygame     = None
        self._verificar_dependencias()

    def _verificar_dependencias(self):
        erros = []
        try:
            import speech_recognition as sr
            self._sr = sr
        except ImportError:
            erros.append("speech_recognition  →  pip install speechrecognition")
        try:
            import pyaudio  # noqa
        except ImportError:
            erros.append("pyaudio             →  pip install pyaudio")
        try:
            import edge_tts  # noqa
            self._edge_ok = True
        except ImportError:
            erros.append("edge-tts            →  pip install edge-tts")
            self._edge_ok = False
        try:
            import pygame
            self._pygame = pygame
            pygame.mixer.init()
        except ImportError:
            erros.append("pygame              →  pip install pygame")

        if erros:
            print(f"\n{Fore.RED}  [MAGIVoz] Dependências faltando:")
            for e in erros:
                print(f"  {Fore.YELLOW}  · {e}")
            print(f"{Fore.WHITE}  Instale tudo: pip install speechrecognition pyaudio edge-tts pygame\n")

    # ── API pública ───────────────────────────────────────────────────────────
    def iniciar(self):
        if self._ativo:
            _log("WARN", "Sistema de voz já está ativo.")
            return
        if not self._sr or not self._edge_ok:
            _log("ERROR", "Dependências não satisfeitas. Voz não iniciada.")
            return

        self._ativo = True

        self._thread_tts = threading.Thread(target=self._loop_tts, daemon=True)
        self._thread_tts.start()

        self._thread = threading.Thread(target=self._loop_escuta, daemon=True)
        self._thread.start()

        _log("OK", f"Sistema de voz ativo. Palavras de ativação: {PALAVRA_ATIVACAO}")
        self.falar("MAGI online. Aguardando ativação.")

    def parar(self):
        self._ativo = False
        _log("INFO", "Sistema de voz encerrado.")

    def mutar(self):
        """Muta o microfone — MAGI para de ouvir."""
        self._mutado = True
        self._fila_tts.queue.clear()
        try:
            if self._pygame:
                self._pygame.mixer.music.stop()
        except Exception:
            pass
        _log("WARN", "Microfone MUTADO.")

    def desmutar(self):
        """Desmuta o microfone — MAGI volta a ouvir."""
        self._mutado = False
        _log("OK", "Microfone ATIVO.")
        self.falar("Microfone reativado.")

    def falar(self, texto: str):
        if texto:
            self._fila_tts.put(texto)

    # ── Loop TTS (Edge TTS — Microsoft Neural) ───────────────────────────────
    def _loop_tts(self):
        import asyncio
        import edge_tts

        async def _sintetizar(texto: str, caminho: str):
            comunicar = edge_tts.Communicate(texto, EDGE_VOICE)
            await comunicar.save(caminho)

        while self._ativo:
            try:
                texto = self._fila_tts.get(timeout=1)
            except queue.Empty:
                continue

            tmp_path = None
            try:
                _log("INFO", f"Sintetizando: {texto[:60]}...")

                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp_path = tmp.name

                asyncio.run(_sintetizar(texto, tmp_path))
                self._reproduzir(tmp_path)

            except Exception as e:
                _log("ERROR", f"Erro TTS: {type(e).__name__}: {e}")
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

    def _reproduzir(self, caminho_mp3: str):
        try:
            pg = self._pygame
            pg.mixer.music.load(caminho_mp3)
            pg.mixer.music.play()
            while pg.mixer.music.get_busy():
                time.sleep(0.1)
        except Exception as e:
            _log("ERROR", f"Erro ao reproduzir áudio: {e}")

    # ── Loop STT ──────────────────────────────────────────────────────────────
    def _loop_escuta(self):
        sr = self._sr
        recognizer = sr.Recognizer()
        recognizer.energy_threshold         = ENERGIA_MINIMA
        recognizer.dynamic_energy_threshold = True
        recognizer.dynamic_energy_adjustment_damping = 0.10  # adapta mais rápido
        recognizer.dynamic_energy_ratio     = 1.2            # menos exigente
        recognizer.pause_threshold          = 1.5            # mais tempo para pausas
        recognizer.non_speaking_duration    = 0.4            # detecta fala mais cedo

        _log("INFO", "Calibrando microfone...")
        try:
            with sr.Microphone() as fonte:
                recognizer.adjust_for_ambient_noise(fonte, duration=3)
                # Força threshold baixo após calibração para microfones fracos
                if recognizer.energy_threshold > 150:
                    recognizer.energy_threshold = 150
                    _log("WARN", "Threshold ajustado para 150 (microfone fraco detectado)")
            _log("OK", f"Microfone calibrado. Threshold: {recognizer.energy_threshold:.0f}")
        except Exception as e:
            _log("ERROR", f"Microfone não encontrado: {e}")
            return

        _log("OK", "Escutando... Diga 'MAGI' para ativar.")

        while self._ativo:
            try:
                # Se mutado, não escuta
                if self._mutado:
                    time.sleep(0.3)
                    continue

                with sr.Microphone() as fonte:
                    try:
                        audio = recognizer.listen(fonte, timeout=3, phrase_time_limit=4)
                    except sr.WaitTimeoutError:
                        continue

                texto = self._transcrever(recognizer, audio)
                if not texto:
                    continue

                _log("INFO", f"Escutei: '{texto}'")
                texto_lower = texto.lower().strip()
                ativado = any(p in texto_lower for p in PALAVRA_ATIVACAO)

                if ativado:
                    comando_inline = texto_lower
                    for p in PALAVRA_ATIVACAO:
                        comando_inline = comando_inline.replace(p, "").strip()

                    if len(comando_inline) > 3:
                        # Roda em thread separada para não travar o loop de escuta
                        threading.Thread(
                            target=self._processar_comando,
                            args=(comando_inline,),
                            daemon=True
                        ).start()
                    else:
                        print(f"\n{Fore.RED}  [MAGI VOZ] {Fore.YELLOW}Ativado! Aguardando comando...{Style.RESET_ALL}")
                        self.falar("Sim, pode falar.")
                        # Captura e processa em thread separada
                        threading.Thread(
                            target=self._capturar_e_processar_comando,
                            args=(recognizer,),
                            daemon=True
                        ).start()

            except Exception as e:
                _log("ERROR", f"Erro no loop de escuta: {e}")
                time.sleep(0.5)

    def _capturar_e_processar_comando(self, recognizer):
        sr = self._sr
        try:
            with sr.Microphone() as fonte:
                print(f"  {Fore.CYAN}[Ouvindo comando...]")
                audio = recognizer.listen(
                    fonte,
                    timeout=SILENCIO_TIMEOUT,
                    phrase_time_limit=FRASE_MAX_SEGUNDOS,
                )
            texto = self._transcrever(recognizer, audio)
            if texto:
                self._processar_comando(texto)
            else:
                self.falar("Não entendi. Pode repetir?")
        except sr.WaitTimeoutError:
            self.falar("Não ouvi nada. Diga MAGI quando quiser falar.")
        except Exception as e:
            _log("ERROR", f"Erro ao capturar comando: {e}")

    def _transcrever(self, recognizer, audio) -> str:
        sr = self._sr
        try:
            return recognizer.recognize_google(audio, language=GOOGLE_SPEECH_LANG).strip()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            _log("ERROR", f"Google Speech API indisponível: {e}")
            return ""

    def _limpar_para_voz(self, texto: str) -> str:
        """Remove tudo que não deve ser falado — ruído de terminal, fontes, markdown."""
        import re
        # Remove blocos FONTES: [1]...
        texto = re.sub(r'FONTES?:\s*\[.*', '', texto, flags=re.DOTALL | re.IGNORECASE)
        # Remove referências inline [1], [2], [3]
        texto = re.sub(r'\[\d+\]', '', texto)
        # Remove prefixos de núcleos [CASPER-3], [MELCHIOR-1] etc
        texto = re.sub(r'\[(?:CASPER-3|MELCHIOR-1|BALTHASAR-2|ADAM-0)[^\]]*\]', '', texto)
        # Remove linha "→ Analisando..."
        texto = re.sub(r'→\s*Analisando[^\n]*\n?', '', texto)
        # Remove separadores ─────
        texto = re.sub(r'─+', '', texto)
        # Remove markdown: **negrito**, *itálico*, `código`, # títulos
        texto = re.sub(r'\*\*(.+?)\*\*', r'\1', texto)
        texto = re.sub(r'\*(.+?)\*',     r'\1', texto)
        texto = re.sub(r'`[^`]*`',       '',    texto)
        texto = re.sub(r'^#{1,6}\s+',    '',    texto, flags=re.MULTILINE)
        # Remove URLs
        texto = re.sub(r'https?://\S+', '', texto)
        # Remove emojis e símbolos especiais comuns no terminal
        texto = re.sub(r'[◈⚡🔬🛡️🖥◉●▶▸✓✗⚠]', '', texto)
        # Colapsa espaços e linhas extras
        texto = re.sub(r'\n{3,}', '\n\n', texto)
        texto = re.sub(r'  +', ' ', texto)
        return texto.strip()

    # ── Processamento ─────────────────────────────────────────────────────────
    def _processar_comando(self, texto: str):
        print(f"\n{Fore.RED}NERV (VOZ) >> {Fore.WHITE}{texto}{Style.RESET_ALL}")

        if not self.magi:
            self.falar(f"Você disse: {texto}")
            return

        # Registra o turno do usuário no histórico compartilhado
        if self._history:
            self._history.record_user(texto)

        texto_lower = texto.lower()

        # ── Comandos especiais por voz ────────────────────────
        if any(p in texto_lower for p in ["silêncio", "calar", "para de falar", "mudo", "parar", "para", "chega"]):
            self._fila_tts.queue.clear()
            try:
                if self._pygame:
                    self._pygame.mixer.music.stop()
            except Exception:
                pass
            _log("INFO", "Fala interrompida por comando.")
            return

        if any(p in texto_lower for p in ["encerrar voz", "desligar voz", "voz off"]):
            self.falar("Sistema de voz encerrado. Até logo.")
            time.sleep(2)
            self.parar()
            return

        # ── Comando: olha minha tela ──────────────────────────
        palavras_tela = ["olha minha tela", "veja minha tela", "o que tem na tela",
                         "analisa a tela", "captura a tela", "o que está na tela"]
        if any(p in texto_lower for p in palavras_tela):
            self.falar("Capturando sua tela, um momento.")
            resposta = self._capturar_tela()
            limpa = self._limpar_para_voz(resposta)
            self.falar(limpa[:600])
            return

        # ── Comandos de código: não lê o resultado em voz ────
        cmds_codigo = ["codigo ", "revisar ", "testar ", "testes ", "visual "]
        if any(texto_lower.startswith(c) for c in cmds_codigo):
            self.falar("Processando. Confira o resultado no terminal.")
            threading.Thread(
                target=self.magi.processar,
                args=(texto,),
                daemon=True
            ).start()
            return

        # ── Comando normal: processa e fala a resposta ────────
        resposta = self._capturar_resposta_magi(texto)
        if resposta:
            limpa = self._limpar_para_voz(resposta)
            # Limita a 500 chars para não ficar falando eternamente
            if len(limpa) > 500:
                # Corta na última frase completa antes de 500 chars
                import re as _re
                trecho = limpa[:500]
                ultimo_ponto = max(
                    trecho.rfind('. '),
                    trecho.rfind('! '),
                    trecho.rfind('? '),
                )
                if ultimo_ponto > 200:
                    trecho = trecho[:ultimo_ponto + 1]
                trecho += " Confira o terminal para a resposta completa."
                self.falar(trecho)
            else:
                self.falar(limpa)
        else:
            self.falar("Não obtive resposta. Confira o terminal.")

    def _capturar_resposta_magi(self, query: str) -> str:
        """
        Para voz: chama CASPER-3 diretamente sem passar por MELCHIOR/BALTHASAR.
        Mais rápido, resposta mais natural para conversa por voz.
        Injeta histórico compartilhado com a UI quando disponível.
        """
        import re as _re

        if not self.magi:
            return ""

        try:
            # ── Monta contexto de histórico se disponível ─────────────────────
            ctx_block = ""
            if self._history:
                # Detecta se é pedido de continuidade antes de perguntar ao modelo
                if self._history.needs_context(query):
                    ctx_block = self._history.context_block(n_turns=5)
                    _log("INFO", f"Contexto de {min(5, len(self._history._turns))} turnos injetado no prompt de voz")

            # ── System prompt para voz (conciso + contexto) ───────────────────
            system_voz = (
                "Você é CASPER-3, respondendo por voz. "
                "Seja DIRETO e CONCISO — máximo 3 frases curtas. "
                "Sem markdown, sem bullets, sem listas numeradas. "
                "Fale como se estivesse respondendo verbalmente a uma pergunta."
            )
            if ctx_block:
                system_voz += (
                    "\n\nIMPORTANTE: O histórico abaixo contém a conversa atual. "
                    "Use-o para dar continuidade, repetir ou elaborar quando pedido."
                )

            # ── Prompt final: histórico + query ──────────────────────────────
            prompt_final = f"{ctx_block}\n\nUsuário agora diz: {query}" if ctx_block else query

            resposta = None

            # Tenta DeepSeek primeiro (mente do CASPER)
            if hasattr(self.magi, 'deepseek') and self.magi.deepseek:
                from MagiSystem import DEEPSEEK_MODELO_PADRAO
                resposta = self.magi._chamar_deepseek(
                    DEEPSEEK_MODELO_PADRAO, system_voz, prompt_final
                )

            # Fallback: local
            if not resposta and hasattr(self.magi, 'local') and self.magi.local:
                resposta = self.magi._chamar_local(system_voz, prompt_final)

            # Fallback final: processar() completo + extrai do histórico
            if not resposta:
                tamanho_antes = len(self.magi.historico)
                self.magi.processar(query)
                for _ in range(80):
                    if len(self.magi.historico) > tamanho_antes:
                        break
                    time.sleep(0.1)
                if len(self.magi.historico) > tamanho_antes:
                    ultimo = list(self.magi.historico)[-1]
                    for sep in [" | CASPER: ", "| CASPER:", "CASPER:"]:
                        if sep in ultimo:
                            resposta = ultimo.split(sep, 1)[-1].strip()
                            break
                    if not resposta and "|" in ultimo:
                        resposta = ultimo.rsplit("|", 1)[-1].strip()

            # Remove thinking tags do DeepSeek R1
            if resposta:
                resposta = _re.sub(r'<think>.*?</think>', '', resposta, flags=_re.DOTALL).strip()

            # ── Registra a resposta no histórico compartilhado ────────────────
            if resposta and self._history:
                self._history.record_ai(resposta)

            return resposta or ""

        except Exception as e:
            _log("ERROR", f"Erro ao processar comando: {e}")
            return ""

    def _capturar_tela(self) -> str:
        """Captura a tela e envia para o Gemini Vision analisar."""
        try:
            import mss
            import base64
            import tempfile

            # Captura a tela
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # tela principal
                screenshot = sct.grab(monitor)
                # Salva como PNG temporário
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=tmp_path)

            _log("INFO", "Tela capturada, enviando para análise...")

            # Envia para o Gemini Vision via MagiSystem
            if hasattr(self.magi, '_chamar_google_vision'):
                resposta = self.magi._chamar_google_vision(tmp_path)
            else:
                # Fallback: usa PIL + base64 + Gemini direto
                with open(tmp_path, "rb") as f:
                    img_bytes = f.read()
                img_b64 = base64.b64encode(img_bytes).decode()
                from google import genai
                from google.genai import types as gt
                client = genai.Client(api_key=__import__("os").getenv("GOOGLE_API_KEY"))
                resp = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        gt.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                        "Descreva o que está na tela de forma resumida e objetiva. "
                        "Se houver código, erro ou texto importante, destaque."
                    ]
                )
                resposta = resp.text.strip()

            try:
                __import__("os").unlink(tmp_path)
            except Exception:
                pass

            return resposta or "Não consegui analisar a tela."

        except ImportError:
            return "Instale o mss: py -3.11 -m pip install mss"
        except Exception as e:
            _log("ERROR", f"Erro ao capturar tela: {e}")
            return f"Erro ao capturar tela: {e}"


def integrar_voz_ao_magi(magi, history=None) -> "MAGIVoz":
    """
    Integra o sistema de voz ao MAGI.
    Passe o ConversationHistory do MAGIWorker para que voz e texto
    compartilhem o mesmo histórico de conversa.

    Exemplo:
        from magi_voz import integrar_voz_ao_magi
        voz = integrar_voz_ao_magi(magi, history=worker.history)
        magi.voz = voz
    """
    voz = MAGIVoz(magi, history=history)
    magi.voz = voz
    return voz


if __name__ == "__main__":
    print(f"""
{Fore.RED}╔══════════════════════════════════════╗
║   M A G I  —  S I S T E M A  V O Z  ║
╚══════════════════════════════════════╝{Style.RESET_ALL}
{Fore.WHITE}  Modo : Standalone (sem MAGISystem)
  TTS  : Edge TTS (Microsoft Neural, pt-BR-AntonioNeural)
  STT  : Google Speech Recognition (pt-BR)
""")
    voz = MAGIVoz(magi=None)
    voz.iniciar()
    print(f"{Fore.YELLOW}  Pressione Ctrl+C para encerrar.\n")
    try:
        while voz._ativo:
            time.sleep(0.5)
    except KeyboardInterrupt:
        voz.parar()
        print(f"\n{Fore.RED}  [MAGI VOZ] Encerrado.{Style.RESET_ALL}")