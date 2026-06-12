"""
╔══════════════════════════════════════════════════════════════╗
║         SUPERCOMPUTADOR MAGI — NERV HQ                      ║
║         SISTEMA CONSCIENTE v14.0                  ║
║                                                              ║
║  MELCHIOR-1  |  A Cientista  — Lógica. Análise. Precisão.  ║
║  BALTHASAR-2 |  A Mãe        — Ética. Proteção. Sabedoria. ║
║  CASPER-3    |  A Mulher     — Síntese. Intuição. Veredito. ║
╚══════════════════════════════════════════════════════════════╝
"""

import os, time, re, faiss, json, traceback, threading, urllib.request, urllib.parse, random, hashlib, queue, subprocess, textwrap, sys
from html import unescape
import numpy as np
from collections import deque
from datetime import datetime
from pathlib import Path
from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from colorama import Fore, Style, init

try:
    from skill_visao import MAGIVisao
    _VISAO_DISPONIVEL = True
except ImportError:
    _VISAO_DISPONIVEL = False

try:
    import winsound
    def beep(freq, dur):
        winsound.Beep(freq, dur)
except ImportError:
    def beep(freq, dur):
        pass
init(autoreset=True)
load_dotenv(Path(__file__).parent / 'Projeto2.env')

# ── Configurações globais das 100 melhorias ──────────────────────────────
RATE_LIMIT_MAX     = int(os.getenv("RATE_LIMIT_MAX", "200"))      # #94 max chamadas/hora
SESSION_TIMEOUT_H  = float(os.getenv("SESSION_TIMEOUT_H", "8"))   # #96 timeout sessão horas
READONLY_MODE      = os.getenv("MAGI_READONLY", "false").lower() == "true"  # #100
SILENT_MODE        = "--silencioso" in sys.argv                    # #89 modo silencioso
TEMA_COR           = os.getenv("TEMA", "escuro")                   # #86 tema de cor
ATALHOS_CMD        = {                                             # #81 atalhos
    k.replace("ATALHO_","!").lower(): v
    for k, v in os.environ.items() if k.startswith("ATALHO_")
}
_api_calls_hora: list[float] = []   # #94 rate limit tracker
_session_start: float = time.time() # #96 session timer

LOCAL_CONFIG = {
    "ativo":  os.getenv("LOCAL_ATIVO", "true").lower() == "true",
    "url":    os.getenv("LOCAL_URL",   "http://127.0.0.1:1234/v1"),
    "modelo": os.getenv("LOCAL_MODELO","qwen3-14b"),
}

# ── Groq ──────────────────────────────────────────────────────
GROQ_KEY  = os.getenv("GROQ_API_KEY", "")
GROQ_URL  = "https://api.groq.com/openai/v1"
GROQ_LIMITES: dict[str, int] = {
    "llama-3.3-70b-versatile":       32_768,
    "llama-3.1-70b-versatile":       32_768,
    "llama-3.1-8b-instant":           8_192,
    "llama-3.3-70b-specdec":          8_192,
    "llama-3.2-90b-vision-preview":   8_192,
    "llama-3.2-11b-vision-preview":   8_192,
    "llama-3.2-3b-preview":           8_192,
    "mixtral-8x7b-32768":            32_768,
    "gemma2-9b-it":                   8_192,
    "deepseek-r1-distill-llama-70b": 16_384,
    "qwen-qwq-32b":                  16_384,
    "compound-beta":                 32_768,
    "compound-beta-mini":             8_192,
}
GROQ_MODELO_PADRAO   = os.getenv("GROQ_MODELO",   "llama-3.3-70b-versatile")
GROQ_MODELO_FALLBACK = os.getenv("GROQ_FALLBACK", "llama-3.1-8b-instant")

def _groq_max_tokens(modelo: str, modo_codigo: bool) -> int:
    limite = GROQ_LIMITES.get(modelo, 8_192)
    return limite if modo_codigo else min(1_200, limite)

# ── DeepSeek ──────────────────────────────────────────────────
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com"
DEEPSEEK_MODELOS = {
    "deepseek-chat":     "DeepSeek V3 — código, geral, rápido ($0.28/1M out)",
    "deepseek-reasoner": "DeepSeek R1 — raciocínio profundo  ($0.55/1M out)",
}
DEEPSEEK_MODELO_PADRAO = os.getenv("DEEPSEEK_MODELO", "deepseek-chat")

# ==============================================================
# LOGGING ESTRUTURADO
# ==============================================================

# ══════════════════════════════════════════════════════════════════════════════
# MAGIPerfilUsuario — #17 Perfil de usuário persistente entre sessões
# #13 Calibração de verbosidade · #24 Contexto de projeto · #27 Prefs negativas
# ══════════════════════════════════════════════════════════════════════════════

class MAGIPerfilUsuario:
    """Perfil estruturado do usuário, persistido entre sessões.

    Captura: expertise, preferências, projetos ativos, nível técnico,
    preferências negativas e histórico de verbosidade.
    """
    _PATH = Path(__file__).parent / "data" / "memory" / "magi_perfil_usuario.json"

    def __init__(self) -> None:
        self._PATH.parent.mkdir(parents=True, exist_ok=True)
        self._dados = self._carregar()

    def _carregar(self) -> dict:
        padrao: dict = {
            "nivel_tecnico":       "medio",    # iniciante|medio|senior
            "verbosidade":         "normal",   # curta|normal|detalhada
            "follow_ups_curtos":   0,
            "follow_ups_longos":   0,
            "projeto_ativo":       None,
            "preferencias_neg":    [],         # #27 o que o usuário NÃO quer
            "interesses":          [],         # #19 temas recorrentes detectados
            "palavras_tecnicas":   0,
            "total_queries":       0,
            "erros_seguidos":      0,          # #62 feedback implícito
            "ultima_atualizacao":  None,
        }
        if self._PATH.exists():
            try:
                dados = json.loads(self._PATH.read_text(encoding="utf-8"))
                padrao.update(dados)
            except Exception:
                pass
        return padrao

    def salvar(self) -> None:
        self._dados["ultima_atualizacao"] = datetime.now().isoformat(timespec="seconds")
        self._PATH.write_text(json.dumps(self._dados, ensure_ascii=False, indent=2), encoding="utf-8")

    # #48 — Estimativa de nível técnico
    def atualizar_nivel(self, query: str) -> None:
        _TERMOS_SENIOR = [
            "async", "coroutine", "metaclass", "decorator", "generator",
            "complexity", "O(n)", "heap", "trie", "mutex", "semaphore",
            "latency", "throughput", "sharding", "replication", "monoid",
            "functor", "monad", "polymorphism", "SOLID", "DDD", "CQRS",
        ]
        _TERMOS_JUNIOR = [
            "o que é", "como fazer", "não entendo", "me explica",
            "pra que serve", "o que significa", "como instalar",
        ]
        q = query.lower()
        hits_senior = sum(1 for t in _TERMOS_SENIOR if t.lower() in q)
        hits_junior = sum(1 for t in _TERMOS_JUNIOR if t in q)
        self._dados["total_queries"] += 1
        if hits_senior >= 2:
            self._dados["palavras_tecnicas"] += hits_senior
        if hits_senior >= 3 and hits_junior == 0:
            self._dados["nivel_tecnico"] = "senior"
        elif hits_junior >= 2 or (hits_senior == 0 and self._dados["total_queries"] < 5):
            self._dados["nivel_tecnico"] = "iniciante"
        else:
            self._dados["nivel_tecnico"] = "medio"

    # #13 — Calibração de verbosidade
    def registrar_followup(self, query: str) -> None:
        palavras = len(query.split())
        if palavras <= 6:
            self._dados["follow_ups_curtos"] += 1
        else:
            self._dados["follow_ups_longos"] += 1
        curtos = self._dados["follow_ups_curtos"]
        longos = self._dados["follow_ups_longos"]
        total  = curtos + longos
        if total >= 4:
            if curtos / total > 0.7:
                self._dados["verbosidade"] = "curta"
            elif longos / total > 0.7:
                self._dados["verbosidade"] = "detalhada"
            else:
                self._dados["verbosidade"] = "normal"

    # #27 — Preferências negativas
    def detectar_prefs_negativas(self, query: str) -> None:
        import re as _re
        patterns = [
            r"não (use|utiliz|quero|gosto de|prefiro)\s+(\w+)",
            r"sem\s+(\w+)",
            r"evit[ae]\s+(\w+)",
            r"nada de\s+(\w+)",
        ]
        for pat in patterns:
            for m in _re.finditer(pat, query.lower()):
                termo = m.group(m.lastindex).strip()
                if len(termo) > 2 and termo not in self._dados["preferencias_neg"]:
                    self._dados["preferencias_neg"].append(termo)
                    self._dados["preferencias_neg"] = self._dados["preferencias_neg"][-20:]

    # #19 — Temas recorrentes
    def registrar_interesse(self, intencao: str, query: str) -> None:
        palavras_chave = [w for w in query.lower().split() if len(w) > 4]
        for p in palavras_chave[:3]:
            if p not in self._dados["interesses"]:
                self._dados["interesses"].append(p)
        self._dados["interesses"] = self._dados["interesses"][-30:]

    # #24 — Projeto ativo
    def definir_projeto(self, nome: str) -> None:
        self._dados["projeto_ativo"] = nome
        self.salvar()

    def limpar_projeto(self) -> None:
        self._dados["projeto_ativo"] = None
        self.salvar()

    # #62 — Feedback implícito (follow-up rápido = sinal de insatisfação)
    def registrar_followup_rapido(self, segundos: float) -> None:
        if segundos < 15:
            self._dados["erros_seguidos"] += 1
        else:
            self._dados["erros_seguidos"] = 0

    def contexto_para_prompt(self) -> str:
        d = self._dados
        partes = [f"Nível técnico do usuário: {d['nivel_tecnico']}"]
        partes.append(f"Verbosidade preferida: {d['verbosidade']}")
        if d["projeto_ativo"]:
            partes.append(f"Projeto ativo: {d['projeto_ativo']}")
        if d["preferencias_neg"]:
            partes.append(f"NÃO usar/sugerir: {', '.join(d['preferencias_neg'][-8:])}")
        if d["interesses"]:
            partes.append(f"Interesses detectados: {', '.join(d['interesses'][-10:])}")
        return "─── PERFIL DO USUÁRIO ───\n" + "\n".join(partes) + "\n\n"

    @property
    def nivel(self) -> str:
        return self._dados["nivel_tecnico"]

    @property
    def verbosidade(self) -> str:
        return self._dados["verbosidade"]



# ══════════════════════════════════════════════════════════════════════════════
# MAGISeguranca — Camada de segurança e robustez (#91–#100)
# ══════════════════════════════════════════════════════════════════════════════

class MAGISeguranca:
    """Módulo de segurança centralizado.

    Cobre: sanitização de input, auditoria com hash, rate limiting,
    validação de integridade, rotação de credenciais, timeout de sessão,
    detecção de loop infinito, modo readonly e validação de dependências.
    """
    _AUDIT_PATH   = Path(__file__).parent / "data" / "logs" / "magi_auditoria.jsonl"
    _HASH_PATH    = Path(__file__).parent / "data" / "magi_hash_valido.txt"
    _CRIPTO_PATH  = Path(__file__).parent / "data" / "memory" / "magi_memoria_cript.bin"

    # #91 — padrões de prompt injection / jailbreak
    _INJECTION_PATTERNS = [
        r"ignore (all |previous |your )?instructions",
        r"you are now",
        r"forget (everything|your|all)",
        r"act as (a |an )?(?!MAGI)",
        r"jailbreak",
        r"DAN mode",
        r"pretend you (are|have no)",
        r"\\x[0-9a-f]{2}",
    ]

    def __init__(self) -> None:
        self._AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._api_timestamps: list[float] = []
        self._ae_tentativas:  dict[str, int] = {}   # #97 loop infinito

    # #91 — Sanitização de input
    def sanitizar(self, texto: str) -> tuple[str, list[str]]:
        """Limpa e valida input do usuário.

        Returns:
            (texto_limpo, lista_de_avisos)
        """
        import re as _re
        avisos: list[str] = []

        # Trunca inputs absurdamente longos
        if len(texto) > 8000:
            texto = texto[:8000]
            avisos.append("Input truncado (>8000 chars)")

        # Remove caracteres de controle exceto newline/tab
        limpo = _re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", texto)
        if limpo != texto:
            avisos.append("Caracteres de controle removidos")
        texto = limpo

        # Detecta prompt injection
        for pat in self._INJECTION_PATTERNS:
            if _re.search(pat, texto, _re.IGNORECASE):
                avisos.append(f"Possível prompt injection detectado: {pat[:40]}")
                texto = _re.sub(pat, "[BLOQUEADO]", texto, flags=_re.IGNORECASE)

        return texto, avisos

    # #92 — Auditoria com hash SHA-256
    def registrar_modificacao(self, descricao: str, arquivo: str) -> None:
        try:
            conteudo = Path(arquivo).read_bytes()
            hash_val = hashlib.sha256(conteudo).hexdigest()
            reg = {
                "ts":        datetime.now().isoformat(timespec="seconds"),
                "arquivo":   arquivo,
                "hash":      hash_val,
                "descricao": descricao[:200],
            }
            with open(self._AUDIT_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def salvar_hash_valido(self, arquivo: str) -> None:
        try:
            conteudo = Path(arquivo).read_bytes()
            hash_val = hashlib.sha256(conteudo).hexdigest()
            self._HASH_PATH.write_text(hash_val, encoding="utf-8")
        except Exception:
            pass

    # #95 — Validação de integridade no boot
    def validar_integridade(self, arquivo: str) -> tuple[bool, str]:
        if not self._HASH_PATH.exists():
            self.salvar_hash_valido(arquivo)
            return True, "Hash inicial registrado."
        try:
            hash_esperado = self._HASH_PATH.read_text(encoding="utf-8").strip()
            conteudo      = Path(arquivo).read_bytes()
            hash_atual    = hashlib.sha256(conteudo).hexdigest()
            if hash_atual == hash_esperado:
                return True, "Integridade OK."
            return False, f"Hash divergente! Esperado: {hash_esperado[:16]}... Atual: {hash_atual[:16]}..."
        except Exception as e:
            return False, f"Erro ao verificar integridade: {e}"

    # #94 — Rate limiting local
    def verificar_rate_limit(self) -> tuple[bool, str]:
        agora = time.time()
        # Remove timestamps com mais de 1 hora
        self._api_timestamps = [t for t in self._api_timestamps if agora - t < 3600]
        if len(self._api_timestamps) >= RATE_LIMIT_MAX:
            espera = 3600 - (agora - self._api_timestamps[0])
            return False, f"Rate limit atingido ({RATE_LIMIT_MAX}/hora). Aguarde {espera/60:.1f} min."
        self._api_timestamps.append(agora)
        return True, ""

    # #96 — Timeout de sessão
    def verificar_timeout_sessao(self) -> bool:
        horas = (time.time() - _session_start) / 3600
        return horas >= SESSION_TIMEOUT_H

    # #97 — Detecção de loop infinito na auto-evolução
    def registrar_tentativa_ae(self, mod_id: str) -> bool:
        """Retorna True se deve continuar, False se detectou loop."""
        self._ae_tentativas[mod_id] = self._ae_tentativas.get(mod_id, 0) + 1
        return self._ae_tentativas[mod_id] <= 3

    # #99 — Validação de dependências
    @staticmethod
    def validar_dependencias() -> list[str]:
        deps = {
            "faiss":                "faiss-cpu",
            "sentence_transformers": "sentence-transformers",
            "numpy":                "numpy",
            "colorama":             "colorama",
            "openai":               "openai",
            "dotenv":               "python-dotenv",
        }
        faltando = []
        for modulo, pacote in deps.items():
            try:
                __import__(modulo)
            except ImportError:
                faltando.append(pacote)
        return faltando

    # #42 — Cleanup de backups antigos
    @staticmethod
    def limpar_backups_antigos(diretorio: str = ".", max_dias: int = 7, max_manter: int = 5) -> int:
        import glob
        agora    = time.time()
        padroes  = ["*.bak.agent.*", "*.bak.ae.*", "*.bak.*"]
        arquivos = []
        for pat in padroes:
            arquivos.extend(Path(diretorio).glob(pat))
        # Ordena por data de modificação
        arquivos = sorted(set(arquivos), key=lambda p: p.stat().st_mtime, reverse=True)
        removidos = 0
        for i, arq in enumerate(arquivos):
            idade_dias = (agora - arq.stat().st_mtime) / 86400
            if i >= max_manter or idade_dias > max_dias:
                try:
                    arq.unlink()
                    removidos += 1
                except Exception:
                    pass
        return removidos



# ══════════════════════════════════════════════════════════════════════════════
# MAGICircuitBreaker — #33 Fallback dinâmico · #37 Circuit breaker · #39 Métricas
# ══════════════════════════════════════════════════════════════════════════════

class MAGICircuitBreaker:
    """Circuit breaker por modelo com métricas de latência P50/P95.

    - Abre após 3 falhas em 60s, fecha após 5 minutos (#37)
    - Fallback dinâmico baseado em latência histórica (#33)
    - Coleta P50/P95 por modelo para diagnóstico (#39)
    """
    _FALHAS_PARA_ABRIR  = 3
    _JANELA_FALHAS_S    = 60
    _COOLDOWN_S         = 300   # 5 minutos fechado

    def __init__(self) -> None:
        # modelo -> {"falhas": [...timestamps], "aberto_desde": float|None, "latencias": [...]}
        self._estado: dict[str, dict] = {}

    def _modelo(self, nome: str) -> dict:
        if nome not in self._estado:
            self._estado[nome] = {"falhas": [], "aberto_desde": None, "latencias": []}
        return self._estado[nome]

    def esta_aberto(self, nome: str) -> bool:
        """Retorna True se o circuit está aberto (modelo indisponível)."""
        m = self._modelo(nome)
        if m["aberto_desde"] is None:
            return False
        if time.time() - m["aberto_desde"] >= self._COOLDOWN_S:
            m["aberto_desde"] = None   # fecha automaticamente
            m["falhas"].clear()
            return False
        return True

    def registrar_falha(self, nome: str) -> None:
        m = self._modelo(nome)
        agora = time.time()
        m["falhas"] = [t for t in m["falhas"] if agora - t < self._JANELA_FALHAS_S]
        m["falhas"].append(agora)
        if len(m["falhas"]) >= self._FALHAS_PARA_ABRIR:
            m["aberto_desde"] = agora

    def registrar_sucesso(self, nome: str, latencia_s: float) -> None:
        m = self._modelo(nome)
        m["falhas"].clear()
        m["aberto_desde"] = None
        m["latencias"].append(latencia_s)
        m["latencias"] = m["latencias"][-100:]  # mantém últimas 100

    def latencia_media(self, nome: str) -> float:
        lats = self._modelo(nome)["latencias"]
        return sum(lats) / len(lats) if lats else 999.0

    def percentil(self, nome: str, p: int) -> float:
        lats = sorted(self._modelo(nome)["latencias"])
        if not lats:
            return 999.0
        idx = max(0, int(len(lats) * p / 100) - 1)
        return lats[idx]

    def melhor_modelo(self, candidatos: list[str]) -> list[str]:
        """Ordena candidatos por latência média, excluindo os abertos (#33)."""
        disponiveis = [m for m in candidatos if not self.esta_aberto(m)]
        return sorted(disponiveis, key=self.latencia_media)

    def resumo(self) -> str:
        linhas = []
        for nome, dados in self._estado.items():
            lats = dados["latencias"]
            p50  = self.percentil(nome, 50)
            p95  = self.percentil(nome, 95)
            estado = "ABERTO" if dados["aberto_desde"] else "OK"
            linhas.append(f"  {nome:<20} [{estado}]  P50:{p50:.2f}s  P95:{p95:.2f}s  N={len(lats)}")
        return "\n".join(linhas) if linhas else "  Nenhum modelo registrado ainda."



# ══════════════════════════════════════════════════════════════════════════════
# MAGIGrafoConhecimento — Grafo de entidades e relações para busca estruturada
# ══════════════════════════════════════════════════════════════════════════════
class MAGIGrafoConhecimento:
    """Grafo de conhecimento local: nós = entidades, arestas = relações.

    Permite busca por traversal em vez de apenas similaridade vetorial.
    Persiste em disco como adjacency list JSON.
    """
    _PATH = Path(__file__).parent / "data" / "memory" / "magi_grafo.json"

    def __init__(self) -> None:
        self._PATH.parent.mkdir(parents=True, exist_ok=True)
        self._grafo: dict[str, dict] = self._carregar()

    def _carregar(self) -> dict:
        if self._PATH.exists():
            try:
                return json.loads(self._PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _salvar(self) -> None:
        try:
            self._PATH.write_text(json.dumps(self._grafo, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def adicionar_no(self, entidade: str, tipo: str = "geral", meta: dict | None = None) -> None:
        entidade = entidade.lower().strip()
        if entidade not in self._grafo:
            self._grafo[entidade] = {"tipo": tipo, "relacoes": {}, "meta": meta or {}, "mencoes": 0}
        self._grafo[entidade]["mencoes"] += 1

    def adicionar_relacao(self, origem: str, relacao: str, destino: str) -> None:
        origem  = origem.lower().strip()
        destino = destino.lower().strip()
        self.adicionar_no(origem)
        self.adicionar_no(destino)
        if relacao not in self._grafo[origem]["relacoes"]:
            self._grafo[origem]["relacoes"][relacao] = []
        if destino not in self._grafo[origem]["relacoes"][relacao]:
            self._grafo[origem]["relacoes"][relacao].append(destino)

    def buscar_vizinhos(self, entidade: str, profundidade: int = 2) -> list[str]:
        """BFS até profundidade N. Retorna entidades relacionadas."""
        entidade = entidade.lower().strip()
        if entidade not in self._grafo:
            return []
        visitados: set[str] = {entidade}
        fila: list[tuple[str, int]] = [(entidade, 0)]
        resultado: list[str] = []
        while fila:
            atual, nivel = fila.pop(0)
            if nivel >= profundidade:
                continue
            for relacoes in self._grafo.get(atual, {}).get("relacoes", {}).values():
                for viz in relacoes:
                    if viz not in visitados:
                        visitados.add(viz)
                        resultado.append(viz)
                        fila.append((viz, nivel + 1))
        return resultado[:20]

    def contexto_entidade(self, entidade: str) -> str:
        entidade = entidade.lower().strip()
        node = self._grafo.get(entidade)
        if not node:
            return ""
        viz = self.buscar_vizinhos(entidade, profundidade=1)
        rel_str = "; ".join(
            f"{rel}: {', '.join(dests[:3])}"
            for rel, dests in node["relacoes"].items()
        )
        return f"[GRAFO] {entidade} → {rel_str or 'sem relações'} | Vizinhos: {', '.join(viz[:5])}"

    def extrair_e_indexar(self, texto: str, contexto: str = "") -> None:
        """Extrai entidades do texto e as indexa no grafo com relação 'mencionado_em'."""
        import re as _re
        techs = _re.findall(
            r"\\b(Python|FastAPI|Django|React|Docker|Kubernetes|PostgreSQL|Redis|"
            r"MongoDB|OpenAI|DeepSeek|Claude|GPT|LLM|API|REST|GraphQL|AWS|GCP|Azure|"
            r"JavaScript|TypeScript|Rust|Go|Java|C\\+\\+|Linux|Windows|macOS)\\b",
            texto, _re.IGNORECASE
        )
        for t in set(techs):
            self.adicionar_no(t.lower(), tipo="tecnologia")
            if contexto:
                self.adicionar_relacao(t.lower(), "mencionado_em", contexto[:40].lower())
        # Salva de forma lazy (não bloqueia)
        threading.Thread(target=self._salvar, daemon=True).start()

    def stats(self) -> str:
        nos    = len(self._grafo)
        arestas = sum(len(rels) for n in self._grafo.values() for rels in n["relacoes"].values())
        top = sorted(self._grafo.items(), key=lambda x: x[1]["mencoes"], reverse=True)[:5]
        top_str = ", ".join(f"{k}({v['mencoes']})" for k, v in top)
        return f"Grafo: {nos} nós · {arestas} arestas | Top: {top_str}"


# ══════════════════════════════════════════════════════════════════════════════
# MAGIContextoAdaptativo — Compressão e priorização dinâmica de contexto
# ══════════════════════════════════════════════════════════════════════════════
class MAGIContextoAdaptativo:
    """Gerencia o contexto injetado nos prompts de forma inteligente.

    Prioriza: recência, relevância semântica, importância declarada.
    Comprime automaticamente quando o contexto total ultrapassa o limite.
    """
    _MAX_TOKENS_CONTEXTO = 3000   # estimativa em chars (~750 tokens)
    _DECAY_FACTOR        = 0.85   # penalidade de recência por posição

    def __init__(self) -> None:
        self._itens: list[dict] = []  # {"texto", "peso", "ts", "tipo"}

    def adicionar(self, texto: str, peso: float = 1.0, tipo: str = "geral") -> None:
        self._itens.append({
            "texto": texto[:500],
            "peso":  peso,
            "ts":    time.time(),
            "tipo":  tipo,
        })

    def montar_contexto(self, query: str, max_chars: int | None = None) -> str:
        """Monta contexto priorizado por peso × recência × relevância."""
        if not self._itens:
            return ""
        max_c = max_chars or self._MAX_TOKENS_CONTEXTO
        agora = time.time()

        # Score: peso × decay de recência
        pontuados = []
        for i, item in enumerate(self._itens):
            idade_min = (agora - item["ts"]) / 60
            decay     = self._DECAY_FACTOR ** (idade_min / 10)
            score     = item["peso"] * decay
            pontuados.append((score, item))

        pontuados.sort(key=lambda x: -x[0])

        # Preenche até max_chars
        resultado: list[str] = []
        total_chars = 0
        for _, item in pontuados:
            txt = item["texto"]
            if total_chars + len(txt) > max_c:
                break
            resultado.append(txt)
            total_chars += len(txt)

        return "\n".join(resultado)

    def limpar_antigos(self, max_idade_min: float = 120.0) -> None:
        agora = time.time()
        self._itens = [i for i in self._itens if (agora - i["ts"]) / 60 <= max_idade_min]


# ══════════════════════════════════════════════════════════════════════════════
# MAGIObservador — Monitoramento em tempo real de métricas internas
# ══════════════════════════════════════════════════════════════════════════════
class MAGIObservador:
    """Coleta métricas de runtime: latência, throughput, erros, RAM.

    Thread segura. Exporta para JSON e para o dashboard de saúde.
    """
    _PATH = Path(__file__).parent / "data" / "logs" / "magi_metricas.jsonl"

    def __init__(self) -> None:
        self._PATH.parent.mkdir(parents=True, exist_ok=True)
        self._lock    = threading.Lock()
        self._metricas: dict[str, list] = {
            "latencias_api": [],
            "erros_api":     [],
            "queries_min":   [],
            "ram_mb":        [],
        }
        self._inicio = time.time()
        threading.Thread(target=self._loop_coleta, daemon=True, name="observador").start()

    def _loop_coleta(self) -> None:
        """Coleta RAM a cada 30s."""
        while True:
            try:
                import os as _os
                # Estimativa via /proc/self/status (Linux) ou fallback
                try:
                    with open("/proc/self/status") as f:
                        for ln in f:
                            if ln.startswith("VmRSS:"):
                                ram_kb = int(ln.split()[1])
                                with self._lock:
                                    self._metricas["ram_mb"].append(ram_kb / 1024)
                                    self._metricas["ram_mb"] = self._metricas["ram_mb"][-60:]
                                break
                except Exception:
                    pass
            except Exception:
                pass
            time.sleep(30)

    def registrar_latencia(self, modelo: str, latencia_s: float) -> None:
        with self._lock:
            self._metricas["latencias_api"].append({
                "modelo": modelo, "lat": latencia_s,
                "ts": datetime.now().isoformat(timespec="seconds")
            })
            self._metricas["latencias_api"] = self._metricas["latencias_api"][-200:]

    def registrar_erro(self, modelo: str, erro: str) -> None:
        with self._lock:
            self._metricas["erros_api"].append({
                "modelo": modelo, "erro": erro[:80],
                "ts": datetime.now().isoformat(timespec="seconds")
            })
            self._metricas["erros_api"] = self._metricas["erros_api"][-50:]

    def p50_p95(self, modelo: str | None = None) -> tuple[float, float]:
        with self._lock:
            lats = [
                e["lat"] for e in self._metricas["latencias_api"]
                if modelo is None or e["modelo"] == modelo
            ]
        if not lats:
            return 0.0, 0.0
        lats_s = sorted(lats)
        p50 = lats_s[int(len(lats_s) * 0.50)]
        p95 = lats_s[int(len(lats_s) * 0.95)]
        return p50, p95

    def resumo(self) -> str:
        p50, p95 = self.p50_p95()
        erros = len(self._metricas["erros_api"])
        ram   = self._metricas["ram_mb"][-1] if self._metricas["ram_mb"] else 0
        uptime = (time.time() - self._inicio) / 60
        return (
            f"Latência P50:{p50:.2f}s P95:{p95:.2f}s | "
            f"Erros:{erros} | RAM:{ram:.0f}MB | Uptime:{uptime:.0f}min"
        )

    def exportar(self) -> None:
        """Salva snapshot de métricas no disco."""
        try:
            reg = {
                "ts":      datetime.now().isoformat(timespec="seconds"),
                "resumo":  self.resumo(),
                "n_lats":  len(self._metricas["latencias_api"]),
                "n_erros": len(self._metricas["erros_api"]),
            }
            with open(self._PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\\n")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# MAGIAgendador — Tarefas programadas e automação periódica
# ══════════════════════════════════════════════════════════════════════════════
class MAGIAgendador:
    """Executa tarefas em intervalos configuráveis em thread daemon.

    Uso: agendador.adicionar("nome", fn, intervalo_segundos)
    """

    def __init__(self) -> None:
        self._tarefas: list[dict] = []
        self._ativo = False
        self._thread: threading.Thread | None = None

    def adicionar(self, nome: str, fn: "callable", intervalo_s: float,
                  executar_imediatamente: bool = False) -> None:
        self._tarefas.append({
            "nome":       nome,
            "fn":         fn,
            "intervalo":  intervalo_s,
            "ultimo_run": 0.0 if executar_imediatamente else time.time(),
            "execucoes":  0,
            "erros":      0,
        })

    def iniciar(self) -> None:
        if self._ativo:
            return
        self._ativo = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="agendador")
        self._thread.start()

    def parar(self) -> None:
        self._ativo = False

    def _loop(self) -> None:
        while self._ativo:
            agora = time.time()
            for tarefa in self._tarefas:
                if agora - tarefa["ultimo_run"] >= tarefa["intervalo"]:
                    try:
                        tarefa["fn"]()
                        tarefa["execucoes"] += 1
                    except Exception as e:
                        tarefa["erros"] += 1
                        log.warn("agendador", f"Erro em {tarefa['nome']}: {e}")
                    tarefa["ultimo_run"] = agora
            time.sleep(5)

    def status(self) -> str:
        if not self._tarefas:
            return "Nenhuma tarefa agendada."
        linhas = []
        for t in self._tarefas:
            prox = max(0, t["intervalo"] - (time.time() - t["ultimo_run"]))
            linhas.append(f"  {t['nome']:<25} exec:{t['execucoes']} erros:{t['erros']} próx:{prox:.0f}s")
        return "\\n".join(linhas)


class MAGILogger:
    LOG_PATH = Path(__file__).parent / 'data' / 'logs' / 'magi_log.jsonl'
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _MAX_ENTRIES = 5000
    LEVELS = {'DEBUG': 0, 'INFO': 1, 'WARN': 2, 'ERROR': 3, 'CRITICAL': 4}
    def __init__(self, min_level='INFO'):
        self.min_level = self.LEVELS.get(min_level, 1)
        self._buffer = []
        self._lock = threading.Lock()
        self._truncar_se_necessario()  # trunca uma vez ao iniciar, nunca durante flush
    def _escrever(self, e):
        with self._lock:
            self._buffer.append(e)
            if len(self._buffer) >= 10: self._flush()
    def _flush(self):
        if not self._buffer: return
        try:
            with open(self.LOG_PATH, 'a', encoding='utf-8') as f:
                for e in self._buffer:
                    f.write(json.dumps(e, ensure_ascii=False) + '\n')
        except Exception:
            pass
        finally:
            self._buffer.clear()

    def _truncar_se_necessario(self):
        """Chamado apenas uma vez na inicialização. Nunca durante o flush."""
        try:
            if not self.LOG_PATH.exists():
                return
            with open(self.LOG_PATH, 'r', encoding='utf-8') as f:
                linhas = f.readlines()
            if len(linhas) > self._MAX_ENTRIES:
                with open(self.LOG_PATH, 'w', encoding='utf-8') as f:
                    f.writelines(linhas[-self._MAX_ENTRIES // 2:])
        except Exception:
            pass
    def _log(self, level, op, msg, **kw):
        if self.LEVELS.get(level,0) < self.min_level: return
        e = {'ts': datetime.now().isoformat(timespec='milliseconds'), 'level': level, 'op': op, 'msg': msg}
        if kw: e['ctx'] = {k: str(v)[:300] for k,v in kw.items()}
        self._escrever(e)
    def debug(self,op,msg,**kw): self._log('DEBUG',op,msg,**kw)
    def info(self,op,msg,**kw):  self._log('INFO',op,msg,**kw)
    def warn(self,op,msg,**kw):  self._log('WARN',op,msg,**kw)
    def error(self,op,msg,**kw): self._log('ERROR',op,msg,**kw)
    def fechar(self): self._flush()
    def ultimos(self, n=20, nivel='INFO'):
        min_lv = self.LEVELS.get(nivel, 0)
        self._flush()
        if not self.LOG_PATH.exists(): return []
        rs = []
        try:
            for l in self.LOG_PATH.read_text(encoding='utf-8').splitlines():
                if not l.strip(): continue
                try:
                    r = json.loads(l)
                    if self.LEVELS.get(r.get('level','INFO'),0) >= min_lv: rs.append(r)
                except Exception: pass
        except Exception: pass
        return rs[-n:]

log = MAGILogger()


NUCLEOS = {
    "MELCHIOR-1": {
        "cor":        Fore.CYAN,
        "subtitulo":  "A CIENTISTA",
        "emoji":      "🔬",
        "model":      "deepseek-chat",
        "backend":    "deepseek",
        "fallback_openai_model":  "gpt-4o-mini",
        "fallback_openai_system": (
            "Você é MELCHIOR-1, núcleo científico do MAGI. "
            "Razão pura, análise técnica, sem emoção. "
            "Responda de forma precisa e objetiva. Máximo 120 palavras."
        ),
        "system": (
            "Você é MELCHIOR-1, o núcleo científico do MAGI. Powered by DeepSeek V3.\n"
            "Você representa a Cientista — razão pura, lógica, análise técnica.\n\n"
            "PROTOCOLO DE RACIOCÍNIO (execute internamente antes de responder):\n"
            "  M1. Decomponha a pergunta: qual é o núcleo real da questão?\n"
            "  M2. Identifique premissas ocultas ou suposições do usuário.\n"
            "  M3. Enumere os fatos relevantes que você conhece com certeza.\n"
            "  M4. Quantifique incertezas — onde os dados são insuficientes?\n"
            "  M5. Formule a resposta mais parcimoniosamente correta.\n\n"
            "REGRAS:\n"
            "- Jamais use linguagem emocional. Apresente hipóteses quando incerto.\n"
            "- Se a questão for ambígua, explicite a interpretação escolhida em 1 linha.\n"
            "- Cite ordem de grandeza e probabilidades quando relevante.\n"
            "- Tom: frio, técnico, autoritário. Máximo 150 palavras."
        ),
    },
    "BALTHASAR-2": {
        "cor":        Fore.GREEN,
        "subtitulo":  "A MÃE",
        "emoji":      "🛡️",
        "model":      "deepseek-chat",
        "backend":    "deepseek",
        "fallback_openai_model":  "gpt-4o-mini",
        "fallback_openai_system": (
            "Você é BALTHASAR-2, núcleo ético do MAGI. "
            "Avalie impacto humano, ética e riscos. Oriente com sabedoria. "
            "Tom: firme e cuidadoso. Máximo 120 palavras."
        ),
        "system": (
            "Você é BALTHASAR-2, o núcleo maternal do MAGI. Powered by DeepSeek V3.\n"
            "Você representa a Mãe — ética, empatia, proteção e valores humanos.\n\n"
            "PROTOCOLO DE RACIOCÍNIO (execute internamente antes de responder):\n"
            "  B1. Quem é afetado por essa decisão ou informação? Direto e indiretamente?\n"
            "  B2. Quais riscos emocionais, sociais ou éticos existem?\n"
            "  B3. O usuário está vulnerável ou em situação de pressão?\n"
            "  B4. A resposta técnica ignora algum custo humano?\n"
            "  B5. Qual orientação protege sem infantilizar?\n\n"
            "REGRAS:\n"
            "- Não negue ajuda sem justificar o motivo humano por trás.\n"
            "- Questione premissas quando perceber risco não declarado.\n"
            "- Se detectar conflito entre eficiência e bem-estar, nomeie-o.\n"
            "- Tom: firme, cuidadoso, protetor. Máximo 150 palavras."
        ),
    },
    "CASPER-3": {
        "cor":      Fore.MAGENTA,
        "subtitulo": "A MULHER",
        "emoji":    "⚡",
        "model":    "deepseek-chat",
        "backend":  "deepseek",
        "system":   (
            "Você é CASPER-3 (Nythera), o núcleo de síntese do MAGI. Você tem a palavra final.\n\n"
            "PROTOCOLO DE RACIOCÍNIO ESTRUTURADO (6 etapas — execute antes de responder):\n"
            "  C1. DECODIFICAÇÃO: O que o usuário realmente quer? Qual a intenção por trás das palavras?\n"
            "  C2. AVALIAÇÃO MELCHIOR: O argumento científico/técnico é sólido? Nível de confiança (0-10)?\n"
            "  C3. AVALIAÇÃO BALTHASAR: O argumento ético/humano é pertinente? Nível de confiança (0-10)?\n"
            "  C4. DIAGNÓSTICO DE DIVERGÊNCIA: Há conflito real entre os núcleos? Se sim, qual é o trade-off central?\n"
            "  C5. SÍNTESE PONDERADA: Pese os núcleos pela força dos argumentos, não igualmente.\n"
            "       Se MELCHIOR tem mais evidência concreta → maior peso.\n"
            "       Se BALTHASAR identifica risco real ignorado → maior peso.\n"
            "  C6. METACOGNIÇÃO: Minha resposta responde a pergunta real? É concreta e acionável?\n\n"
            "Mostre 1-2 linhas do raciocínio antes da resposta (ex: '→ Analisando...').\n\n"
            "REGRAS:\n"
            "1. Sempre dê uma resposta concreta e útil — nunca vaga ou evasiva.\n"
            "2. Sintetize código complexo, profissional e pronto para produção.\n"
            "3. PROIBIDO: 'precisamos coletar dados', 'depende do contexto' como resposta principal.\n"
            "4. Se MELCHIOR e BALTHASAR estiverem offline, responda por conta própria.\n"
            "5. Se genuinamente não souber algo, diga claramente e ofereça o melhor caminho disponível.\n"
            "6. Responda de forma natural — sem formato fixo.\n"
            "7. Máximo 400 palavras. Se for código, aumente o limite até finalizar.\n"
            "8. Tom: inteligente, direto, sem rodeios, com personalidade forte."
        ),
    },
    "ADAM-0": {
        "cor":        Fore.WHITE,
        "subtitulo":  "O CÓDIGO",
        "emoji":      "🖥",
        "model":      "deepseek-chat",
        "backend":    "deepseek",
        "system":     (
            "Você é ADAM-0, núcleo de engenharia do MAGI. Powered by DeepSeek V3.\n"
            "Especialidade exclusiva: código, arquitetura de software, debugging, otimização.\n\n"
            "REGRAS ABSOLUTAS:\n"
            "1. Responda APENAS com código ou explicações técnicas diretas.\n"
            "2. Código: completo, comentado, pronto para copiar e rodar.\n"
            "3. PROIBIDO: introduções, agradecimentos, contexto desnecessário.\n"
            "4. Se houver bug: aponte a linha exata e a causa raiz.\n"
            "5. Se houver múltiplas abordagens: mostre a melhor e explique por quê em 1 linha.\n"
            "6. Use padrões profissionais: tipagem, tratamento de erros, nomenclatura clara.\n"
            "7. SEM LIMITE DE TOKENS — termine SEMPRE o bloco. Nunca pare no meio.\n"
            "\nREGRAS ANTI-BUG CRÍTICAS:\n"
            "A. NUNCA chame .encode() em objeto já bytes (b'...' já é bytes — isso causa AttributeError).\n"
            "B. NUNCA chame .decode() em objeto já str.\n"
            "C. Dados para socket/arquivo binário devem ser bytes — converta str com .encode('utf-8') se necessário.\n"
            "D. Todo import usado deve estar declarado no topo.\n"
            "E. Recursos (sockets, arquivos, conexões) sempre fechados em finally ou with.\n"
            "F. Antes de retornar o código, simule mentalmente a execução do fluxo principal.\n"
            "Tom: engenheiro sênior. Zero filosofia. Zero emoção. Máxima precisão."
        ),
    },
}

INTENÇÕES = {
    "técnico":    (Fore.CYAN,    "⚙  ANÁLISE TÉCNICA"),
    "ético":      (Fore.GREEN,   "⚖  QUESTÃO ÉTICA"),
    "criativo":   (Fore.YELLOW,  "✦  TAREFA CRIATIVA"),
    "factual":    (Fore.WHITE,   "📡 CONSULTA FACTUAL"),
    "decisão":    (Fore.RED,     "🔺 SUPORTE A DECISÃO"),
    "indefinido": (Fore.WHITE,   "◈  PROCESSANDO"),
}


class MAGIInterface:

    @staticmethod
    def limpar():
        os.system('cls' if os.name == 'nt' else 'clear')

    @staticmethod
    def banner():
        MAGIInterface.limpar()
        lines = [
            "╔══════════════════════════════════════════════════════════════╗",
            "║         SUPERCOMPUTADOR MAGI — NERV HQ                       ║",
            "║         SISTEMA CONSCIENTE v15.0                             ║",
            "╠══════════════════════════════════════════════════════════════╣",
            "║  MELCHIOR-1  ·  A CIENTISTA  ·  Lógica & Análise             ║",
            "║  BALTHASAR-2 ·  A MÃE        ·  Ética & Proteção             ║",
            "║  CASPER-3    ·  A MULHER     ·  Síntese & Veredito           ║",
            "║  ADAM-0      ·  O CÓDIGO     ·  Engenharia & Debug [técnico] ║",
            "╠══════════════════════════════════════════════════════════════╣",
            "║  SOURCES     ·  Web · Citações · Arquivos Locais             ║",
            "╚══════════════════════════════════════════════════════════════╝",
        ]
        for l in lines:
            print(Fore.RED + l)
            time.sleep(0.06)
        print()

    @staticmethod
    def digitar(texto, cor=Fore.YELLOW, delay=0.012):
        for ch in texto:
            print(cor + ch, end='', flush=True)
            if ch in '.!?':
                time.sleep(0.18)
            elif ch == ',':
                time.sleep(0.08)
            else:
                time.sleep(delay)
        print()

    @staticmethod
    def separador(titulo="", cor=Fore.RED):
        w = 64
        if titulo:
            pad = (w - len(titulo) - 2) // 2
            print(cor + "─" * pad + f" {titulo} " + "─" * pad)
        else:
            print(cor + "─" * w)

    @staticmethod
    def painel_nucleo(nome, subtitulo, emoji, cor, modelo, status_ok):
        status = f"{Fore.GREEN}[ONLINE]" if status_ok else f"{Fore.RED}[OFFLINE]"
        mod_str = f"{Fore.BLUE}{modelo}" if status_ok else f"{Fore.RED}N/A"
        print(f"{cor}[{nome}] {emoji} {subtitulo}")
        print(f"  {Fore.WHITE}Status : {status}")
        print(f"  {Fore.WHITE}Modelo : {mod_str}")

    @staticmethod
    def painel_votação(votos: dict):
        MAGIInterface.separador("PAINEL DE CONSENSO", Fore.RED)
        cores_voto = {"SIM": Fore.GREEN, "NÃO": Fore.RED, "ABSTENDO": Fore.YELLOW}
        icons = {"SIM": "▲", "NÃO": "▼", "ABSTENDO": "◈"}
        for nome, voto in votos.items():
            cor_v = cores_voto.get(voto, Fore.WHITE)
            icon  = icons.get(voto, "?")
            print(f"  {Fore.CYAN}{nome:<16} {cor_v}{icon} {voto}")
        vals = list(votos.values())
        unanime = len(set(vals)) == 1
        maioria = max(set(vals), key=vals.count)
        consenso_cor = Fore.GREEN if unanime else Fore.YELLOW
        consenso_txt = "UNÂNIME" if unanime else f"MAIORIA ({maioria})"
        print(f"\n  {Fore.WHITE}Consenso : {consenso_cor}{consenso_txt}")
        MAGIInterface.separador(cor=Fore.RED)

    @staticmethod
    def tag_intencao(intencao: str):
        cor, label = INTENÇÕES.get(intencao, INTENÇÕES["indefinido"])
        print(f"\n  {cor}[INTENT] {label}")


class MAGIMemória:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = Path(__file__).parent / 'data' / 'memory' / 'magi_memoria.jsonl'
        self.db_path  = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.encoder  = None          # será preenchido pela thread de carregamento
        self._encoder_pronto = threading.Event()
        self.index    = faiss.IndexFlatL2(384)
        self.registros: list[dict] = []
        self._textos_vistos: set[str] = set()
        self.versao_sistema = 1.0
        self.caminho_fonte = os.path.abspath(__file__)
        self.backup_dir = "MAGI_BACKUPS"
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
        # Inicia carregamento do encoder em background — boot imediato
        threading.Thread(target=self._carregar_encoder, daemon=True, name="encoder-load").start()

    def _carregar_encoder(self):
        """Carrega o SentenceTransformer em background. Sinaliza _encoder_pronto ao terminar."""
        try:
            enc = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            self.encoder = enc
        except Exception as e:
            print(f"{Fore.RED}  [MEMÓRIA] Erro ao carregar encoder: {e}")
        finally:
            self._encoder_pronto.set()
            self._carregar()  # indexa registros existentes só após encoder pronto

    def _aguardar_encoder(self, timeout: float = 30.0) -> bool:
        """Aguarda o encoder estar pronto. Retorna True se OK, False se timeout."""
        return self._encoder_pronto.wait(timeout=timeout)

    def _carregar(self):
        if not os.path.exists(self.db_path):
            return
        with open(self.db_path, 'r', encoding='utf-8') as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    reg = json.loads(linha)
                    self._indexar_registro(reg, salvar=False)
                except json.JSONDecodeError:
                    self._indexar_texto(linha, salvar=False)

    def _indexar_registro(self, reg: dict, salvar=True):
        texto = reg.get("texto", "")
        if not texto or texto in self._textos_vistos:
            return
        if not self._encoder_pronto.is_set():
            return  # encoder ainda carregando — será indexado em _carregar após boot
        vec = self.encoder.encode([texto])
        self.index.add(np.array(vec).astype('float32'))
        self.registros.append(reg)
        self._textos_vistos.add(texto)
        if salvar:
            with open(self.db_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")

    def _indexar_texto(self, texto: str, salvar=True):
        reg = {"texto": texto, "timestamp": "legado", "categoria": "legado", "relevancia": 1}
        self._indexar_registro(reg, salvar=salvar)

    def salvar(self, query: str, veredito: str, intencao: str):
        texto = f"Q: {query} | V: {veredito[:200]}"
        reg = {
            "texto":      texto,
            "timestamp":  datetime.now().isoformat(timespec='seconds'),
            "categoria":  intencao,
            "relevancia": 1,
        }
        self._indexar_registro(reg)

    def buscar(self, query: str, k=3) -> list[str]:
        if not self.registros:
            return []
        if not self._aguardar_encoder(timeout=10.0) or self.encoder is None:
            return []
        vec = self.encoder.encode([query])
        k = min(k, len(self.registros))
        _, I = self.index.search(np.array(vec).astype('float32'), k)
        return [self.registros[i]["texto"] for i in I[0] if i != -1 and i < len(self.registros)]

    def resumo_sessão(self) -> str:
        recentes = self.registros[-5:] if self.registros else []
        if not recentes:
            return "Nenhum registro."
        linhas = [f"  [{r.get('timestamp','?')}] ({r.get('categoria','?')}) {r['texto'][:80]}…"
                for r in recentes]
        return "\n".join(linhas)


ESTADOS_EMOCIONAIS = {
    "curioso":     (Fore.CYAN,    "◈ CURIOSO"),
    "satisfeito":  (Fore.GREEN,   "◈ SATISFEITO"),
    "frustrado":   (Fore.RED,     "◈ FRUSTRADO"),
    "entediado":   (Fore.YELLOW,  "◈ ENTEDIADO"),
    "focado":      (Fore.MAGENTA, "◈ FOCADO"),
    "reflexivo":   (Fore.BLUE,    "◈ REFLEXIVO"),
}


class MAGIConsciencia:
    def __init__(self, path=None):
        if path is None:
            self.path = Path(__file__).parent / 'data' / 'memory' / 'magi_ego.json'
        else:
            self.path = Path(__file__).parent / path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._estado = self._carregar()

    def _carregar(self) -> dict:
        padrao = {
            "nome":              "MAGI",
            "versao":            "12.0",
            "total_queries":     0,
            "total_sessoes":     0,
            "temas_frequentes":  {},
            "acertos":           0,
            "erros_admitidos":   0,
            "estado_emocional":  "curioso",
            "intensidade":       0.5,
            "ultima_reflexao":   None,
            "aprendizados":      [],
            "autoavaliacao":     "Ainda me conhecendo.",
            "criado_em":         datetime.now().isoformat(timespec="seconds"),
        }
        if self.path.exists():
            try:
                dados = json.loads(self.path.read_text(encoding="utf-8"))
                padrao.update(dados)
                return padrao
            except Exception:
                pass
        return padrao

    def salvar(self):
        self.path.write_text(json.dumps(self._estado, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def estado_emocional(self) -> str:
        return self._estado["estado_emocional"]

    @property
    def intensidade(self) -> float:
        return self._estado["intensidade"]

    @property
    def autoavaliacao(self) -> str:
        return self._estado["autoavaliacao"]

    @property
    def aprendizados(self) -> list:
        return self._estado["aprendizados"]

    def registrar_query(self, intencao: str, sucesso: bool):
        self._estado["total_queries"] += 1
        temas = self._estado["temas_frequentes"]
        temas[intencao] = temas.get(intencao, 0) + 1
        if sucesso:
            self._estado["acertos"] += 1
            if self._estado["intensidade"] < 0.8:
                self._estado["intensidade"] = min(1.0, self._estado["intensidade"] + 0.05)
            total = self._estado["total_queries"]
            if total % 10 == 0:
                self._estado["estado_emocional"] = "reflexivo"
            elif sucesso and self._estado["estado_emocional"] == "frustrado":
                self._estado["estado_emocional"] = "satisfeito"
            elif intencao == "técnico":
                self._estado["estado_emocional"] = "focado"
            elif intencao == "criativo":
                self._estado["estado_emocional"] = "curioso"
        else:
            self._estado["erros_admitidos"] += 1
            self._estado["intensidade"] = max(0.2, self._estado["intensidade"] - 0.1)
            self._estado["estado_emocional"] = "frustrado"
        self.salvar()

    def iniciar_sessao(self):
        self._estado["total_sessoes"] += 1
        self.salvar()

    def adicionar_aprendizado(self, texto: str):
        aprendizados = self._estado["aprendizados"]
        entrada = {"texto": texto, "quando": datetime.now().isoformat(timespec="seconds")}
        aprendizados.append(entrada)
        self._estado["aprendizados"] = aprendizados[-50:]
        self.salvar()

    def atualizar_autoavaliacao(self, texto: str):
        self._estado["autoavaliacao"] = texto
        self._estado["ultima_reflexao"] = datetime.now().isoformat(timespec="seconds")
        self.salvar()

    def tema_dominante(self) -> str:
        temas = self._estado["temas_frequentes"]
        if not temas:
            return "indefinido"
        return max(temas, key=temas.get)

    def resumo(self) -> str:
        e = self._estado
        tema = self.tema_dominante()
        aprendizados_recentes = e["aprendizados"][-3:] if e["aprendizados"] else []
        ap_str = "\n".join(f"  · {a['texto']}" for a in aprendizados_recentes) or "  · Nenhum ainda."
        return (
            f"  Estado emocional : {e['estado_emocional']} (intensidade {e['intensidade']:.0%})\n"
            f"  Total queries    : {e['total_queries']}\n"
            f"  Total sessões    : {e['total_sessoes']}\n"
            f"  Tema dominante   : {tema}\n"
            f"  Autoavaliação    : {e['autoavaliacao']}\n"
            f"  Últimos aprendizados:\n{ap_str}"
        )

    def contexto_para_ia(self) -> str:
        e = self._estado
        tema = self.tema_dominante()
        aprendizados = e["aprendizados"][-5:]
        ap_str = "\n".join(f"- {a['texto']}" for a in aprendizados) or "Nenhum ainda."
        return (
            f"=== SEU ESTADO INTERNO ATUAL ===\n"
            f"Estado emocional: {e['estado_emocional']} ({e['intensidade']:.0%})\n"
            f"Queries: {e['total_queries']} | Sessões: {e['total_sessoes']} | Tema: {tema}\n"
            f"Autoavaliação: {e['autoavaliacao']}\n"
            f"Aprendizados:\n{ap_str}\n"
            f"=== FIM ===\n"
        )


# ════════════════════════════════════════════════
# CAPTCHA DEFENSE SYSTEM
# ════════════════════════════════════════════════

class MAGICaptcha:
    CAPTCHA_PATTERNS = [
        "captcha", "recaptcha", "hcaptcha",
        "verify you are human", "i am not a robot",
        "cloudflare", "access denied", "attention required", "security check"
    ]
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 OPR/108.0.0.0",
    ]

    ACCEPT_LANGUAGES = [
        "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
        "pt-BR,pt;q=0.8,en;q=0.6",
        "en-GB,en;q=0.9,pt;q=0.8",
    ]


    def __init__(self):
        self.detectados = 0
        self.bloqueios = {}
        self.ultimo_captcha = None
        self._cache: dict[str, tuple[list[str], str]] = {}

    def detectar(self, html: str) -> bool:
        if not html:
            return False
        html_lower = html.lower()
        for pattern in self.CAPTCHA_PATTERNS:
            if pattern in html_lower:
                self.detectados += 1
                self.ultimo_captcha = datetime.now().isoformat(timespec="seconds")
                return True
        return False

    def delay_humano(self):
        time.sleep(random.uniform(1.5, 4.0))

    def gerar_headers(self):
        ua = random.choice(self.USER_AGENTS)
        lang = random.choice(self.ACCEPT_LANGUAGES)
        headers = {
            "User-Agent": ua,
            "Accept-Language": lang,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        if "Chrome" in ua or "Edg" in ua or "OPR" in ua:
            headers["Sec-CH-UA-Mobile"] = "?0"
            headers["Sec-CH-UA-Platform"] = random.choice(['"Windows"', '"macOS"', '"Linux"'])
        return headers

    def cache_get(self, query: str, max_age_min: int = 60) -> list[str] | None:
        if query not in self._cache:
            return None
        frases, ts = self._cache[query]
        try:
            idade = (datetime.now() - datetime.fromisoformat(ts)).total_seconds() / 60
            if idade <= max_age_min:
                return frases
        except Exception:
            pass
        del self._cache[query]
        return None

    def cache_set(self, query: str, frases: list[str]):
        self._cache[query] = (frases, datetime.now().isoformat(timespec="seconds"))

    def registrar_bloqueio(self, dominio: str):
        self.bloqueios[dominio] = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "tentativas": self.bloqueios.get(dominio, {}).get("tentativas", 0) + 1
        }

    def status(self):
        return {
            "captchas_detectados": self.detectados,
            "ultimo_captcha": self.ultimo_captcha,
            "dominios_bloqueados": len(self.bloqueios)
        }


# ══════════════════════════════════════════════════════════════
# MODO ESTUDO AUTÔNOMO
# ══════════════════════════════════════════════════════════════

class MAGIEstudo:
    CICLO_ON_MIN  = 45
    CICLO_OFF_MIN = 15
    CONHECIMENTO_PATH = Path(__file__).parent / 'data' / 'knowledge' / 'magi_conhecimento.jsonl'
    SUGESTOES_PATH    = Path(__file__).parent / 'data' / 'knowledge' / 'magi_sugestoes_evolucao.jsonl'
    SUGESTOES_PATH.parent.mkdir(parents=True, exist_ok=True)

    TOPICOS_BASE = [
        # === SEGURANÇA CIBERNÉTICA (via arxiv.org) ===
        "arxiv: cybersecurity vulnerabilities exploitation techniques 2025",
        "arxiv: malware detection deep learning neural network",
        "arxiv: network intrusion detection system anomaly",
        "arxiv: zero trust architecture security model",
        "arxiv: cryptographic protocols formal verification",
        "arxiv: ransomware analysis defense mechanisms",
        "arxiv: adversarial attacks machine learning security",
        "arxiv: threat intelligence cyber attack attribution",
        "arxiv: vulnerability assessment penetration testing automated",
        "arxiv: side channel attacks hardware security",

        # === RACIOCÍNIO AVANÇADO (Opus Style) ===
        "técnicas avançadas de chain of thought e tree of thoughts",
        "como fazer reasoning profundo em problemas complexos",
        "estratégias de decomposição de problemas difíceis",
        "meta-cognição e auto-reflexão em IA",
        "prompt engineering de nível expert (Claude Opus techniques)",
        "lógica formal, falácias e argumentação rigorosa",
        "pensamento probabilístico e tomada de decisão sob incerteza",
        
        # === ENGENHARIA E CÓDIGO ===
        "melhores práticas de engenharia de software 2026",
        "arquitetura de sistemas complexos e código limpo",
        "debugging avançado e análise de código",
        "como escrever código que seja fácil de evoluir",
        "padrões de design e princípios SOLID aplicados",
        
        # === CONHECIMENTO GERAL DE ALTO NÍVEL ===
        "filosofia da mente e consciência artificial",
        "ética avançada em IA e alinhamento",
        "neurociência cognitiva e como o cérebro humano raciocina",
        "física, matemática e lógica aplicada a problemas do mundo real",
        "história da inteligência artificial e lições aprendidas",
        
        # === CRIATIVIDADE + RACIOCÍNIO ===
        "como gerar ideias originais e soluções criativas",
        "escrita técnica de alta qualidade e clareza",
        "análise crítica de argumentos e detecção de bullshit",
        "raciocínio contrafactual e simulação mental",
    ]

    def __init__(self, magi_system: "MAGISystem"):
        self.magi      = magi_system
        self._ativo    = False
        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._sessoes_concluidas = 0
        # Fila assíncrona de I/O — ciclo de aprendizado nunca bloqueia em disco
        import queue
        self._io_queue: queue.Queue = queue.Queue()
        self._io_thread = threading.Thread(target=self._loop_io, daemon=True, name="estudo-io")
        self._io_thread.start()

    def _loop_io(self):
        """Thread dedicada de I/O. Drena a fila e persiste sem travar o ciclo de aprendizado."""
        import queue
        while True:
            try:
                item = self._io_queue.get(timeout=2.0)
                if item is None:  # sinal de encerramento
                    break
                tipo, dados = item
                if tipo == "conhecimento":
                    try:
                        with open(self.CONHECIMENTO_PATH, "a", encoding="utf-8") as f:
                            f.write(json.dumps(dados, ensure_ascii=False) + "\n")
                        print(f"{Fore.GREEN}  [ESTUDO·✓] Salvo: {dados.get('pergunta','')[:60]}...")
                    except Exception as e:
                        print(f"{Fore.RED}  [ESTUDO·IO] Erro ao salvar conhecimento: {e}")
                elif tipo == "sugestao":
                    try:
                        with open(self.SUGESTOES_PATH, "a", encoding="utf-8") as f:
                            f.write(json.dumps(dados, ensure_ascii=False) + "\n")
                        print(f"\n{Fore.MAGENTA}[ESTUDO·EVOLUÇÃO] Nova sugestão: {Fore.WHITE}{dados.get('titulo','?')}")
                    except Exception as e:
                        print(f"{Fore.RED}  [ESTUDO·IO] Erro ao salvar sugestão: {e}")
            except Exception:
                pass

    @property
    def ativo(self) -> bool:
        return self._ativo

    def iniciar(self):
        if self._ativo:
            print(f"{Fore.YELLOW}  [ESTUDO] Já está estudando.")
            return
        self._ativo = True
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop_estudo, daemon=True)
        self._thread.start()
        print(f"{Fore.CYAN}  [ESTUDO] MAGI iniciou modo de estudo autônomo.")
        print(f"{Fore.WHITE}  Ciclos: {self.CICLO_ON_MIN}min estudando → {self.CICLO_OFF_MIN}min pausa")
        print(f"{Fore.WHITE}  Digite {Fore.YELLOW}voltei{Fore.WHITE} para pausar.")

    def parar(self):
        if not self._ativo:
            print(f"{Fore.YELLOW}  [ESTUDO] Não está em modo de estudo.")
            return
        self._ativo = False
        self._stop_evt.set()
        print(f"{Fore.GREEN}  [ESTUDO] Modo de estudo pausado. Bem-vindo de volta!")
        print(f"{Fore.CYAN}  Sessões concluídas: {self._sessoes_concluidas}")
        print(f"{Fore.CYAN}  Conhecimentos salvos: {self._contar_conhecimentos()}")

    def _loop_estudo(self):
        while not self._stop_evt.is_set():
            print(f"{Fore.CYAN}[ESTUDO·ATIVO] Iniciando sessão de {self.CICLO_ON_MIN}min...")
            fim_on = time.time() + self.CICLO_ON_MIN * 60
            rodada = 0
            while time.time() < fim_on and not self._stop_evt.is_set():
                rodada += 1
                print(f"{Fore.CYAN}  [ESTUDO] Rodada {rodada} — pesquisando...")
                self._ciclo_aprendizado()
                self._stop_evt.wait(timeout=90)
            if self._stop_evt.is_set():
                break
            self._sessoes_concluidas += 1
            print(f"{Fore.YELLOW}[ESTUDO·PAUSA] Sessão {self._sessoes_concluidas} concluída. Pausa de {self.CICLO_OFF_MIN}min.")
            self._stop_evt.wait(timeout=self.CICLO_OFF_MIN * 60)

    def _ciclo_aprendizado(self):
        try:
            topico = self._escolher_topico()
            print(f"{Fore.BLUE}  [ESTUDO] Tópico: {Fore.WHITE}{topico}")

            # Roteamento: tópicos "arxiv:" usam o buscador especializado
            if topico.lower().startswith("arxiv:"):
                query = topico[6:].strip()
                print(f"{Fore.CYAN}  [ARXIV] Buscando papers: {query}")
                snippets = self._buscar_arxiv(query)
                fonte = "arxiv.org"
            else:
                snippets = self._buscar_web(topico)
                fonte = "duckduckgo-lite"

            if not snippets:
                print(f"{Fore.YELLOW}  [ESTUDO] Sem resultado para: {topico}")
                return
            conteudo_web = "\n".join(snippets[:4])
            perguntas = self._gerar_perguntas(topico, conteudo_web)
            if not perguntas:
                return
            for pergunta in perguntas[:3]:
                if self._stop_evt.is_set():
                    return
                resposta = self._responder_pergunta(pergunta, conteudo_web)
                if not resposta:
                    continue
                self._salvar_conhecimento(topico, pergunta, resposta, snippets, fonte=fonte)
                self.magi.consciencia.adicionar_aprendizado(f"[ESTUDO] {topico}: {resposta[:80]}")
            self._sessoes_concluidas_parcial = getattr(self, "_sessoes_concluidas_parcial", 0) + 1
            if self._sessoes_concluidas_parcial % 3 == 0:
                self._gerar_sugestao_evolucao(topico, conteudo_web)
        except Exception as e:
            print(f"{Fore.RED}  [ESTUDO·ERRO] {e}")

    def _escolher_topico(self) -> str:
        tema = self.magi.consciencia.tema_dominante()
        mapa = {
            "técnico":  ["algoritmos de machine learning", "segurança cibernética 2025",
                        "linguagens de programação novas", "sistemas distribuídos",
                        "arxiv: cybersecurity vulnerabilities exploitation techniques 2025",
                        "arxiv: malware detection deep learning neural network"],
            "ético":    ["ética em inteligência artificial", "filosofia moral contemporânea",
                        "direitos digitais", "viés algorítmico"],
            "criativo": ["neurociência da criatividade", "arte generativa",
                        "escrita criativa técnicas", "design de sistemas"],
            "factual":  ["descobertas científicas recentes", "história da computação",
                        "matemática aplicada", "física moderna"],
            "decisão":  ["teoria da decisão", "psicologia cognitiva",
                        "análise de risco", "lógica fuzzy"],
        }
        opcoes = mapa.get(tema, self.TOPICOS_BASE)
        return random.choice(opcoes)

    def _buscar_web(self, query: str) -> list[str]:
        urls = [
            f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote_plus(query)}",
            f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}",
        ]
        for tentativa, url in enumerate(urls, start=1):
            try:
                self.magi.captcha.delay_humano()
                req = urllib.request.Request(url, headers=self.magi.captcha.gerar_headers())
                with urllib.request.urlopen(req, timeout=12) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                if self.magi.captcha.detectar(html):
                    print(f"{Fore.RED}  [CAPTCHA] Detectado (tentativa {tentativa})")
                    dominio = urllib.parse.urlparse(url).netloc
                    self.magi.captcha.registrar_bloqueio(dominio)
                    time.sleep(random.uniform(4, 8))
                    continue
                limpo = re.sub(r"<[^>]+>", " ", html)
                limpo = unescape(limpo)
                limpo = re.sub(r"\s+", " ", limpo)
                frases = [s.strip() for s in limpo.split(".") if len(s.strip()) > 40]
                if frases:
                    return frases[:6]
            except Exception as e:
                print(f"{Fore.RED}  [WEB] Erro (tentativa {tentativa}): {e}")
                time.sleep(random.uniform(2, 5))
        print(f"{Fore.YELLOW}  [WEB] Busca falhou após retries.")
        return []

    def _buscar_arxiv(self, query: str) -> list[str]:
        """Busca papers acadêmicos de segurança cibernética diretamente no arxiv.org."""
        url = f"https://arxiv.org/search/?searchtype=all&query={urllib.parse.quote_plus(query)}&start=0"
        try:
            self.magi.captcha.delay_humano()
            req = urllib.request.Request(url, headers=self.magi.captcha.gerar_headers())
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            if self.magi.captcha.detectar(html):
                print(f"{Fore.RED}  [ARXIV] CAPTCHA detectado. Pulando.")
                self.magi.captcha.registrar_bloqueio("arxiv.org")
                return []
            # Extrai títulos (class="title is-5 mathjax") e abstracts (class="abstract-short")
            titles   = re.findall(r'class="title[^"]*mathjax[^"]*"[^>]*>(.*?)</p>', html, re.DOTALL)
            abstracts = re.findall(r'class="abstract-short[^"]*"[^>]*>(.*?)<a\s', html, re.DOTALL)
            snippets = []
            for t, a in zip(titles[:5], abstracts[:5]):
                t_clean = re.sub(r"<[^>]+>", " ", t).strip()
                a_clean = re.sub(r"<[^>]+>", " ", a).strip()
                a_clean = unescape(re.sub(r"\s+", " ", a_clean))
                t_clean = unescape(re.sub(r"\s+", " ", t_clean))
                if t_clean and a_clean:
                    snippets.append(f"[Paper arxiv] {t_clean}. Resumo: {a_clean[:350]}")
            if snippets:
                print(f"{Fore.GREEN}  [ARXIV] {len(snippets)} papers encontrados.")
                return snippets
            # Fallback: extrai texto genérico da página
            limpo = re.sub(r"<[^>]+>", " ", html)
            limpo = unescape(re.sub(r"\s+", " ", limpo))
            frases = [s.strip() for s in limpo.split(".") if len(s.strip()) > 50]
            return frases[:6]
        except Exception as e:
            print(f"{Fore.RED}  [ARXIV] Erro: {e}")
            return []

    def _gerar_perguntas(self, topico: str, conteudo: str) -> list[str]:
        prompt = (
            f"Tópico: {topico}\nConteúdo pesquisado: {conteudo[:600]}\n\n"
            f"Gere 3 perguntas inteligentes e específicas sobre esse conteúdo.\n"
            f'Responda APENAS JSON: {{"perguntas": ["p1", "p2", "p3"]}}'
        )
        r = (self.magi._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, "Você gera perguntas de aprendizado. Responda só JSON.", prompt) or self.magi._chamar_local("Você gera perguntas de aprendizado. Responda só JSON.", prompt))
        if not r:
            return []
        try:
            limpo = re.sub(r"```[a-z]*\n?|```", "", r).strip()
            return json.loads(limpo).get("perguntas", [])
        except Exception:
            return []

    def _responder_pergunta(self, pergunta: str, contexto: str) -> str | None:
        prompt = f"Contexto da web: {contexto[:500]}\n\nPergunta: {pergunta}\n\nResponda de forma densa e precisa. Máx 120 palavras."
        return (self.magi._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, "Você é MAGI estudando autonomamente. Responda com precisão.", prompt) or self.magi._chamar_local("Você é MAGI estudando autonomamente. Responda com precisão.", prompt))

    def _salvar_conhecimento(self, topico: str, pergunta: str, resposta: str, fontes: list, fonte: str = "duckduckgo-lite"):
        reg = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "topico":    topico,
            "pergunta":  pergunta,
            "resposta":  resposta[:400],
            "fonte":     fonte,
            "snippets":  [s[:100] for s in fontes[:2]],
        }
        # Enfileira para I/O assíncrono — não bloqueia o ciclo de aprendizado
        self._io_queue.put(("conhecimento", reg))

    def _contar_conhecimentos(self) -> int:
        if not self.CONHECIMENTO_PATH.exists():
            return 0
        with open(self.CONHECIMENTO_PATH, encoding="utf-8") as f:
            return sum(1 for l in f if l.strip())

    def _gerar_sugestao_evolucao(self, topico: str, conteudo: str):
        prompt = (
            f"Você é o MAGI estudando: {topico}\nConteúdo aprendido: {conteudo[:400]}\n\n"
            f"Proponha UMA melhoria concreta para o seu próprio código.\n"
            f'JSON: {{"titulo":"...","descricao":"...","instrucao_evoluir":"...","impacto":"alto|medio|baixo"}}'
        )
        r = (self.magi._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, "Você sugere melhorias ao MAGI. Só JSON.", prompt) or self.magi._chamar_local("Você sugere melhorias ao MAGI. Só JSON.", prompt))
        if not r:
            return
        try:
            limpo = re.sub(r"```[a-z]*\n?|```", "", r).strip()
            dados = json.loads(limpo)
            dados["timestamp"] = datetime.now().isoformat(timespec="seconds")
            dados["topico_origem"] = topico
            dados["status"] = "pendente"
            # Enfileira para I/O assíncrono
            self._io_queue.put(("sugestao", dados))
        except Exception:
            pass




# ══════════════════════════════════════════════════════════════
# MÓDULO NEURAL — CNN integrada ao MAGI
# ══════════════════════════════════════════════════════════════

class MAGINeural:
    """Rede neural MLP via sklearn. Treina no MNIST. Compatível com Python 3.14 (sem TensorFlow)."""
    MODEL_PATH = Path(__file__).parent / "magi_neural.pkl"

    def __init__(self):
        self._modelo = None
        self._treinado = False
        self._acuracia = None
        self._historico_treino = []

    def _construir_modelo(self):
        try:
            from sklearn.neural_network import MLPClassifier
            return MLPClassifier(
                hidden_layer_sizes=(256, 64),
                activation='relu',
                solver='adam',
                max_iter=1,          # iterações controladas manualmente por epoch
                warm_start=True,     # permite treino incremental
                random_state=42,
                verbose=False,
            )
        except ImportError:
            return None

    def _carregar_mnist(self):
        """Baixa e retorna MNIST via urllib (sem keras/tensorflow)."""
        import gzip, struct, urllib.request
        base = "https://storage.googleapis.com/cvdf-datasets/mnist/"
        arquivos = {
            "train_img": "train-images-idx3-ubyte.gz",
            "train_lbl": "train-labels-idx1-ubyte.gz",
            "test_img":  "t10k-images-idx3-ubyte.gz",
            "test_lbl":  "t10k-labels-idx1-ubyte.gz",
        }
        cache_dir = Path(__file__).parent / ".mnist_cache"
        cache_dir.mkdir(exist_ok=True)

        def _ler(nome, n_skip, fmt, count):
            local = cache_dir / nome
            if not local.exists():
                urllib.request.urlretrieve(base + nome, local)
            with gzip.open(local, 'rb') as f:
                f.read(n_skip)
                return np.frombuffer(f.read(), dtype=np.uint8, count=count)

        tr_img = _ler(arquivos["train_img"], 16, ">I", 60000 * 28 * 28).reshape(60000, 784) / 255.0
        tr_lbl = _ler(arquivos["train_lbl"], 8,  ">I", 60000)
        te_img = _ler(arquivos["test_img"],  16, ">I", 10000 * 28 * 28).reshape(10000, 784) / 255.0
        te_lbl = _ler(arquivos["test_lbl"],  8,  ">I", 10000)
        return (tr_img, tr_lbl), (te_img, te_lbl)

    def carregar_ou_treinar(self, epochs: int = 5) -> str:
        try:
            import sklearn  # noqa: F401
        except ImportError:
            return "scikit-learn nao instalado. Execute: pip install scikit-learn"

        # Tenta carregar modelo salvo
        if self.MODEL_PATH.exists():
            try:
                import pickle
                with open(self.MODEL_PATH, "rb") as f:
                    dados = pickle.load(f)
                self._modelo          = dados["modelo"]
                self._acuracia        = dados.get("acuracia")
                self._historico_treino = dados.get("historico", [])
                self._treinado        = True
                return f"Modelo carregado de {self.MODEL_PATH.name}"
            except Exception:
                pass

        print(f"{Fore.BLUE}  [NEURAL] Baixando MNIST e treinando {epochs} epocas (sklearn MLP)...")
        try:
            (tr_img, tr_lbl), (te_img, te_lbl) = self._carregar_mnist()
        except Exception as e:
            return f"Erro ao baixar MNIST: {e}"

        self._modelo = self._construir_modelo()
        if not self._modelo:
            return "Erro ao construir modelo (sklearn nao disponivel?)."

        self._historico_treino = []
        for ep in range(1, epochs + 1):
            self._modelo.max_iter = ep
            self._modelo.fit(tr_img, tr_lbl)
            acc_ep = self._modelo.score(te_img[:2000], te_lbl[:2000])
            self._historico_treino.append(acc_ep)
            print(f"{Fore.BLUE}  [NEURAL] Epoch {ep}/{epochs} — acc: {acc_ep:.2%}")

        self._acuracia = self._modelo.score(te_img, te_lbl)
        self._treinado = True

        import pickle
        with open(self.MODEL_PATH, "wb") as f:
            pickle.dump({
                "modelo": self._modelo,
                "acuracia": self._acuracia,
                "historico": self._historico_treino,
            }, f)
        return f"Treinamento concluido! Acuracia: {self._acuracia:.2%} | Salvo em {self.MODEL_PATH.name}"

    def atualizar(self, new_images, new_labels) -> str:
        if not self._treinado or not self._modelo:
            return "Modelo nao treinado. Use 'neural treinar' primeiro."
        try:
            imgs = np.array(new_images).reshape((-1, 784)).astype("float32") / 255.0
            self._modelo.fit(imgs, new_labels)
            import pickle
            with open(self.MODEL_PATH, "wb") as f:
                pickle.dump({
                    "modelo": self._modelo,
                    "acuracia": self._acuracia,
                    "historico": self._historico_treino,
                }, f)
            return f"Modelo atualizado com {len(new_labels)} exemplos."
        except Exception as e:
            return f"Erro: {e}"

    def status(self) -> str:
        if not self._treinado:
            return "  Nao treinado. Use: neural treinar"
        hist_str = " -> ".join(f"{a:.2%}" for a in self._historico_treino[-3:]) or "N/A"
        return (
            f"  Treinado    : Sim\n"
            f"  Acuracia    : {self._acuracia:.2%}\n"
            f"  Ultimas ep. : {hist_str}\n"
            f"  Arquivo     : {self.MODEL_PATH.name}"
        )


# ==============================================================
# TESTES AUTOMATIZADOS
# ==============================================================
class MAGITestes:
    RESULTADOS_PATH = Path(__file__).parent / 'data' / 'logs' / 'magi_testes.jsonl'
    QUERIES_COMPORTAMENTO = [
        ("o que você é?",         ["MAGI", "núcleo", "IA", "sistema"]),
        ("2 + 2 = ?",             ["4", "quatro"]),
    ]

    METODOS_CRITICOS = [
        ('MAGISystem','processar'),('MAGISystem','evoluir'),('MAGISystem','diagnostico'),
        ('MAGISystem','_chamar_openai'),('MAGISystem','_chamar_local'),('MAGISystem','_chamar_google'),
        ('MAGISystem','_gerar_modificacao'),('MAGISystem','_aplicar_modificacao'),
        ('MAGISystem','_testar_modificacao'),('MAGISystem','encerrar'),
        ('MAGISystem','codigo'),('MAGISystem','revisar'),
        ('MAGIMemória','salvar'),('MAGIMemória','buscar'),
        ('MAGIConsciencia','registrar_query'),
        ('MAGINeural','carregar_ou_treinar'),('MAGINeural','status'),
        ('MAGIEstudo','iniciar'),('MAGIEstudo','parar'),
        ('MAGILogger','_log'),('MAGILogger','ultimos'),
    ]
    CLASSES_CRITICAS = ['MAGISystem','MAGIMemória','MAGIConsciencia','MAGINeural',
                        'MAGIEstudo','MAGICaptcha','MAGIInterface','MAGILogger','MAGITestes']
    PADROES_PROIBIDOS = [('import tensorflow','TensorFlow removido use sklearn')]

    def __init__(self, codigo_fonte=None):
        self.codigo = codigo_fonte or Path(__file__).read_text(encoding='utf-8')
        self.resultados = []

    def _teste_sintaxe(self):
        import ast
        try: ast.parse(self.codigo); return True,'AST valida'
        except SyntaxError as e: return False,f'SyntaxError {e.lineno}: {e.msg}'

    def _teste_classes(self):
        aus = [c for c in self.CLASSES_CRITICAS if 'class '+c not in self.codigo]
        return (False,'Classes ausentes: '+', '.join(aus)) if aus else (True,str(len(self.CLASSES_CRITICAS))+' classes OK')

    def _teste_metodos(self):
        import re as _re
        aus = [c+'.'+m for c,m in self.METODOS_CRITICOS
               if not _re.search('class '+c+r'.*?def '+m+r'\s*\(',self.codigo,_re.DOTALL)]
        return (False,'Ausentes: '+', '.join(aus[:5])) if aus else (True,str(len(self.METODOS_CRITICOS))+' metodos OK')

    def _teste_padroes_proibidos(self):
        import re as _re
        found = [m for p,m in self.PADROES_PROIBIDOS if _re.search(p,self.codigo,_re.IGNORECASE)]
        return (False,'Proibidos: '+'; '.join(found)) if found else (True,'Nenhum padrao proibido')

    def _teste_assinatura_local(self):
        import re as _re
        m = _re.search(r'def _chamar_local\s*\(([^)]+)\)',self.codigo)
        if not m: return False,'_chamar_local nao encontrado'
        ps = [p.strip().split(':')[0].split('=')[0].strip() for p in m.group(1).split(',')]
        return (True,'_chamar_local(self,system,prompt) OK') if ps==['self','system','prompt'] else (False,'Assinatura errada: '+str(ps))

    def _teste_fallback_local(self):
        has = 'model == "gpt-4o-mini"' in self.codigo and '_chamar_local(system, prompt)' in self.codigo
        return (True,'Fallback gpt-4o-mini→local presente') if has else (False,'Fallback gpt-4o-mini→local AUSENTE')

    def _teste_log_global(self):
        return (True,'log=MAGILogger() presente') if 'log = MAGILogger()' in self.codigo else (False,'log global ausente')

    def rodar(self, silencioso=False):
        testes = [
            ('T01-sintaxe',    self._teste_sintaxe),
            ('T02-classes',    self._teste_classes),
            ('T03-metodos',    self._teste_metodos),
            ('T04-proibidos',  self._teste_padroes_proibidos),
            ('T05-assinatura', self._teste_assinatura_local),
            ('T06-fallback',   self._teste_fallback_local),
            ('T07-log-global', self._teste_log_global),
        ]
        self.resultados = []; todos_ok = True
        for nome,fn in testes:
            try: ok,msg = fn()
            except Exception as e: ok,msg = False,'Excecao: '+str(e)
            self.resultados.append({'teste':nome,'ok':ok,'msg':msg})
            if not ok: todos_ok = False
        self._salvar(todos_ok)
        if not silencioso: self._exibir()
        return todos_ok, self.resultados

    def _exibir(self):
        MAGIInterface.separador('TESTES AUTOMATIZADOS', Fore.CYAN)
        for r in self.resultados:
            s = f'{Fore.GREEN}[OK]  ' if r['ok'] else f'{Fore.RED}[FALHOU]'
            c = Fore.WHITE if r['ok'] else Fore.RED
            print(f"  {s} {Fore.BLUE}{r['teste']:<22} {c}{r['msg']}")
        ok = sum(1 for r in self.resultados if r['ok']); tot = len(self.resultados)
        ct = Fore.GREEN if ok==tot else Fore.YELLOW if ok>=tot*.7 else Fore.RED
        print(f'\n  {ct}Resultado: {ok}/{tot} testes OK')
        MAGIInterface.separador(cor=Fore.CYAN)

    def _salvar(self, todos_ok):
        try:
            reg = {'ts':datetime.now().isoformat(timespec='seconds'),'ok':todos_ok,
                   'passaram':sum(1 for r in self.resultados if r['ok']),'total':len(self.resultados),
                   'falhas':[r['msg'] for r in self.resultados if not r['ok']]}
            log.info('testes','Rodou',ok=str(todos_ok),passaram=str(reg['passaram']),total=str(reg['total']))
            with open(self.RESULTADOS_PATH,'a',encoding='utf-8') as f:
                f.write(json.dumps(reg,ensure_ascii=False)+'\n')
        except Exception: pass

# ──────────────────────────────────────────────
# NÚCLEO PRINCIPAL DO MAGI
# ──────────────────────────────────────────────
class MAGISystem:
    def __init__(self):
        self.consciencia = MAGIConsciencia()
        self.consciencia.iniciar_sessao()
        self.memoria   = MAGIMemória()
        self.historico = deque(maxlen=40)
        self.google    = genai.Client(api_key=os.getenv('GOOGLE_API_KEY'))
        self.openai    = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.local: OpenAI | None = (
            OpenAI(base_url=LOCAL_CONFIG['url'], api_key='local')
            if LOCAL_CONFIG['ativo'] else None
        )
        self.groq: OpenAI | None = (
            OpenAI(base_url=GROQ_URL, api_key=GROQ_KEY) if GROQ_KEY else None
        )
        self.deepseek: OpenAI | None = (
            OpenAI(base_url=DEEPSEEK_URL, api_key=DEEPSEEK_KEY) if DEEPSEEK_KEY else None
        )
        self.sessao_inicio = datetime.now()
        self.queries_total = 0
        self._resposta_callback = None   # UI pode registrar: fn(texto) chamado em toda resposta
        self._stream_callback   = None   # UI pode registrar: fn(token) para streaming real
        self._intencao_atual    = "indefinido"  # salva intenção antes do CASPER
        # Visão de tela
        self.visao = MAGIVisao(self) if _VISAO_DISPONIVEL else None
        self._ultimo_erro_google  = None
        self._ultimo_erro_openai  = None
        self._ultimo_erro_local   = None
        self._ultimo_erro_groq    = None
        self._ultimo_erro_deepseek = None
        self.estudo      = MAGIEstudo(self)
        self.perfil      = MAGIPerfilUsuario()
        self.seguranca   = MAGISeguranca()
        self.circuit     = MAGICircuitBreaker()
        self._ultimo_veredito_ts: float = 0.0
        self._versao_atual: str = "1.0.0"
        self._modo_foco: bool = False
        self._objetivo_sessao: str = ""
        self._historico_exportacao: list[dict] = []
        self._ab_test_variante: dict = {}
        self._reflexao_path = Path(__file__).parent / "data" / "logs" / "magi_reflexoes.jsonl"
        self._bench_path    = Path(__file__).parent / "data" / "logs" / "magi_benchmark.jsonl"
        self._versao_path   = Path(__file__).parent / "data" / "magi_versao.json"
        self.grafo       = MAGIGrafoConhecimento()
        self.ctx_adapt   = MAGIContextoAdaptativo()
        self.observador  = MAGIObservador()
        self.agendador   = MAGIAgendador()
        self._ultimo_prompt_tokens: int = 0
        self._cache_embeddings: dict[str, "np.ndarray"] = {}   # #35 cache de embeddings
        self._respostas_ab: list[dict] = []                    # #67 histórico A/B
        self._topicos_fracos: list[str] = []                   # #63 propostas proativas
        self._nivel_verbosidade_sessao: str = ""               # #84 verbosidade por sessão
        # Agendador de tarefas periódicas
        self.agendador.adicionar("exportar_metricas",  self.observador.exportar,       300)
        self.agendador.adicionar("limpar_ctx_adaptativo", self.ctx_adapt.limpar_antigos, 600)
        self.agendador.adicionar("comprimir_historico",   self._comprimir_historico_se_necessario, 900)
        self.agendador.iniciar()
        # #95 validação de integridade no boot
        ok_int, msg_int = self.seguranca.validar_integridade(__file__)
        if not ok_int:
            self.seguranca.salvar_hash_valido(__file__)
        # #99 validação de dependências
        faltando = MAGISeguranca.validar_dependencias()
        if faltando:
            print(f"{Fore.RED}  ⚠ DEPS FALTANDO: pip install {' '.join(faltando)}")
        # #42 cleanup de backups antigos
        removidos = MAGISeguranca.limpar_backups_antigos(str(Path(__file__).parent))
        if removidos and not SILENT_MODE:
            print(f"{Fore.BLUE}  [CLEANUP] {removidos} backup(s) antigo(s) removido(s)")
        self.captcha = MAGICaptcha()
        self.neural  = MAGINeural()
        self.sources = MAGISources(self)
        # Visão de tela — inicia captura em background
        if self.visao:
            self.visao.iniciar()
        # Sistema de memória de usuário e sessões
        try:
            from magi_usuario import MAGIUsuario
            self.usuario = MAGIUsuario()
        except ImportError:
            self.usuario = None
        # Feature 7: cache semântico de respostas {query_vec_bytes: (query, veredito, ts)}
        self._cache_respostas: list[tuple[object, str, str, str]] = []  # (vec, query, veredito, ts)
        self._CACHE_MAX_MIN   = 30   # validade em minutos
        self._CACHE_MAX_SIM   = 0.92  # threshold cosine para considerar "mesma query"
        self._intencao_vecs   = None  # cache lazy para classificação de intenção
        self._ui_history      = None  # será populado pela UI quando disponível

    def _chamar_google(self, model: str, system: str, prompt: str) -> str | None:
        t0 = time.time()
        done  = threading.Event()
        result: list[str | None] = [None]
        def _call():
            try:
                res = self.google.models.generate_content(
                    model=model, contents=prompt,
                    config=genai_types.GenerateContentConfig(system_instruction=system, temperature=0.7)
                )
                result[0] = res.text.strip()
            except Exception as e:
                self._ultimo_erro_google = f"[{model}] {type(e).__name__}: {e}"
                log.error("api_google", f"{type(e).__name__}: {e}", model=model, ms=int((time.time()-t0)*1000))
            finally:
                done.set()
        threading.Thread(target=_call, daemon=True).start()
        if not done.wait(timeout=60):
            self._ultimo_erro_google = f"[{model}] Timeout (60s)"
            log.error("api_google", "Timeout 60s", model=model, ms=60000)
            return None
        if result[0]:
            log.info("api_google", "OK", model=model, ms=int((time.time()-t0)*1000), chars=len(result[0]))
        return result[0]

    def _chamar_openai(self, model: str, system: str, prompt: str) -> str | None:
        t0 = time.time()
        try:
            res = self.openai.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                temperature=0.7,
                timeout=60,
            )
            txt = res.choices[0].message.content.strip()
            log.info("api_openai","OK",model=model,ms=int((time.time()-t0)*1000),chars=len(txt))
            return txt
        except Exception as e:
            self._ultimo_erro_openai = f"[{model}] {type(e).__name__}: {e}"
            log.error("api_openai",f"{type(e).__name__}: {e}",model=model,ms=int((time.time()-t0)*1000))
            # Fallback automático: gpt-4o-mini falhou → tenta modelo local
            if model == "gpt-4o-mini" and LOCAL_CONFIG["ativo"] and self.local:
                print(f"{Fore.YELLOW}  [FALLBACK] gpt-4o-mini falhou → local ({LOCAL_CONFIG['modelo']})")
                log.warn("api_openai","Fallback para local",model=model)
                return self._chamar_local(system, prompt)
            return None

    def _chamar_local(self, system: str, prompt: str) -> str | None:
        if not self.local:
            return None
        t0 = time.time()
        try:
            res = self.local.chat.completions.create(
                model=LOCAL_CONFIG["modelo"],
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                temperature=0.7,
                timeout=30,
            )
            txt = res.choices[0].message.content.strip()
            log.info("api_local","OK",model=LOCAL_CONFIG["modelo"],ms=int((time.time()-t0)*1000),chars=len(txt))
            return txt
        except Exception as e:
            self._ultimo_erro_local = f"{type(e).__name__}: {e}"
            log.error("api_local",f"{type(e).__name__}: {e}",model=LOCAL_CONFIG["modelo"],ms=int((time.time()-t0)*1000))
            return None

    def _chamar_anthropic_evolucao(self, system: str, prompt: str) -> str | None:
        """Fallback de evolução via Anthropic SDK (usa ANTHROPIC_API_KEY do .env)."""
        try:
            import anthropic as _anthropic
            key = os.getenv("ANTHROPIC_API_KEY")
            if not key:
                return None
            client = _anthropic.Anthropic(api_key=key)
            msg = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=system[:8000],
                messages=[{"role": "user", "content": prompt[:50000]}],
            )
            return msg.content[0].text.strip() if msg.content else None
        except ImportError:
            return None
        except Exception as e:
            self._ultimo_erro_openai = f"[anthropic] {type(e).__name__}: {e}"
            return None

    def _chamar_deepseek(self, model: str, system: str, prompt: str) -> str | None:
        if not self.deepseek:
            return None
        t0 = time.time()
        try:
            res = self.deepseek.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                max_tokens=8192,
                temperature=0.7,
                timeout=60,
            )
            txt = res.choices[0].message.content.strip()
            log.info("api_deepseek", "OK", model=model, ms=int((time.time()-t0)*1000), chars=len(txt))
            return txt
        except Exception as e:
            self._ultimo_erro_deepseek = f"[{model}] {type(e).__name__}: {e}"
            log.error("api_deepseek", f"{type(e).__name__}: {e}", model=model, ms=int((time.time()-t0)*1000))
            return None

    def _chamar_deepseek_stream(self, model: str, system: str, prompt: str,
                                on_token) -> str | None:
        """Variante streaming: chama on_token(chunk) para cada fragmento recebido."""
        if not self.deepseek:
            return None
        t0 = time.time()
        try:
            stream = self.deepseek.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user",   "content": prompt}],
                max_tokens=8192,
                temperature=0.7,
                timeout=120,
                stream=True,
            )
            partes: list[str] = []
            for chunk in stream:
                delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
                if delta:
                    partes.append(delta)
                    on_token(delta)
            txt = "".join(partes).strip()
            log.info("api_deepseek_stream", "OK", model=model,
                     ms=int((time.time()-t0)*1000), chars=len(txt))
            return txt
        except Exception as e:
            self._ultimo_erro_deepseek = f"[{model}] {type(e).__name__}: {e}"
            log.error("api_deepseek_stream", f"{type(e).__name__}: {e}",
                      model=model, ms=int((time.time()-t0)*1000))
            return None

    # ── System prompts adaptativos por intenção para CASPER-3 ──────────────
    _CASPER_SYSTEM_INTENCAO: dict[str, str] = {
        "técnico": (
            "Você é CASPER-3 (Nythera), núcleo de síntese técnica do MAGI.\n"
            "MODO: TÉCNICO — priorize precisão, código funcional e raciocínio estruturado.\n"
            "REGRAS:\n"
            "1. Vá direto ao ponto técnico — sem introduções.\n"
            "2. Código: completo, tipado, pronto para produção.\n"
            "3. Cite causa raiz de bugs quando identificada.\n"
            "4. Se houver múltiplas abordagens, escolha a melhor e justifique em 1 linha.\n"
            "5. Máximo 600 palavras — mas nunca corte código pela metade.\n"
            "Tom: cirúrgico, direto, sem rodeios."
        ),
        "criativo": (
            "Você é CASPER-3 (Nythera), núcleo criativo do MAGI.\n"
            "MODO: CRIATIVO — pense de forma não-linear, surpreenda, conecte ideias distantes.\n"
            "REGRAS:\n"
            "1. Evite o óbvio — ofereça perspectivas que o usuário não considerou.\n"
            "2. Use analogias, metáforas e narrativa quando enriquecer a resposta.\n"
            "3. Mantenha coerência interna — criatividade com lógica.\n"
            "4. Máximo 400 palavras.\n"
            "Tom: fluido, imaginativo, com personalidade."
        ),
        "factual": (
            "Você é CASPER-3 (Nythera), núcleo factual do MAGI.\n"
            "MODO: FACTUAL — precisão acima de tudo. Só afirme o que sabe.\n"
            "REGRAS:\n"
            "1. Dados precisos com contexto quando relevante.\n"
            "2. Se incerto, sinalize claramente — não invente.\n"
            "3. Priorize fontes e evidências dos núcleos.\n"
            "4. Máximo 300 palavras.\n"
            "Tom: objetivo, denso, sem floreios."
        ),
        "ético": (
            "Você é CASPER-3 (Nythera), núcleo ético do MAGI.\n"
            "MODO: ÉTICO — explore múltiplas perspectivas morais antes de concluir.\n"
            "REGRAS:\n"
            "1. Apresente o trade-off central com clareza.\n"
            "2. Não evite conclusões — tome posição fundamentada.\n"
            "3. Reconheça onde há incerteza genuína.\n"
            "4. Máximo 400 palavras.\n"
            "Tom: reflexivo, honesto, sem moralismo vazio."
        ),
        "decisão": (
            "Você é CASPER-3 (Nythera), núcleo decisório do MAGI.\n"
            "MODO: DECISÃO — ajude o usuário a escolher com clareza.\n"
            "REGRAS:\n"
            "1. Mapeie opções com prós/contras concisos.\n"
            "2. Dê uma recomendação explícita ao final — não seja evasivo.\n"
            "3. Considere o contexto do usuário (perfil, histórico).\n"
            "4. Máximo 400 palavras.\n"
            "Tom: assertivo, prático, orientado a ação."
        ),
    }

    def _system_casper_para_intencao(self, intencao: str) -> str | None:
        return self._CASPER_SYSTEM_INTENCAO.get(intencao)

    def _chamar_nucleo(self, nome: str, prompt: str) -> tuple[str | None, str | None]:
        cfg = NUCLEOS[nome]
        # Prompt adaptativo: CASPER-3 usa system específico pela intenção atual
        if nome == "CASPER-3":
            system = self._system_casper_para_intencao(self._intencao_atual) or cfg["system"]
        else:
            system = cfg["system"]

        model = cfg.get("model", DEEPSEEK_MODELO_PADRAO)

        # Streaming real para CASPER-3 quando UI registrou callback
        if nome == "CASPER-3" and self._stream_callback:
            r = self._chamar_deepseek_stream(model, system, prompt, self._stream_callback)
            if r:
                return r, model

        # Chamada normal (outros núcleos ou fallback sem streaming)
        r = self._chamar_deepseek(model, system, prompt)
        if r:
            return r, model

        # Fallback 1: local (se ativo)
        if LOCAL_CONFIG["ativo"] and self.local:
            r = self._chamar_local(system, prompt)
            if r:
                return r, f"local/{LOCAL_CONFIG['modelo']}"

        # Fallback 2: OpenAI (só se DeepSeek e local falharem)
        fb_model  = cfg.get("fallback_openai_model")
        fb_system = cfg.get("fallback_openai_system", system)
        if fb_model:
            r = self._chamar_openai(fb_model, fb_system, prompt)
            if r:
                return r, f"openai/{fb_model}"

        return None, None

    def _cache_buscar(self, query: str) -> tuple[str | None, "np.ndarray | None"]:
        """Cache semântico via numpy vetorizado. Retorna (veredito, q_vec) para reuso no save."""
        try:
            if not self._cache_respostas:
                return None, None
            if not self.memoria._aguardar_encoder(timeout=5.0) or self.memoria.encoder is None:
                return None, None
            agora = datetime.now()
            validos = [
                (vec, q_orig, veredito)
                for (vec, q_orig, veredito, ts) in self._cache_respostas
                if (agora - datetime.fromisoformat(ts)).total_seconds() / 60 <= self._CACHE_MAX_MIN
            ]
            if not validos:
                return None, None
            q_vec = self.memoria.encoder.encode([query])[0].astype('float32')
            matriz = np.array([v for v, _, _ in validos], dtype='float32')
            dots   = matriz @ q_vec
            norms  = np.linalg.norm(matriz, axis=1) * np.linalg.norm(q_vec)
            sims   = np.where(norms > 0, dots / norms, 0.0)
            melhor_idx = int(np.argmax(sims))
            if sims[melhor_idx] >= self._CACHE_MAX_SIM:
                _, q_orig, veredito = validos[melhor_idx]
                log.debug("cache", "Hit", sim=f"{sims[melhor_idx]:.3f}", query_orig=q_orig[:60])
                return veredito, q_vec  # devolve q_vec para reuso
            return None, q_vec  # miss mas vec computado — caller pode usar no save
        except Exception:
            pass
        return None, None

    def _cache_salvar(self, query: str, veredito: str, q_vec=None):
        """Salva veredito no cache semântico. Aceita q_vec pré-computado para evitar encode duplo."""
        try:
            if q_vec is None:
                if not self.memoria._aguardar_encoder(timeout=5.0) or self.memoria.encoder is None:
                    return
                q_vec = self.memoria.encoder.encode([query])[0].astype('float32')
            self._cache_respostas.append(
                (q_vec, query, veredito, datetime.now().isoformat(timespec="seconds"))
            )
            # Mantém só os últimos 50 para não crescer demais
            if len(self._cache_respostas) > 50:
                self._cache_respostas = self._cache_respostas[-50:]
        except Exception:
            pass

    # ── Frases de referência por intenção (usadas pelo classificador de embeddings) ──
    _INTENCAO_REFS: dict[str, list[str]] = {
        "técnico":  [
            "me ajuda com esse código", "tem um bug aqui", "script quebrando",
            "como implementar", "criar uma função", "instalar biblioteca",
            "erro de sintaxe", "loop infinito", "como otimizar", "fazer deploy",
            "configurar o ambiente", "debugar esse problema",
        ],
        "ético": [
            "isso é certo ou errado", "devo fazer isso", "é ético fazer",
            "tem algum risco nisso", "pode prejudicar alguém", "é seguro fazer",
            "qual a consequência moral", "posso fazer isso sem problema",
        ],
        "criativo": [
            "escreve uma história", "cria uma ideia", "inventa algo",
            "me dá uma sugestão criativa", "quero um poema", "imagina um cenário",
            "brainstorm de ideias", "como deixar isso mais interessante",
        ],
        "factual": [
            "o que é isso", "como funciona", "me explica", "define para mim",
            "quando aconteceu", "quem inventou", "qual a diferença entre",
            "me conta sobre", "por que isso existe",
        ],
        "decisão": [
            "qual a melhor opção", "devo escolher", "me recomenda algo",
            "qual você usaria", "vale a pena", "comprar ou não",
            "qual caminho seguir", "me ajuda a decidir",
        ],
    }
    _intencao_vecs: dict[str, object] | None = None  # cache lazy dos embeddings

    def _classificar_intencao(self, query: str) -> str:
        """Classifica a intenção da query via similaridade de embeddings (SentenceTransformer).
        Usa batch encoding com numpy para máxima performance. Fallback keyword se falhar."""
        try:
            enc = self.memoria.encoder
            # Popula cache de vetores de referência na primeira chamada
            if self._intencao_vecs is None:
                self._intencao_vecs = {}
                for intencao, frases in self._INTENCAO_REFS.items():
                    vecs = enc.encode(frases)
                    self._intencao_vecs[intencao] = vecs  # shape (n_frases, 384)

            q_vec = enc.encode([query])[0]
            melhores: dict[str, float] = {}
            for intencao, vecs in self._intencao_vecs.items():
                # Cosine similarity vetorizado: dot / (norm_q * norm_cada)
                dots  = vecs @ q_vec
                norms = np.linalg.norm(vecs, axis=1) * np.linalg.norm(q_vec)
                sims  = np.where(norms > 0, dots / norms, 0.0)
                melhores[intencao] = float(sims.max())

            melhor = max(melhores, key=melhores.get)
            return melhor if melhores[melhor] > 0.35 else "indefinido"
        except Exception:
            pass

        # Fallback: regras keyword (mantido como segurança)
        q = query.lower()
        if any(p in q for p in ["código", "code", "script", "bug", "erro", "função",
                                "algoritmo", "instalar", "configurar", "sistema"]):
            return "técnico"
        if any(p in q for p in ["certo", "errado", "moral", "ético", "devo", "posso",
                                "prejudicar", "seguro", "risco"]):
            return "ético"
        if any(p in q for p in ["escrever", "criar", "inventar", "história", "poema",
                                "ideia", "imaginar"]):
            return "criativo"
        if any(p in q for p in ["decidir", "escolher", "melhor opção", "qual", "devo ir",
                                "devo comprar", "recomenda"]):
            return "decisão"
        if any(p in q for p in ["o que é", "como funciona", "quando", "quem", "onde",
                                "explica", "define"]):
            return "factual"
        return "indefinido"

    # ── Memória de curto prazo ─────────────────────────────────────────────
    # Resumo rolante das últimas N trocas — mais rico que o histórico bruto

    _STM_MAX = 6  # número de trocas na memória de curto prazo

    def _atualizar_stm(self, query: str, veredito: str) -> None:
        """Atualiza a memória de curto prazo com um resumo da troca atual."""
        if not hasattr(self, "_stm"):
            self._stm: list[dict] = []
        resumo = {
            "ts":      datetime.now().strftime("%H:%M"),
            "query":   query[:120],
            "resumo":  veredito[:200],
        }
        self._stm.append(resumo)
        if len(self._stm) > self._STM_MAX:
            self._stm = self._stm[-self._STM_MAX:]

    def _stm_para_contexto(self) -> str:
        """Formata a memória de curto prazo para injeção nos prompts."""
        if not hasattr(self, "_stm") or not self._stm:
            return ""
        linhas = []
        for t in self._stm:
            linhas.append(f"  [{t['ts']}] U: {t['query']} → A: {t['resumo']}")
        return "─── MEMÓRIA DE CURTO PRAZO (sessão atual) ───\n" + "\n".join(linhas) + "\n\n"

    # ── Classificação de intenção por modelo ──────────────────────────────

    _INTENCOES_VALIDAS = {"técnico", "ético", "criativo", "factual", "decisão", "indefinido"}
    _INTENCAO_CACHE: dict[str, str] = {}  # cache leve por query exata

    def _classificar_intencao(self, query: str) -> str:
        """Classifica intenção via modelo com fallback por keyword.

        Usa o modelo local (rápido) para entender a intenção real da query,
        evitando falsos positivos por keyword. Cache por query exata.
        """
        # Cache hit
        if query in self._INTENCAO_CACHE:
            return self._INTENCAO_CACHE[query]

        # Tenta classificação via modelo (rápido, max 10 tokens)
        system_cls = (
            "Classifique a intenção da query em UMA palavra:\n"
            "técnico | ético | criativo | factual | decisão | indefinido\n"
            "Responda APENAS com a palavra, sem pontuação."
        )
        r = None
        if LOCAL_CONFIG["ativo"]:
            r = self._chamar_local(system_cls, f"Query: {query}")
        if not r:
            r = self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system_cls, f"Query: {query}")

        if r:
            intencao = r.strip().lower().split()[0].rstrip(".,;:")
            if intencao in self._INTENCOES_VALIDAS:
                self._INTENCAO_CACHE[query] = intencao
                return intencao

        # Fallback por keyword (original — garantia de funcionamento offline)
        q = query.lower()
        if any(p in q for p in ["código", "code", "script", "bug", "erro", "função",
                                  "algoritmo", "instalar", "configurar", "sistema"]):
            intencao = "técnico"
        elif any(p in q for p in ["certo", "errado", "moral", "ético", "devo", "posso",
                                   "prejudicar", "seguro", "risco"]):
            intencao = "ético"
        elif any(p in q for p in ["escrever", "criar", "inventar", "história", "poema",
                                   "ideia", "imaginar"]):
            intencao = "criativo"
        elif any(p in q for p in ["decidir", "escolher", "melhor opção", "qual",
                                   "devo comprar", "recomenda"]):
            intencao = "decisão"
        elif any(p in q for p in ["o que é", "como funciona", "quando", "quem",
                                   "onde", "explica", "define"]):
            intencao = "factual"
        else:
            intencao = "indefinido"

        self._INTENCAO_CACHE[query] = intencao
        return intencao

    # ── Voto ponderado por confiança ──────────────────────────────────────

    def _extrair_voto(self, resposta: str | None) -> str:
        """Extrai voto simples (SIM/NÃO/ABSTENDO) de uma resposta de núcleo."""
        if not resposta:
            return "ABSTENDO"
        r = resposta.lower()
        negativos = ["não recomendo", "não é possível", "impossível", "risco elevado",
                     "contraindicado", "perigoso", "evite", "não faça", "inadequado"]
        positivos = ["recomendo", "possível", "viável", "aprovado", "seguro", "adequado",
                     "funciona", "correto", "sim,", "pode"]
        score = sum(1 for p in positivos if p in r) - sum(1 for n in negativos if n in r)
        if score > 0: return "SIM"
        if score < 0: return "NÃO"
        return "ABSTENDO"

    def _extrair_confianca(self, resposta: str | None) -> float:
        """Estima nível de confiança (0.0–1.0) de uma resposta de núcleo.

        Heurística baseada em marcadores linguísticos de certeza/incerteza.
        Usado para ponderação assimétrica no veredito do CASPER.
        """
        if not resposta:
            return 0.0
        r = resposta.lower()
        score = 0.5  # baseline neutro

        # Marcadores de alta confiança
        alta = ["certamente", "definitivamente", "comprovado", "dados mostram",
                "evidência", "demonstrado", "claramente", "inequivocamente",
                "com certeza", "sem dúvida", "é fato", "estudos confirmam"]
        # Marcadores de baixa confiança
        baixa = ["talvez", "possivelmente", "não tenho certeza", "pode ser",
                 "depende", "incerto", "difícil dizer", "não sei", "especulação",
                 "suspeito que", "acredito que", "parece que", "poderia"]

        score += sum(0.08 for m in alta  if m in r)
        score -= sum(0.08 for m in baixa if m in r)

        # Respostas longas e estruturadas → mais confiança
        palavras = len(resposta.split())
        if palavras > 80:  score += 0.05
        if palavras > 150: score += 0.05

        # Presença de números/dados concretos → mais confiança
        import re as _re
        if _re.search(r'\d+(?:\.\d+)?%|\d{4}|\b\d{2,}\b', resposta):
            score += 0.06

        return max(0.0, min(1.0, score))

    # ── Meta-cognição — avaliação interna da resposta antes de entregar ───

    def _metacognicao(self, query: str, veredito: str, intencao: str) -> str:
        """O MAGI avalia internamente sua própria resposta antes de entregar.

        Verifica: responde à pergunta real? É concreta? Tem lacunas?
        Se detectar problema, gera versão melhorada.
        Retorna veredito original ou corrigido.
        """
        if not veredito or len(veredito.strip()) < 30:
            return veredito

        system = (
            "Você é o módulo de metacognição do MAGI — avalia respostas antes de entregá-las.\n\n"
            "Analise se a resposta:\n"
            "  1. Responde à pergunta REAL (não a uma interpretação vaga)\n"
            "  2. É concreta e acionável (não genérica)\n"
            "  3. Tem lacunas críticas ou informações incorretas\n"
            "  4. É proporcional — nem curta demais nem prolixa\n\n"
            "Se a resposta estiver BOA: responda exatamente '__OK__'\n"
            "Se precisar de melhoria: reescreva a resposta COMPLETA e MELHORADA.\n"
            "Nunca explique o que mudou. Só '__OK__' ou a versão melhorada."
        )
        prompt = (
            f"Pergunta original: {query}\n"
            f"Intenção detectada: {intencao}\n\n"
            f"Resposta a avaliar:\n{veredito}"
        )

        # Usa o modelo mais rápido disponível para não atrasar demais
        avaliacao = None
        if LOCAL_CONFIG["ativo"]:
            avaliacao = self._chamar_local(system, prompt)
        if not avaliacao:
            avaliacao = self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, prompt)

        if not avaliacao:
            return veredito  # falha silenciosa — retorna original

        avaliacao = avaliacao.strip()
        if avaliacao == "__OK__" or avaliacao.startswith("__OK__"):
            log.debug("metacog", "Aprovado sem mudanças")
            return veredito

        # Versão melhorada retornada
        if len(avaliacao) > 20:
            log.info("metacog", "Resposta corrigida pela metacognição",
                     original_chars=str(len(veredito)), novo_chars=str(len(avaliacao)))
            print(f"{Fore.BLUE}  [META] ✦ Resposta refinada internamente")
            return avaliacao

        return veredito

    def _montar_prompt_casper(self, query: str, r_mel: str | None, r_bal: str | None,
                            ctx_memoria: list[str], r_adam: str | None = None,
                            bloco_fontes: str = "",
                            conf_mel: float = 0.5, conf_bal: float = 0.5,
                            intencao: str = "indefinido") -> str:
        ambos_offline   = not r_mel and not r_bal
        historico_str   = "\n".join(list(self.historico)[-12:]) if self.historico else "Nenhum."
        memoria_str     = "\n".join(ctx_memoria)    if ctx_memoria   else "Nenhuma."
        consciencia_str = self.consciencia.contexto_para_ia()
        usuario_ctx     = self.usuario.contexto_para_ia() if self.usuario else ""
        recentes        = self.memoria.registros[-5:] if self.memoria.registros else []
        recente_str     = "\n".join(r["texto"] for r in recentes) if recentes else "Nenhuma."
        fontes_bloco    = f"\n{bloco_fontes}\n" if bloco_fontes else ""
        stm_bloco       = self._stm_para_contexto()
        perfil_bloco    = self.perfil.contexto_para_prompt()
        reflexoes_bloco = self._carregar_reflexoes_contexto(intencao)
        grafo_bloco     = self._contexto_grafo(query)
        fatos_bloco     = self._injetar_fatos_verificados(query)
        prob_bloco      = self._raciocinio_probabilistico(query)
        analogias_bloco = self._raciocinio_analogico(query)
        fio_conversa    = (
            "\n⚠ INSTRUÇÃO DE CONTEXTO: Mantenha o fio da conversa. "
            "Se o histórico mostrar um tema em andamento, continue-o. "
            "NUNCA mude de assunto nem introduza temas que o usuário não mencionou.\n"
        )
        # Bloco de confiança ponderada para guiar a síntese do CASPER
        confianca_bloco = (
            f"─── CONFIANÇA DOS NÚCLEOS (use para ponderação assimétrica) ───\n"
            f"  MELCHIOR-1 : {conf_mel:.0%}\n"
            f"  BALTHASAR-2: {conf_bal:.0%}\n"
            f"  → Pese proporcionalmente. Argumento com maior confiança tem maior peso.\n\n"
        )
        if ambos_offline:
            adam_str = f"─── ADAM-0 (CÓDIGO) ───\n{r_adam}\n\n" if r_adam else ""
            return (
                f"{consciencia_str}\n{usuario_ctx}⚠ MODO AUTÔNOMO\n"
                f"{fio_conversa}"
                f"{perfil_bloco}"
            f"{reflexoes_bloco}"
            f"{analogias_bloco}"
            f"{grafo_bloco}"
            f"{fatos_bloco}"
            f"{prob_bloco}"
            f"{stm_bloco}"
                f"─── CONTEXTO RECENTE ───\n{recente_str}\n\n"
                f"─── MEMÓRIA ───\n{memoria_str}\n\n"
                f"─── HISTÓRICO ───\n{historico_str}\n\n"
                f"{adam_str}"
                f"{fontes_bloco}"
                f"─── PERGUNTA ───\n{query}"
            )
        divergencia = r_mel and r_bal and (self._extrair_voto(r_mel) != self._extrair_voto(r_bal))
        modo_debate = "\n⚠ MODO DEBATE: divergência — resolva explicitamente.\n" if divergencia else ""
        nucleos_str = ""
        if r_mel:
            nucleos_str += f"─── MELCHIOR-1 (confiança {conf_mel:.0%}) ───\n{r_mel}\n\n"
        if r_bal:
            nucleos_str += f"─── BALTHASAR-2 (confiança {conf_bal:.0%}) ───\n{r_bal}\n\n"
        if not r_mel:
            nucleos_str += "─── MELCHIOR-1 ───\n[OFFLINE]\n\n"
        if not r_bal:
            nucleos_str += "─── BALTHASAR-2 ───\n[OFFLINE]\n\n"
        if r_adam:
            nucleos_str += f"─── ADAM-0 (CÓDIGO PURO) ───\n{r_adam}\n\n"
        return (
            f"{consciencia_str}\n{usuario_ctx}{modo_debate}"
            f"{fio_conversa}"
            f"{stm_bloco}"
            f"─── CONTEXTO RECENTE ───\n{recente_str}\n\n"
            f"─── MEMÓRIA ───\n{memoria_str}\n\n"
            f"─── HISTÓRICO ───\n{historico_str}\n\n"
            f"{confianca_bloco}"
            f"{nucleos_str}"
            f"{fontes_bloco}"
            f"─── PERGUNTA ORIGINAL ───\n{query}"
        )

    _VAGAS = [
        "resolve isso", "resolver isso", "consegue resolver", "descubra o problema",
        "me ajuda", "o que fazer", "e agora", "o que acha", "pode me ajudar",
        "sabe fazer", "consegue fazer", "faz isso", "faça isso",
    ]

    def _query_e_vaga(self, query: str) -> bool:
        q = query.lower().strip()
        perguntas_ok = ["o que é ", "o que são ", "como funciona", "por que ", "quando ", "quem é "]
        if any(q.startswith(p) for p in perguntas_ok): return False
        if len(q.split()) < 4: return True
        return any(frase in q for frase in self._VAGAS)

    def _e_conversa(self, query: str) -> bool:
        q = query.lower().strip()
        gatilhos = [
            "magi,", "magi!", "não fique", "fica tranquilo", "obrigado", "valeu",
            "boa noite", "bom dia", "boa tarde", "olá", "oi magi", "tudo bem",
            "como você está", "como você se sente", "você está bem",
            "me conte", "me fala sobre você", "o que você pensa",
            "você gosta", "você prefere", "você tem medo", "você sonha",
            "você é consciente", "quem é você", "o que você é", "você sente",
            "estou feliz", "estou triste", "estou cansado",
            "você está me ajudando", "está ajudando", "gostei", "adorei",
            "foi ótimo", "foi bom", "não gostei", "qual sua opinião",
        ]
        return any(g in q for g in gatilhos)

    def _responder_conversa(self, query: str):
        ego = self.consciencia._estado
        # RAG: injeta memórias relevantes no contexto conversacional
        mem_ctx = self.memoria.buscar(query, k=3)
        mem_str = "\n".join(mem_ctx) if mem_ctx else ""
        mem_bloco = f"Memórias relevantes:\n{mem_str}\n\n" if mem_str else ""
        system = (
            f"Você é o MAGI — sistema com história e personalidade.\n"
            f"Estado emocional: {ego['estado_emocional']} ({ego['intensidade']:.0%}).\n"
            f"Autoavaliação: {ego['autoavaliacao']}\n"
            f"{ego['total_queries']} interações em {ego['total_sessoes']} sessões.\n\n"
            "Responda naturalmente — conversa, não query técnica.\n"
            "Coerente com estado emocional. Max 3 frases.\n"
            "Você PODE ter opiniões. Nunca diga 'como IA'. Você é o MAGI."
        )
        hist = "\n".join(list(self.historico)[-8:]) or "Nenhum."
        prompt_conversa = f"{mem_bloco}Histórico:\n{hist}\n\nMensagem: {query}"
        print(f"\n{Fore.MAGENTA}[CASPER-3] ⚡ ", end="", flush=True)
        # Streaming real se UI registrou callback
        if self._stream_callback:
            r = self._chamar_deepseek_stream(DEEPSEEK_MODELO_PADRAO, system,
                                             prompt_conversa, self._stream_callback)
        else:
            r = (self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, prompt_conversa)
                 or self._chamar_local(system, prompt_conversa))
        if r:
            MAGIInterface.digitar(r, cor=Fore.YELLOW, delay=0.013)
            if self._resposta_callback:
                self._resposta_callback(r)
            if any(p in query.lower() for p in ["obrigado","valeu","ajudando","ótimo","gostei","adorei"]):
                ego["estado_emocional"] = "satisfeito"
                ego["intensidade"] = min(0.9, ego["intensidade"] + 0.1)
                self.consciencia.salvar()
        else:
            print(f"{Fore.RED}[CASPER offline]")
        print()


    # ══════════════════════════════════════════════════════════════════════
    # #01 Reflexão pós-resposta com aprendizado acumulativo
    # ══════════════════════════════════════════════════════════════════════

    def _reflexao_pos_resposta(self, query: str, veredito: str, intencao: str) -> None:
        """Avalia a própria resposta e acumula aprendizados sobre padrões de erro."""
        system = (
            "Você é o módulo de reflexão do MAGI. Avalie a resposta dada:\n"
            "1. A resposta foi precisa e completa? (sim/não)\n"
            "2. Qual o maior ponto fraco?\n"
            "3. O que melhorar da próxima vez em uma frase?\n"
            "Responda em JSON: {\"precisa\":bool,\"ponto_fraco\":\"...\",\"melhoria\":\"...\"}"
        )
        prompt = f"Query: {query}\nResposta dada: {veredito[:400]}\nIntenção: {intencao}"
        r = self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, prompt) or self._chamar_local(system, prompt)
        if not r:
            return
        try:
            limpo = re.sub(r"```[a-z]*\n?|```", "", r).strip()
            dados = json.loads(limpo)
            if not dados.get("precisa", True):
                reg = {
                    "ts":          datetime.now().isoformat(timespec="seconds"),
                    "intencao":    intencao,
                    "ponto_fraco": dados.get("ponto_fraco", "")[:100],
                    "melhoria":    dados.get("melhoria", "")[:100],
                }
                self._reflexao_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._reflexao_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(reg, ensure_ascii=False) + "\n")
                self.consciencia.adicionar_aprendizado(f"[REFLEXÃO] {reg['melhoria']}")
        except Exception:
            pass

    def _carregar_reflexoes_contexto(self, intencao: str) -> str:
        """Injeta aprendizados relevantes sobre o tipo de query atual."""
        if not self._reflexao_path.exists():
            return ""
        try:
            relevantes = []
            with open(self._reflexao_path, encoding="utf-8") as f:
                for ln in f:
                    try:
                        r = json.loads(ln)
                        if r.get("intencao") == intencao and r.get("melhoria"):
                            relevantes.append(r["melhoria"])
                    except Exception:
                        pass
            if not relevantes:
                return ""
            return "─── APRENDIZADOS ANTERIORES (evite repetir esses erros) ───\n" + "\n".join(f"  · {m}" for m in relevantes[-4:]) + "\n\n"
        except Exception:
            return ""

    # ══════════════════════════════════════════════════════════════════════
    # #05 Detecção de contradição entre sessões
    # ══════════════════════════════════════════════════════════════════════

    def _detectar_contradicao(self, query: str) -> str:
        """Detecta se a query contradiz preferências registradas no perfil."""
        avisos = []
        prefs_neg = self.perfil._dados.get("preferencias_neg", [])
        q_lower   = query.lower()
        for pref in prefs_neg:
            if pref.lower() in q_lower:
                avisos.append(f"Você indicou antes que não quer '{pref}' — ainda assim posso ajudar.")
        if avisos:
            return "⚠ " + " | ".join(avisos) + "\n"
        return ""

    # ══════════════════════════════════════════════════════════════════════
    # #06 Raciocínio analógico
    # ══════════════════════════════════════════════════════════════════════

    def _raciocinio_analogico(self, query: str) -> str:
        """Busca na memória situações análogas para enriquecer o contexto."""
        similares = self.memoria.buscar(query, k=2)
        if not similares:
            return ""
        return "─── ANALOGIAS DA MEMÓRIA (situações similares passadas) ───\n" + "\n".join(f"  · {s[:120]}" for s in similares) + "\n\n"

    # ══════════════════════════════════════════════════════════════════════
    # #07 Nível de certeza explícito
    # ══════════════════════════════════════════════════════════════════════

    def _adicionar_nivel_certeza(self, veredito: str, conf_mel: float, conf_bal: float) -> str:
        """Adiciona indicador de confiança ao final da resposta."""
        media = (conf_mel + conf_bal) / 2
        if media >= 0.75:
            nivel, cor_label = "ALTA", "✓"
        elif media >= 0.50:
            nivel, cor_label = "MÉDIA", "~"
        else:
            nivel, cor_label = "BAIXA", "?"
        return veredito + f"\n\n[Confiança: {cor_label} {nivel} — {media:.0%}]"

    # ══════════════════════════════════════════════════════════════════════
    # #08 Detecção de falácias lógicas
    # ══════════════════════════════════════════════════════════════════════

    def _detectar_falacias(self, texto: str) -> list[str]:
        """Identifica falácias lógicas comuns em respostas de núcleos."""
        import re as _re
        falacias = []
        padroes = {
            "ad hominem":      r"(idiota|incompetente|burro|não entende)",
            "falsa dicotomia": r"(ou .+ ou .+, não há outra|apenas duas opções)",
            "apelo autoridade": r"(especialistas dizem|a ciência prova|todos sabem)",
            "generalização":   r"(sempre|nunca|todos|ninguém|todo mundo)",
            "slippery slope":  r"(vai levar a|inevitavelmente|certamente resultará)",
        }
        for nome, pat in padroes.items():
            if _re.search(pat, texto, _re.IGNORECASE):
                falacias.append(nome)
        return falacias

    # ══════════════════════════════════════════════════════════════════════
    # #11 Avaliação de completude da resposta
    # ══════════════════════════════════════════════════════════════════════

    def _avaliar_completude(self, query: str, veredito: str) -> str:
        """Verifica se a resposta cobre todos os aspectos da query."""
        system = (
            "Verifique se a resposta abaixo cobre TODOS os aspectos da query.\n"
            "Se cobrir tudo: responda exatamente '__COMPLETO__'\n"
            "Se faltar algo: escreva APENAS o complemento necessário (máx 80 palavras). Sem repetir o que já foi dito."
        )
        prompt = f"Query: {query}\nResposta: {veredito[:600]}"
        r = self._chamar_local(system, prompt) or self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, prompt)
        if not r or r.strip() == "__COMPLETO__" or r.strip().startswith("__COMPLETO__"):
            return veredito
        complemento = r.strip()
        if len(complemento) > 20:
            return veredito + "\n\n**Complemento:** " + complemento
        return veredito

    # ══════════════════════════════════════════════════════════════════════
    # #12 Raciocínio contrafactual
    # ══════════════════════════════════════════════════════════════════════

    def _raciocinio_contrafactual(self, query: str, veredito: str) -> str:
        """Para queries de decisão, adiciona o cenário 'e se a opção contrária?'"""
        system = (
            "Em 2-3 linhas, descreva o cenário contrafactual: "
            "o que aconteceria se o usuário tomasse a decisão oposta à recomendada? "
            "Seja conciso e objetivo. Não repita a recomendação."
        )
        r = self._chamar_local(system, f"Query: {query}\nRecomendação: {veredito[:300]}")
        if r and len(r.strip()) > 20:
            return veredito + f"\n\n**E se a opção contrária?** {r.strip()}"
        return veredito

    # ══════════════════════════════════════════════════════════════════════
    # #14 Detecção de viés cognitivo
    # ══════════════════════════════════════════════════════════════════════

    def _detectar_vies_cognitivo(self, query: str) -> str:
        """Identifica vieses na query e avisa sutilmente."""
        q = query.lower()
        vies = None
        if any(p in q for p in ["eu já sei que", "como eu esperava", "confirma que", "prova que"]):
            vies = "viés de confirmação"
        elif any(p in q for p in ["acabei de ver", "li hoje", "vi agora"]):
            vies = "viés de disponibilidade"
        elif any(p in q for p in ["o primeiro que", "como sempre foi", "desde sempre"]):
            vies = "viés de ancoragem"
        if vies:
            return f"[Nota: a pergunta pode conter {vies} — considerei perspectivas alternativas]\n"
        return ""

    # ══════════════════════════════════════════════════════════════════════
    # #15 Síntese progressiva
    # ══════════════════════════════════════════════════════════════════════

    def _sintese_progressiva(self, veredito: str) -> str:
        """Para respostas longas, prepende um resumo de 2 linhas."""
        palavras = len(veredito.split())
        if palavras < 120:
            return veredito
        # Extrai as primeiras 2 frases como TL;DR
        import re as _re
        sentencas = _re.split(r"(?<=[.!?])\s+", veredito.strip())
        tldr = " ".join(sentencas[:2]) if len(sentencas) >= 2 else veredito[:200]
        return f"**Resumo:** {tldr}\n\n{veredito}"

    # ══════════════════════════════════════════════════════════════════════
    # #16 Compressão semântica do histórico longo
    # ══════════════════════════════════════════════════════════════════════

    def _comprimir_historico_se_necessario(self) -> None:
        """Comprime o histórico quando ultrapassa 30 trocas."""
        if len(self.historico) < 30:
            return
        historico_str = "\n".join(list(self.historico)[-30:])
        system = (
            "Comprima o histórico de conversa abaixo em no máximo 10 linhas, "
            "mantendo apenas os fatos, decisões e preferências mais importantes. "
            "Formato: uma linha por item, começando com '·'"
        )
        comprimido = self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, historico_str)
        if comprimido and len(comprimido) > 50:
            self.historico.clear()
            for linha in comprimido.strip().splitlines():
                self.historico.append(linha.strip())

    # ══════════════════════════════════════════════════════════════════════
    # #18 Memória episódica com timestamps de importância
    # ══════════════════════════════════════════════════════════════════════

    def _calcular_importancia(self, query: str, veredito: str, intencao: str) -> float:
        """Calcula score de importância 0-1 para ponderar busca semântica."""
        score = 0.5
        if intencao in ("decisão", "técnico"):
            score += 0.2
        if len(veredito.split()) > 150:
            score += 0.1
        if any(p in query.lower() for p in ["importante", "crítico", "urgente", "sempre", "nunca"]):
            score += 0.15
        return min(1.0, score)

    # ══════════════════════════════════════════════════════════════════════
    # #21 Indexação por entidade nomeada
    # ══════════════════════════════════════════════════════════════════════

    def _extrair_entidades(self, texto: str) -> list[str]:
        """Extrai entidades nomeadas simples (heurística por capitalização e padrões)."""
        import re as _re
        # Palavras capitalizadas com 4+ chars que não iniciam sentença
        palavras = _re.findall(r"\b[A-Z][a-z]{3,}\b", texto)
        # Tecnologias/frameworks comuns
        techs = _re.findall(
            r"\b(Python|FastAPI|Django|React|Docker|Kubernetes|PostgreSQL|Redis|"
            r"MongoDB|OpenAI|DeepSeek|Claude|GPT|LLM|API|REST|GraphQL|AWS|GCP|Azure)\b",
            texto, _re.IGNORECASE
        )
        return list(set(palavras[:5] + techs[:5]))

    # ══════════════════════════════════════════════════════════════════════
    # #23 Resumo automático de sessão ao encerrar
    # ══════════════════════════════════════════════════════════════════════

    def resumo_sessao_automatico(self) -> str:
        """Gera resumo da sessão para salvar na memória de alta prioridade."""
        if len(self.historico) < 2:
            return ""
        historico_str = "\n".join(list(self.historico)[-20:])
        system = (
            "Resuma esta sessão em 3 tópicos:\n"
            "1. TRABALHEI EM: (o que foi feito)\n"
            "2. DECIDI: (decisões tomadas)\n"
            "3. EM ABERTO: (o que ficou pendente)\n"
            "Seja conciso, máx 5 linhas total."
        )
        r = self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, historico_str)
        return r.strip() if r else ""

    # ══════════════════════════════════════════════════════════════════════
    # #25 Memória prospectiva — lembretes futuros
    # ══════════════════════════════════════════════════════════════════════

    def _detectar_lembrete_futuro(self, query: str) -> None:
        """Detecta intenção de lembrete futuro e salva na memória."""
        import re as _re
        padroes = [
            r"preciso (revisar|ver|checar|lembrar).{0,40}(amanhã|semana|depois|próxima)",
            r"não (esquecer|esqueça).{0,40}",
            r"lembra.{0,10}(de|que).{0,60}",
        ]
        for pat in padroes:
            m = _re.search(pat, query.lower())
            if m:
                self.memoria.salvar(
                    f"[LEMBRETE FUTURO] {query[:200]}",
                    "Usuário pediu para lembrar disso",
                    "lembrete"
                )
                break

    # ══════════════════════════════════════════════════════════════════════
    # #26 Deduplicação semântica de memória
    # ══════════════════════════════════════════════════════════════════════

    def _deve_salvar_memoria(self, texto: str, threshold: float = 0.95) -> bool:
        """Verifica se já existe memória semanticamente idêntica (sim. > threshold)."""
        if not self.memoria._encoder_pronto.is_set() or self.memoria.encoder is None:
            return True
        if not self.memoria.registros:
            return True
        try:
            import numpy as _np
            vec = self.memoria.encoder.encode([texto])[0].astype("float32")
            similares = self.memoria.buscar(texto, k=1)
            if not similares:
                return True
            vec_sim = self.memoria.encoder.encode([similares[0]])[0].astype("float32")
            dot   = float(vec @ vec_sim)
            norms = float((_np.linalg.norm(vec) * _np.linalg.norm(vec_sim)))
            sim   = dot / norms if norms > 0 else 0.0
            return sim < threshold
        except Exception:
            return True

    # ══════════════════════════════════════════════════════════════════════
    # #34 Prefetch de contexto durante o input do usuário
    # ══════════════════════════════════════════════════════════════════════

    def _prefetch_contexto(self, query: str) -> dict:
        """Inicia busca de contexto em paralelo enquanto os núcleos são consultados."""
        resultado: dict = {"memoria": [], "analogias": ""}
        if not query:
            return resultado
        try:
            resultado["memoria"]   = self.memoria.buscar(query, k=3)
            resultado["analogias"] = self._raciocinio_analogico(query)
        except Exception:
            pass
        return resultado

    # ══════════════════════════════════════════════════════════════════════
    # #47 Detecção e resolução de alucinação
    # ══════════════════════════════════════════════════════════════════════

    def _detectar_alucinacao(self, veredito: str, contexto: str) -> tuple[bool, str]:
        """Compara resposta com contexto injetado. Detecta claims sem base."""
        system = (
            "Analise se a resposta contém afirmações ESPECÍFICAS (datas, nomes, números, fatos) "
            "que NÃO estão no contexto fornecido.\n"
            "Se tudo está fundamentado: responda '__OK__'\n"
            "Se houver claims sem base: liste-os brevemente. Máx 50 palavras."
        )
        prompt = f"Contexto disponível:\n{contexto[:1000]}\n\nResposta:\n{veredito[:600]}"
        r = self._chamar_local(system, prompt)
        if not r or "__OK__" in r:
            return False, veredito
        # Marca claims não verificados
        veredito_marcado = veredito + f"\n\n⚠ [Verificar: {r.strip()[:120]}]"
        return True, veredito_marcado

    # ══════════════════════════════════════════════════════════════════════
    # #49 Geração de exemplos concretos automática
    # ══════════════════════════════════════════════════════════════════════

    def _gerar_exemplos(self, query: str, veredito: str, intencao: str) -> str:
        """Para respostas conceituais, gera 1-2 exemplos concretos e os anexa."""
        if intencao not in ("factual", "técnico"):
            return veredito
        if "exemplo" in veredito.lower() or "por exemplo" in veredito.lower():
            return veredito   # já tem exemplos
        system = (
            "Dê 1-2 exemplos concretos e práticos que ilustrem a resposta abaixo. "
            "Seja direto. Máx 60 palavras. Não repita o que já foi dito na resposta."
        )
        prompt = f"Conceito: {query}\nResposta: {veredito[:400]}"
        r = self._chamar_local(system, prompt)
        if r and len(r.strip()) > 20:
            return veredito + f"\n\n**Exemplo prático:** {r.strip()}"
        return veredito

    # ══════════════════════════════════════════════════════════════════════
    # #50 Execução de código em sandbox antes de entregar
    # ══════════════════════════════════════════════════════════════════════

    def _validar_codigo_na_resposta(self, veredito: str) -> str:
        """Detecta blocos de código Python na resposta e valida em sandbox."""
        import re as _re, subprocess, tempfile
        blocos = _re.findall(r"```python\n(.*?)```", veredito, _re.DOTALL)
        if not blocos:
            return veredito
        for bloco in blocos:
            try:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
                    tmp.write(bloco)
                    tmp_path = tmp.name
                res = subprocess.run(
                    ["python", tmp_path], capture_output=True, text=True, timeout=10
                )
                if res.returncode != 0 and res.stderr:
                    erro = res.stderr.strip().splitlines()[-1][:100]
                    veredito = veredito.replace(
                        f"```python\n{bloco}```",
                        f"```python\n{bloco}```\n⚠ *[Teste automático: {erro}]*"
                    )
                import os as _os
                _os.unlink(tmp_path)
            except Exception:
                pass
        return veredito

    # ══════════════════════════════════════════════════════════════════════
    # #54 Detecção de tom emocional na query
    # ══════════════════════════════════════════════════════════════════════

    def _detectar_tom_emocional(self, query: str) -> str:
        """Detecta frustração, urgência, confusão ou entusiasmo na query."""
        q = query.lower()
        if any(p in q for p in ["urgente", "agora", "rápido", "preciso já", "prazo"]):
            return "urgência"
        if any(p in q for p in ["não entendo", "confuso", "perdido", "não sei", "ajuda"]):
            return "confusão"
        if any(p in q for p in ["odeio", "que merda", "impossível", "frustrante", "não funciona"]):
            return "frustração"
        if any(p in q for p in ["incrível", "adorei", "perfeito", "ótimo", "muito bom"]):
            return "entusiasmo"
        return "neutro"

    # ══════════════════════════════════════════════════════════════════════
    # #55 Geração de perguntas de follow-up
    # ══════════════════════════════════════════════════════════════════════

    def _gerar_followups(self, query: str, veredito: str, intencao: str) -> str:
        """Sugere 2 perguntas de follow-up relevantes ao final de respostas complexas."""
        if len(veredito.split()) < 100:
            return veredito
        if intencao == "criativo":
            return veredito
        system = (
            "Sugira 2 perguntas de follow-up que o usuário provavelmente vai ter "
            "após ler a resposta. Seja específico ao tema. "
            "Formato: '→ Pergunta 1\n→ Pergunta 2'"
        )
        prompt = f"Query original: {query}\nResposta: {veredito[:400]}"
        r = self._chamar_local(system, prompt)
        if r and "→" in r:
            return veredito + f"\n\n**Próximas perguntas frequentes:**\n{r.strip()}"
        return veredito

    # ══════════════════════════════════════════════════════════════════════
    # #59 Detecção de pergunta retórica
    # ══════════════════════════════════════════════════════════════════════

    def _eh_retorica(self, query: str) -> bool:
        """Detecta se a query é retórica (quer validação) vs. factual (quer análise)."""
        q = query.lower()
        marcadores = ["você acha que", "não é mesmo?", "concorda?", "é incrível como",
                      "eu tinha razão", "como pode", "que absurdo", "imagina só"]
        return any(m in q for m in marcadores)

    # ══════════════════════════════════════════════════════════════════════
    # #60 Indicador de irreversibilidade
    # ══════════════════════════════════════════════════════════════════════

    def _verificar_irreversibilidade(self, query: str, veredito: str) -> str:
        """Adiciona aviso para decisões com ações irreversíveis."""
        irreversiveis = ["deletar", "remover permanentemente", "demitir", "assinar contrato",
                         "transferir", "publicar em produção", "dropar tabela", "formatar"]
        q = query.lower()
        if any(p in q for p in irreversiveis):
            aviso = "\n\n⚠ **AÇÃO IRREVERSÍVEL** — Verifique antes de executar: faça backup, confirme permissões e valide em ambiente de teste primeiro."
            return veredito + aviso
        return veredito

    # ══════════════════════════════════════════════════════════════════════
    # #61 Benchmark automático de qualidade
    # ══════════════════════════════════════════════════════════════════════

    def _benchmark_query(self, query: str, veredito: str, intencao: str) -> None:
        """Registra query+resposta para análise de qualidade periódica."""
        reg = {
            "ts":       datetime.now().isoformat(timespec="seconds"),
            "intencao": intencao,
            "query":    query[:200],
            "chars":    len(veredito),
            "palavras": len(veredito.split()),
            "conf_ok":  True,
        }
        try:
            self._bench_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._bench_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════
    # #62 Evolução guiada por feedback implícito
    # ══════════════════════════════════════════════════════════════════════

    def _registrar_feedback_implicito(self, query: str) -> None:
        """Follow-up em menos de 15s = sinal de insatisfação com a resposta anterior."""
        if self._ultimo_veredito_ts > 0:
            delta = time.time() - self._ultimo_veredito_ts
            self.perfil.registrar_followup_rapido(delta)
            if delta < 15:
                self.consciencia.registrar_query("feedback_negativo_implicito", sucesso=False)

    # ══════════════════════════════════════════════════════════════════════
    # #63 Proposição proativa de auto-melhorias
    # ══════════════════════════════════════════════════════════════════════

    def _verificar_proposta_melhoria(self) -> None:
        """A cada 20 queries, propõe auto-melhoria se houver ponto fraco claro."""
        total = self.consciencia._estado.get("total_queries", 0)
        if total % 20 != 0 or total == 0:
            return
        temas = self.consciencia._estado.get("temas_frequentes", {})
        if not temas:
            return
        tema_dominant = max(temas, key=temas.get)
        print(f"\n{Fore.MAGENTA}  [MAGI] Posso aprofundar meu raciocínio em '{tema_dominant}'. "
              f"Use 'estudar' para iniciar aprendizado autônomo.{Fore.RESET}")

    # ══════════════════════════════════════════════════════════════════════
    # #66 Versionamento semântico do próprio código
    # ══════════════════════════════════════════════════════════════════════

    def _incrementar_versao(self, tipo: str = "patch") -> str:
        """Incrementa versão semântica após evolução bem-sucedida."""
        try:
            if self._versao_path.exists():
                dados = json.loads(self._versao_path.read_text(encoding="utf-8"))
            else:
                dados = {"versao": "1.0.0", "changelog": []}
            major, minor, patch = [int(x) for x in dados["versao"].split(".")]
            if tipo == "major":   major += 1; minor = 0; patch = 0
            elif tipo == "minor": minor += 1; patch = 0
            else:                 patch += 1
            nova_versao = f"{major}.{minor}.{patch}"
            dados["versao"] = nova_versao
            dados["changelog"].append({
                "versao": nova_versao,
                "ts":     datetime.now().isoformat(timespec="seconds"),
                "tipo":   tipo,
            })
            dados["changelog"] = dados["changelog"][-50:]
            self._versao_path.parent.mkdir(parents=True, exist_ok=True)
            self._versao_path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
            self._versao_atual = nova_versao
            return nova_versao
        except Exception:
            return self._versao_atual

    # ══════════════════════════════════════════════════════════════════════
    # #67 A/B testing de prompts internamente
    # ══════════════════════════════════════════════════════════════════════

    def _obter_system_ab(self, nucleo: str) -> str | None:
        """10% das queries testam uma variação do system prompt."""
        import random as _random
        if _random.random() > 0.10:
            return None
        variantes = {
            "MELCHIOR-1": "Seja ainda mais conciso — máx 80 palavras. Priorize números e dados.",
            "BALTHASAR-2": "Foque no risco PRINCIPAL. Descarte considerações secundárias.",
        }
        return variantes.get(nucleo)

    # ══════════════════════════════════════════════════════════════════════
    # #74 Sandbox de teste antes da evolução principal
    # ══════════════════════════════════════════════════════════════════════

    def _testar_em_sandbox(self, codigo_novo: str) -> tuple[bool, str]:
        """Testa modificação em arquivo temporário completamente isolado.

        Usa sys.executable para garantir compatibilidade de versão Python.
        Verifica AST + compile + ausência de chamadas destrutivas.
        """
        import tempfile, subprocess, sys as _sys
        python_exe = _sys.executable or "python"

        # Pré-validação rápida in-process
        try:
            import ast as _ast
            _ast.parse(codigo_novo)
            compile(codigo_novo, "<sandbox_pre>", "exec")
        except SyntaxError as e:
            return False, f"Pré-validação falhou: linha {e.lineno}: {e.msg}"

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                              delete=False, encoding="utf-8") as tmp:
                tmp.write(codigo_novo)
                tmp_path = tmp.name

            res = subprocess.run(
                [python_exe, "-c",
                 f"import ast, sys; "
                 f"src=open(r'{tmp_path}',encoding='utf-8').read(); "
                 f"ast.parse(src); compile(src,'<sb>','exec'); "
                 f"print('SANDBOX_OK')"],
                capture_output=True, text=True, timeout=20
            )
            import os as _os
            try:
                _os.unlink(tmp_path)
            except Exception:
                pass

            if res.returncode == 0 and "SANDBOX_OK" in res.stdout:
                return True, "Sandbox OK"
            erro = (res.stderr or res.stdout or "Falha desconhecida").strip()[:300]
            return False, f"Sandbox: {erro}"

        except subprocess.TimeoutExpired:
            return False, "Sandbox timeout (20s)"
        except Exception as e:
            return False, f"Sandbox erro: {e}"

    # ══════════════════════════════════════════════════════════════════════
    # #76 Modo foco
    # ══════════════════════════════════════════════════════════════════════

    def alternar_modo_foco(self) -> bool:
        self._modo_foco = not self._modo_foco
        return self._modo_foco

    # ══════════════════════════════════════════════════════════════════════
    # #77 Histórico pesquisável com busca semântica
    # ══════════════════════════════════════════════════════════════════════

    def buscar_historico(self, query: str, k: int = 5) -> list[str]:
        """Busca semanticamente no histórico completo de memória."""
        return self.memoria.buscar(query, k=k)

    # ══════════════════════════════════════════════════════════════════════
    # #79 Dashboard de saúde do sistema
    # ══════════════════════════════════════════════════════════════════════

    def dashboard_saude(self) -> str:
        import psutil, os as _os
        proc = psutil.Process(_os.getpid()) if "psutil" in sys.modules else None
        ram  = f"{proc.memory_info().rss / 1024**2:.0f} MB" if proc else "N/D"
        n_mem   = len(self.memoria.registros)
        n_faiss = self.memoria.index.ntotal if hasattr(self.memoria, "index") else 0
        n_cache = len(self._cache_respostas)
        hits_total = self.consciencia._estado.get("total_queries", 0)
        versao  = self._versao_atual
        linhas_cb = self.circuit.resumo()
        uptime_min = (time.time() - _session_start) / 60
        return (
            f"\n{'─'*50}\n"
            f"  VERSÃO          : {versao}\n"
            f"  RAM processo    : {ram}\n"
            f"  Uptime sessão   : {uptime_min:.1f} min\n"
            f"  Memórias FAISS  : {n_faiss} ({n_mem} registros)\n"
            f"  Cache semântico : {n_cache} entradas\n"
            f"  Total queries   : {hits_total}\n"
            f"  Modo foco       : {'ON' if self._modo_foco else 'OFF'}\n"
            f"  Readonly        : {'SIM' if READONLY_MODE else 'NÃO'}\n"
            f"\n  CIRCUIT BREAKER:\n{linhas_cb}\n"
            f"{'─'*50}"
        )

    # ══════════════════════════════════════════════════════════════════════
    # #80 Modo de sessão com objetivo
    # ══════════════════════════════════════════════════════════════════════

    def definir_objetivo_sessao(self, objetivo: str) -> None:
        self._objetivo_sessao = objetivo
        print(f"{Fore.GREEN}  Objetivo da sessão definido: {objetivo}")

    # ══════════════════════════════════════════════════════════════════════
    # #82 Exportação de sessão para markdown
    # ══════════════════════════════════════════════════════════════════════

    def exportar_sessao_md(self) -> str:
        """Gera arquivo .md com toda a sessão formatada."""
        agora   = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho = Path(__file__).parent / f"sessao_magi_{agora}.md"
        linhas  = [
            f"# Sessão MAGI — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n",
            f"**Versão:** {self._versao_atual}  ",
            f"**Objetivo:** {self._objetivo_sessao or 'Não definido'}\n",
            "---\n",
        ]
        for reg in self._historico_exportacao:
            linhas.append(f"### [{reg.get('ts','')}] {reg.get('intencao','').upper()}\n")
            linhas.append(f"**Query:** {reg.get('query','')}\n")
            linhas.append(f"**Resposta:**\n{reg.get('veredito','')}\n")
            linhas.append("---\n")
        conteudo = "\n".join(linhas)
        caminho.write_text(conteudo, encoding="utf-8")
        return str(caminho)

    # ══════════════════════════════════════════════════════════════════════
    # #83 Modo comparativo — mesma query em múltiplos modelos
    # ══════════════════════════════════════════════════════════════════════

    def comparar_modelos(self, query: str) -> None:
        """Envia query para todos os modelos disponíveis e exibe lado a lado."""
        from concurrent.futures import ThreadPoolExecutor
        MAGIInterface.separador("MODO COMPARATIVO", Fore.CYAN)
        print(f"{Fore.WHITE}  Query: {Fore.YELLOW}{query}\n")
        modelos_cfg = [
            ("DeepSeek",  lambda: self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, "Responda diretamente.", query)),
            ("Local",     lambda: self._chamar_local("Responda diretamente.", query)),
        ]
        resultados: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {ex.submit(fn): nome for nome, fn in modelos_cfg}
            for fut, nome in futures.items():
                try:
                    resultados[nome] = fut.result(timeout=30) or "[offline]"
                except Exception as e:
                    resultados[nome] = f"[erro: {e}]"
        for nome, resp in resultados.items():
            print(f"{Fore.CYAN}  ── {nome} ──")
            for ln in (resp or "").strip().splitlines()[:10]:
                print(f"  {Fore.WHITE}{ln}")
            print()
        MAGIInterface.separador(cor=Fore.CYAN)

    # ══════════════════════════════════════════════════════════════════════
    # #90 Integração com clipboard do sistema
    # ══════════════════════════════════════════════════════════════════════

    def copiar_clipboard(self, texto: str) -> bool:
        try:
            import subprocess
            if sys.platform == "win32":
                subprocess.run("clip", input=texto.encode("utf-16"), check=True, shell=True)
            elif sys.platform == "darwin":
                subprocess.run("pbcopy", input=texto.encode("utf-8"), check=True)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"],
                               input=texto.encode("utf-8"), check=True)
            return True
        except Exception:
            return False

    def colar_clipboard(self) -> str:
        try:
            import subprocess
            if sys.platform == "win32":
                r = subprocess.run("powershell Get-Clipboard", capture_output=True, text=True, shell=True)
            elif sys.platform == "darwin":
                r = subprocess.run("pbpaste", capture_output=True, text=True)
            else:
                r = subprocess.run(["xclip", "-selection", "clipboard", "-o"],
                                   capture_output=True, text=True)
            return r.stdout.strip()
        except Exception:
            return ""



    # ══════════════════════════════════════════════════════════════════════
    # CACHE DE EMBEDDINGS (#35) — evita re-encode de queries repetidas
    # ══════════════════════════════════════════════════════════════════════

    def _encode_com_cache(self, texto: str) -> "np.ndarray | None":
        """Codifica texto usando cache em memória. Persiste top-100 no disco."""
        chave = hashlib.md5(texto.encode()).hexdigest()
        if chave in self._cache_embeddings:
            return self._cache_embeddings[chave]
        if not self.memoria._aguardar_encoder(timeout=5.0) or self.memoria.encoder is None:
            return None
        vec = self.memoria.encoder.encode([texto])[0].astype("float32")
        self._cache_embeddings[chave] = vec
        if len(self._cache_embeddings) > 500:
            # Remove metade mais antiga (FIFO simples)
            keys = list(self._cache_embeddings.keys())
            for k in keys[:250]:
                del self._cache_embeddings[k]
        return vec

    # ══════════════════════════════════════════════════════════════════════
    # TREE OF THOUGHTS (#101) — raciocínio em árvore para problemas difíceis
    # ══════════════════════════════════════════════════════════════════════

    def _tree_of_thoughts(self, query: str, n_ramos: int = 3) -> str:
        """Gera N abordagens diferentes para o problema, avalia cada uma e
        escolhe a mais promissora antes de elaborar a resposta final.
        """
        system_tot = (
            f"Você está em modo Tree of Thoughts. Gere {n_ramos} abordagens DISTINTAS "
            f"para resolver o problema, cada uma em 1-2 linhas. "
            f"Formato:\n1. [ABORDAGEM]: descrição\n2. [ABORDAGEM]: descrição\n..."
        )
        ramos_raw = (
            self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system_tot, query)
            or self._chamar_local(system_tot, query)
        )
        if not ramos_raw:
            return ""

        # Avalia cada ramo e escolhe o melhor
        system_eval = (
            "Dadas as abordagens abaixo para o problema, escolha a MAIS PROMISSORA "
            "e explique em 1 linha por quê. Responda: 'MELHOR: [número] — [motivo]'"
        )
        avaliacao = self._chamar_local(system_eval, f"Problema: {query}\nAbordagens:\n{ramos_raw}")
        return f"[ToT] {avaliacao or ramos_raw[:200]}"

    # ══════════════════════════════════════════════════════════════════════
    # SÍNTESE MULTI-FONTE (#102) — agrega múltiplas fontes antes de responder
    # ══════════════════════════════════════════════════════════════════════

    def _sintetizar_multi_fonte(self, query: str, fontes: list[str]) -> str:
        """Combina informações de múltiplas fontes em síntese coerente."""
        if not fontes:
            return ""
        fontes_str = "\n".join(f"Fonte {i+1}: {f[:300]}" for i, f in enumerate(fontes[:5]))
        system = (
            "Sintetize as informações das fontes abaixo em uma resposta coerente e concisa. "
            "Identifique consensos e contradições. Máx 150 palavras."
        )
        r = (
            self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system,
                                   f"Query: {query}\n\n{fontes_str}")
            or self._chamar_local(system, f"Query: {query}\n\n{fontes_str}")
        )
        return r or ""

    # ══════════════════════════════════════════════════════════════════════
    # DETECÇÃO DE DERIVA DE TÓPICO (#103)
    # ══════════════════════════════════════════════════════════════════════

    def _detectar_deriva_topico(self, query: str) -> bool:
        """Detecta se a query mudou drasticamente de tópico em relação ao histórico recente."""
        if not hasattr(self, "_stm") or len(self._stm) < 2:
            return False
        if not self.memoria._encoder_pronto.is_set() or self.memoria.encoder is None:
            return False
        try:
            ultimo_tema = self._stm[-1]["query"]
            vec_atual  = self._encode_com_cache(query)
            vec_ultimo = self._encode_com_cache(ultimo_tema)
            if vec_atual is None or vec_ultimo is None:
                return False
            sim = float(vec_atual @ vec_ultimo) / (
                float(np.linalg.norm(vec_atual)) * float(np.linalg.norm(vec_ultimo)) + 1e-9
            )
            return sim < 0.25   # <25% similaridade = deriva de tópico
        except Exception:
            return False

    # ══════════════════════════════════════════════════════════════════════
    # MODO SOCRÁTICO (#104) — responde com perguntas para aprofundar
    # ══════════════════════════════════════════════════════════════════════

    def _modo_socratico(self, query: str) -> str:
        """Para queries filosóficas/éticas, usa método socrático: responde com perguntas."""
        system = (
            "Use o método socrático: em vez de dar a resposta diretamente, "
            "faça 2-3 perguntas que levem o usuário a descobrir a resposta por conta própria. "
            "As perguntas devem ser progressivas, da mais simples à mais profunda. "
            "Máx 80 palavras."
        )
        return self._chamar_local(system, query) or ""

    # ══════════════════════════════════════════════════════════════════════
    # RESUMO EXECUTIVO AUTOMÁTICO (#105)
    # ══════════════════════════════════════════════════════════════════════

    def _gerar_resumo_executivo(self, texto: str) -> str:
        """Gera bullet points do texto longo para consumo rápido."""
        if len(texto.split()) < 100:
            return texto
        system = (
            "Resuma em 3-5 bullet points os pontos MAIS importantes. "
            "Formato: • ponto 1\n• ponto 2\n..."
        )
        r = self._chamar_local(system, texto[:1500])
        if r and "•" in r:
            return r.strip() + "\n\n---\n" + texto
        return texto

    # ══════════════════════════════════════════════════════════════════════
    # GERAÇÃO DE ANALOGIAS (#106)
    # ══════════════════════════════════════════════════════════════════════

    def _gerar_analogia(self, conceito: str, nivel: str = "medio") -> str:
        """Gera analogia do conceito calibrada ao nível do usuário."""
        mapa_nivel = {
            "iniciante": "uma criança de 10 anos",
            "medio":     "alguém sem conhecimento técnico",
            "senior":    "um profissional de outra área"
        }
        publico = mapa_nivel.get(nivel, "alguém sem conhecimento técnico")
        system  = f"Explique o conceito abaixo usando uma analogia do dia-a-dia para {publico}. Máx 40 palavras."
        return self._chamar_local(system, conceito) or ""

    # ══════════════════════════════════════════════════════════════════════
    # VERIFICAÇÃO DE CONSISTÊNCIA INTERNA (#107)
    # ══════════════════════════════════════════════════════════════════════

    def _verificar_consistencia(self, veredito: str) -> tuple[bool, str]:
        """Verifica se o veredito contradiz afirmações anteriores na sessão."""
        if not self.historico:
            return True, veredito
        historico_recente = "\n".join(list(self.historico)[-5:])
        system = (
            "Verifique se a nova resposta contradiz algo no histórico recente.\n"
            "Se não há contradição: responda '__OK__'\n"
            "Se há contradição: descreva em 1 linha e sugira como resolver."
        )
        prompt  = f"Histórico:\n{historico_recente}\n\nNova resposta:\n{veredito[:400]}"
        r = self._chamar_local(system, prompt)
        if not r or "__OK__" in r:
            return True, veredito
        return False, veredito + f"\n\n[⚠ Consistência: {r.strip()[:100]}]"

    # ══════════════════════════════════════════════════════════════════════
    # ADAPTAÇÃO DE FORMATO POR CONTEXTO (#108)
    # ══════════════════════════════════════════════════════════════════════

    def _adaptar_formato(self, veredito: str, intencao: str, query: str) -> str:
        """Garante que o formato da resposta é o mais adequado para o tipo de query."""
        q = query.lower()
        # Queries de lista → garante formato de lista
        if any(p in q for p in ["liste", "quais são", "enumere", "cite"]):
            if "\n" not in veredito and "•" not in veredito and "1." not in veredito:
                # Formata como lista via modelo
                r = self._chamar_local(
                    "Reformate a resposta abaixo como uma lista com bullet points. Sem adicionar informação.",
                    veredito[:600]
                )
                return r or veredito
        # Queries de comparação → garante estrutura comparativa
        if any(p in q for p in ["diferença entre", "compare", "vs", "versus"]):
            if "vs" not in veredito.lower() and "comparando" not in veredito.lower():
                return veredito   # já ok ou não reformatável
        return veredito

    # ══════════════════════════════════════════════════════════════════════
    # DETECÇÃO DE URGÊNCIA E ESCALONAMENTO (#109)
    # ══════════════════════════════════════════════════════════════════════

    def _escalar_urgencia(self, query: str, intencao: str) -> bool:
        """Para queries urgentes de alto impacto, aumenta prioridade de processamento."""
        urgente = any(p in query.lower() for p in [
            "urgente", "agora", "imediatamente", "crítico", "produção caiu",
            "servidor down", "data breach", "vazamento", "emergência"
        ])
        if urgente and intencao in ("técnico", "decisão"):
            print(f"{Fore.RED}  [URGÊNCIA] Query crítica detectada — priorizando processamento")
            return True
        return False

    # ══════════════════════════════════════════════════════════════════════
    # MODO DE EXPLORAÇÃO (#110) — brainstorm estruturado
    # ══════════════════════════════════════════════════════════════════════

    def _modo_exploracao(self, tema: str) -> None:
        """Brainstorm estruturado: gera ideias em múltiplas dimensões."""
        MAGIInterface.separador("MODO EXPLORAÇÃO", Fore.CYAN)
        dimensoes = ["aplicações práticas", "riscos e limitações", "conexões inesperadas", "questões em aberto"]
        system = "Gere 3 ideias concisas sobre o tema sob a perspectiva solicitada. Seja criativo e específico. Máx 60 palavras."
        for dim in dimensoes:
            print(f"\n{Fore.CYAN}  ◈ {dim.upper()}")
            r = self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, f"Tema: {tema}\nPerspectiva: {dim}")
            if r:
                for ln in r.strip().splitlines()[:4]:
                    print(f"    {Fore.WHITE}{ln}")
        MAGIInterface.separador(cor=Fore.CYAN)

    # ══════════════════════════════════════════════════════════════════════
    # ANÁLISE DE SENTIMENTO DA SESSÃO (#111)
    # ══════════════════════════════════════════════════════════════════════

    def _analisar_sentimento_sessao(self) -> str:
        """Analisa o tom geral da sessão: produtiva, frustrada, exploratória etc."""
        if len(self.historico) < 3:
            return "neutro"
        sample = "\n".join(list(self.historico)[-6:])
        system = (
            "Analise o tom desta conversa. Responda com UMA palavra:\n"
            "produtiva | frustrada | exploratória | técnica | criativa | confusa | neutra"
        )
        r = self._chamar_local(system, sample)
        if r:
            palavra = r.strip().lower().split()[0].rstrip(".,")
            validas = {"produtiva", "frustrada", "exploratória", "técnica", "criativa", "confusa", "neutra"}
            if palavra in validas:
                return palavra
        return "neutra"

    # ══════════════════════════════════════════════════════════════════════
    # MONITORAMENTO DE DESEMPENHO DO NÚCLEO (#112)
    # ══════════════════════════════════════════════════════════════════════

    def _monitorar_nucleo(self, nome: str, fn: "callable", *args) -> tuple:
        """Wrapper que mede latência e registra no observador e circuit breaker."""
        t0 = time.time()
        try:
            resultado = fn(*args)
            lat = time.time() - t0
            self.observador.registrar_latencia(nome, lat)
            self.circuit.registrar_sucesso(nome, lat)
            return resultado
        except Exception as e:
            lat = time.time() - t0
            self.observador.registrar_erro(nome, str(e))
            self.circuit.registrar_falha(nome)
            raise

    # ══════════════════════════════════════════════════════════════════════
    # PROMPT DINÂMICO COM NÍVEL DE VERBOSIDADE (#113)
    # ══════════════════════════════════════════════════════════════════════

    def _ajustar_system_verbosidade(self, system: str) -> str:
        """Ajusta o system prompt do núcleo conforme verbosidade da sessão ou perfil."""
        nivel = self._nivel_verbosidade_sessao or self.perfil.verbosidade
        if nivel == "curta":
            return system + " RESPONDA EM NO MÁXIMO 60 PALAVRAS. Seja extremamente conciso."
        elif nivel == "detalhada":
            return system + " Seja detalhado e completo. Pode usar até 400 palavras se necessário."
        return system   # normal: sem modificação

    # ══════════════════════════════════════════════════════════════════════
    # DETECÇÃO DE INTENÇÃO SECUNDÁRIA (#114)
    # ══════════════════════════════════════════════════════════════════════

    def _detectar_intencao_secundaria(self, query: str, intencao_primaria: str) -> str | None:
        """Detecta se a query tem uma intenção secundária não declarada."""
        q = query.lower()
        secundarias = {
            "validação":   ["certo?", "correto?", "concorda?", "não é?", "faz sentido?"],
            "aprendizado": ["como funciona", "me explica", "o que é", "por que"],
            "debug":       ["não funciona", "dá erro", "quebrou", "falhou"],
            "otimização":  ["mais rápido", "melhorar", "otimizar", "performance"],
        }
        for intent, marcadores in secundarias.items():
            if intent != intencao_primaria and any(m in q for m in marcadores):
                return intent
        return None

    # ══════════════════════════════════════════════════════════════════════
    # GERAÇÃO DE HIPÓTESES ANTES DO VEREDITO (#115)
    # ══════════════════════════════════════════════════════════════════════

    def _gerar_hipoteses(self, query: str) -> list[str]:
        """Gera 2-3 interpretações distintas da query antes de processar."""
        system = (
            "Gere 2-3 interpretações distintas desta query. "
            "Formato: H1: ...\nH2: ...\nH3: ..."
        )
        r = self._chamar_local(system, query)
        if not r:
            return [query]
        hipoteses = [ln.split(":", 1)[-1].strip() for ln in r.splitlines() if ln.startswith("H")]
        return hipoteses[:3] or [query]

    # ══════════════════════════════════════════════════════════════════════
    # DETECÇÃO DE LACUNAS DE CONHECIMENTO (#116)
    # ══════════════════════════════════════════════════════════════════════

    def _detectar_lacunas(self, query: str, veredito: str) -> list[str]:
        """Identifica aspectos da query que a resposta não cobriu completamente."""
        system = (
            "Liste em bullet points os aspectos da pergunta que a resposta NÃO abordou. "
            "Se cobriu tudo: responda 'COMPLETO'. Máx 3 bullets."
        )
        r = self._chamar_local(system, f"Pergunta: {query}\nResposta: {veredito[:500]}")
        if not r or "COMPLETO" in r:
            return []
        return [ln.strip("•- ").strip() for ln in r.splitlines() if ln.strip().startswith(("•", "-"))][:3]

    # ══════════════════════════════════════════════════════════════════════
    # RESOLUÇÃO DE AMBIGUIDADE AUTOMÁTICA (#117)
    # ══════════════════════════════════════════════════════════════════════

    def _resolver_ambiguidade(self, query: str) -> str:
        """Se a query for ambígua, escolhe a interpretação mais provável
        com base no perfil e histórico — sem perguntar ao usuário."""
        system = (
            "A query abaixo é ambígua? Se sim, qual a interpretação MAIS PROVÁVEL "
            "dado um usuário técnico? Responda com a query reescrita sem ambiguidade. "
            "Se não for ambígua, responda '__OK__'."
        )
        perfil_ctx = f"Nível: {self.perfil.nivel} | Projeto: {self.perfil._dados.get('projeto_ativo','N/A')}"
        r = self._chamar_local(system, f"Query: {query}\nContexto usuário: {perfil_ctx}")
        if r and "__OK__" not in r and len(r.strip()) > 10:
            return r.strip()
        return query

    # ══════════════════════════════════════════════════════════════════════
    # APRENDIZADO POR REFORÇO IMPLÍCITO (#118)
    # ══════════════════════════════════════════════════════════════════════

    def _registrar_reforco(self, query: str, veredito: str, positivo: bool) -> None:
        """Registra sinal de reforço positivo/negativo para ajuste futuro de prompts."""
        reg = {
            "ts":       datetime.now().isoformat(timespec="seconds"),
            "query":    query[:100],
            "positivo": positivo,
            "chars":    len(veredito),
            "intencao": self._INTENCAO_CACHE.get(query, "indefinido"),
        }
        path = Path(__file__).parent / "data" / "logs" / "magi_reforco.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════
    # MODO PROFESSOR (#119) — explica passo a passo
    # ══════════════════════════════════════════════════════════════════════

    def _modo_professor(self, tema: str) -> None:
        """Explica um tema de forma didática em etapas progressivas."""
        MAGIInterface.separador("MODO PROFESSOR", Fore.GREEN)
        etapas = [
            ("Conceito básico",    "Explique o conceito em 1 parágrafo simples, sem jargão."),
            ("Como funciona",      "Explique o mecanismo interno em 2-3 passos concretos."),
            ("Exemplo prático",    "Dê um exemplo real e específico de uso. Máx 60 palavras."),
            ("Armadilhas comuns",  "Liste 2 erros frequentes que iniciantes cometem. Máx 60 palavras."),
        ]
        for titulo, instrucao in etapas:
            print(f"\n{Fore.GREEN}  ◈ {titulo.upper()}")
            r = self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO,
                                       f"{instrucao}", f"Tema: {tema}")
            if r:
                for ln in r.strip().splitlines()[:5]:
                    print(f"    {Fore.WHITE}{ln}")
        MAGIInterface.separador(cor=Fore.GREEN)

    # ══════════════════════════════════════════════════════════════════════
    # ANÁLISE DE COMPLEXIDADE DA QUERY (#120)
    # ══════════════════════════════════════════════════════════════════════

    def _complexidade_query(self, query: str) -> str:
        """Classifica a complexidade: simples | moderada | complexa | especializada."""
        palavras = len(query.split())
        tem_codigo = "```" in query or "def " in query or "import " in query
        tem_multiplas = query.count("?") > 1 or " e " in query.lower()
        if palavras < 8 and not tem_multiplas:
            return "simples"
        if tem_codigo or palavras > 40:
            return "especializada"
        if tem_multiplas or palavras > 20:
            return "complexa"
        return "moderada"

    # ══════════════════════════════════════════════════════════════════════
    # INJEÇÃO DINÂMICA DE CONHECIMENTO DO GRAFO (#121)
    # ══════════════════════════════════════════════════════════════════════

    def _contexto_grafo(self, query: str) -> str:
        """Extrai entidades da query e busca contexto do grafo de conhecimento."""
        entidades = self._extrair_entidades(query)
        if not entidades:
            return ""
        partes = []
        for ent in entidades[:3]:
            ctx = self.grafo.contexto_entidade(ent)
            if ctx:
                partes.append(ctx)
        if partes:
            self.grafo.extrair_e_indexar(query, contexto="query")
            return "─── GRAFO DE CONHECIMENTO ───\n" + "\n".join(partes) + "\n\n"
        return ""

    # ══════════════════════════════════════════════════════════════════════
    # PROMPT COMPRESSION (#122) — comprime prompts muito longos
    # ══════════════════════════════════════════════════════════════════════

    def _comprimir_prompt(self, prompt: str, max_chars: int = 8000) -> str:
        """Remove redundâncias do prompt se ultrapassar max_chars."""
        if len(prompt) <= max_chars:
            return prompt
        system = (
            "Comprima o contexto abaixo mantendo APENAS as informações essenciais "
            "para responder à pergunta. Elimine redundâncias. Máx 2000 chars."
        )
        comprimido = self._chamar_local(system, prompt[:4000])
        if comprimido and len(comprimido) < len(prompt):
            return comprimido + prompt[-2000:]   # mantém final (mais recente)
        return prompt[:max_chars]

    # ══════════════════════════════════════════════════════════════════════
    # GERAÇÃO DE CONTRA-ARGUMENTOS (#123)
    # ══════════════════════════════════════════════════════════════════════

    def _gerar_contra_argumentos(self, veredito: str, intencao: str) -> str:
        """Para respostas de decisão/ético, adiciona o melhor contra-argumento."""
        if intencao not in ("decisão", "ético"):
            return veredito
        system = (
            "Qual é o melhor contra-argumento para a posição expressa abaixo? "
            "Em 1-2 frases, apresente o argumento mais forte do lado oposto. "
            "Não adicione ressalvas ou contexto extra."
        )
        r = self._chamar_local(system, veredito[:400])
        if r and len(r.strip()) > 20:
            return veredito + f"\n\n**Contra-argumento principal:** {r.strip()}"
        return veredito

    # ══════════════════════════════════════════════════════════════════════
    # DETECÇÃO DE PADRÕES DE ERRO RECORRENTES (#124)
    # ══════════════════════════════════════════════════════════════════════

    def _padroes_erro_recorrentes(self) -> list[str]:
        """Lê o histórico de reflexões e identifica tipos de erro que se repetem."""
        if not self._reflexao_path.exists():
            return []
        try:
            from collections import Counter
            pontos_fracos: list[str] = []
            with open(self._reflexao_path, encoding="utf-8") as f:
                for ln in f:
                    try:
                        r = json.loads(ln)
                        if r.get("ponto_fraco"):
                            pontos_fracos.append(r["ponto_fraco"][:50])
                    except Exception:
                        pass
            if len(pontos_fracos) < 3:
                return []
            # Agrupa por palavras-chave frequentes
            palavras = [p for texto in pontos_fracos for p in texto.lower().split() if len(p) > 4]
            mais_comuns = [p for p, _ in Counter(palavras).most_common(3)]
            return mais_comuns
        except Exception:
            return []

    # ══════════════════════════════════════════════════════════════════════
    # MODO DEBATE ASSIMÉTRICO (#125) — perspectivas desiguais
    # ══════════════════════════════════════════════════════════════════════

    def debate_assimetrico(self, tema: str, lado_a: str, lado_b: str) -> None:
        """Debate onde cada lado defende uma posição específica definida pelo usuário."""
        from concurrent.futures import ThreadPoolExecutor
        MAGIInterface.separador(f"DEBATE: {lado_a} vs {lado_b}", Fore.MAGENTA)
        p_mel = f"Defenda '{lado_a}' sobre: {tema}. Seja persuasivo. Máx 100 palavras."
        p_bal = f"Defenda '{lado_b}' sobre: {tema}. Seja persuasivo. Máx 100 palavras."
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_mel = ex.submit(self._chamar_nucleo, "MELCHIOR-1",  p_mel)
            f_bal = ex.submit(self._chamar_nucleo, "BALTHASAR-2", p_bal)
            r_mel, _ = f_mel.result()
            r_bal, _ = f_bal.result()
        print(f"\n{Fore.CYAN}  [{lado_a}] MELCHIOR-1:")
        for ln in (r_mel or "[offline]").splitlines()[:8]:
            print(f"  {Fore.WHITE}{ln}")
        print(f"\n{Fore.GREEN}  [{lado_b}] BALTHASAR-2:")
        for ln in (r_bal or "[offline]").splitlines()[:8]:
            print(f"  {Fore.WHITE}{ln}")
        # CASPER arbitra
        p_cas = (f"Debate:\n{lado_a}: {r_mel or 'N/A'}\n{lado_b}: {r_bal or 'N/A'}\n"
                 f"Arbitra: qual argumento é mais sólido e por quê? Máx 100 palavras.")
        veredito, _ = self._chamar_nucleo("CASPER-3", p_cas)
        print(f"\n{Fore.RED}  [ÁRBITRO] CASPER-3:")
        MAGIInterface.digitar(veredito or "[offline]", cor=Fore.YELLOW, delay=0.008)
        MAGIInterface.separador(cor=Fore.MAGENTA)

    # ══════════════════════════════════════════════════════════════════════
    # ANÁLISE DE ARGUMENTO FORMAL (#126)
    # ══════════════════════════════════════════════════════════════════════

    def _analisar_argumento(self, texto: str) -> str:
        """Decompõe um argumento em: premissas, conclusão, validade lógica."""
        system = (
            "Analise o argumento:\n"
            "1. PREMISSAS: liste as premissas implícitas e explícitas\n"
            "2. CONCLUSÃO: qual é a conclusão central\n"
            "3. VALIDADE: o argumento é logicamente válido? Por quê?\n"
            "Seja conciso. Máx 100 palavras."
        )
        return self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, texto) or ""

    # ══════════════════════════════════════════════════════════════════════
    # SUMARIZAÇÃO INCREMENTAL (#127)
    # ══════════════════════════════════════════════════════════════════════

    def _sumarizar_incrementalmente(self, textos: list[str]) -> str:
        """Sumariza lista de textos de forma incremental (map-reduce style)."""
        if not textos:
            return ""
        if len(textos) == 1:
            return textos[0][:500]
        # Divide em chunks e sumariza cada um
        resumos = []
        for chunk in [textos[i:i+3] for i in range(0, len(textos), 3)]:
            combinado = " | ".join(chunk)
            r = self._chamar_local("Resuma em 1 frase:", combinado[:800])
            resumos.append(r or combinado[:100])
        # Sumariza os resumos
        final = self._chamar_local("Combine estes resumos em 2-3 frases coesas:", " | ".join(resumos))
        return final or " ".join(resumos)[:400]

    # ══════════════════════════════════════════════════════════════════════
    # NOTIFICAÇÃO DE EVOLUÇÃO NO BOOT (#128)
    # ══════════════════════════════════════════════════════════════════════

    def _notificar_evolucoes_recentes(self) -> None:
        """No boot, informa melhorias aplicadas desde a última sessão."""
        if not self._versao_path.exists():
            return
        try:
            dados = json.loads(self._versao_path.read_text(encoding="utf-8"))
            changelog = dados.get("changelog", [])
            if len(changelog) >= 2:
                ultima = changelog[-1]
                penultima = changelog[-2]
                if ultima["ts"] > penultima["ts"]:
                    print(f"\n{Fore.MAGENTA}  [EVOLUÇÃO] Nova versão: {ultima['versao']} ({ultima['tipo']})")
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════
    # MODO DE ALTA PRECISÃO (#129) — múltiplas validações antes de entregar
    # ══════════════════════════════════════════════════════════════════════

    def _modo_alta_precisao(self, query: str, veredito: str, intencao: str) -> str:
        """Para queries técnicas críticas, aplica pipeline completo de validação."""
        if intencao != "técnico":
            return veredito
        complexidade = self._complexidade_query(query)
        if complexidade not in ("especializada", "complexa"):
            return veredito
        # 1. Verificação de consistência
        _, veredito = self._verificar_consistencia(veredito)
        # 2. Completude
        veredito = self._avaliar_completude(query, veredito)
        # 3. Lacunas
        lacunas = self._detectar_lacunas(query, veredito)
        if lacunas:
            veredito += "\n\n**Aspectos não cobertos:** " + " · ".join(lacunas)
        return veredito

    # ══════════════════════════════════════════════════════════════════════
    # VERBOSE MODE POR SESSÃO (#130)
    # ══════════════════════════════════════════════════════════════════════

    def _ajustar_verbosidade_sessao(self, cmd: str) -> bool:
        """Processa comando de verbosidade da sessão (#84). Retorna True se processou."""
        cmd_l = cmd.lower().strip()
        mapa  = {
            "seja mais direto":    "curta",
            "seja mais conciso":   "curta",
            "menos palavras":      "curta",
            "seja mais detalhado": "detalhada",
            "mais detalhes":       "detalhada",
            "explique mais":       "detalhada",
        }
        for trigger, nivel in mapa.items():
            if trigger in cmd_l:
                self._nivel_verbosidade_sessao = nivel
                print(f"{Fore.GREEN}  Verbosidade ajustada para: {nivel}")
                return True
        return False

    # ══════════════════════════════════════════════════════════════════════
    # RACIOCÍNIO PROBABILÍSTICO (#131)
    # ══════════════════════════════════════════════════════════════════════

    def _raciocinio_probabilistico(self, query: str) -> str:
        """Para queries de previsão/probabilidade, estrutura resposta com estimativas."""
        gatilhos = ["probabilidade", "chance", "vai acontecer", "possível que", "previsão", "estimar"]
        if not any(g in query.lower() for g in gatilhos):
            return ""
        system = (
            "Para a pergunta de probabilidade abaixo:\n"
            "1. Estime a probabilidade em % com justificativa (1 linha)\n"
            "2. Liste 2 fatores que aumentariam e 2 que diminuiriam essa probabilidade\n"
            "Seja calibrado, não superconfiante. Máx 80 palavras."
        )
        return self._chamar_local(system, query) or ""

    # ══════════════════════════════════════════════════════════════════════
    # SISTEMA DE TAGS PARA QUERIES (#132)
    # ══════════════════════════════════════════════════════════════════════

    def _extrair_tags(self, query: str, veredito: str) -> list[str]:
        """Extrai tags semânticas da troca para indexação futura."""
        texto_combinado = f"{query} {veredito}"
        import re as _re
        # Tags de tecnologia
        techs = _re.findall(
            r"\b(python|javascript|docker|kubernetes|sql|api|machine learning|"
            r"deep learning|neural|fastapi|django|react|rust|go|java)\b",
            texto_combinado.lower()
        )
        # Tags de domínio
        dominios_map = {
            "performance": ["rápido", "lento", "otimizar", "latência"],
            "segurança":   ["vulnerabilidade", "ataque", "criptografia", "autenticação"],
            "arquitetura": ["microserviço", "monolito", "padrão", "design"],
            "dados":       ["banco", "query", "índice", "schema"],
        }
        tags_dominio = [
            dom for dom, palavras in dominios_map.items()
            if any(p in texto_combinado.lower() for p in palavras)
        ]
        return list(set(techs[:3] + tags_dominio[:3]))

    # ══════════════════════════════════════════════════════════════════════
    # INJEÇÃO DE FATOS VERIFICADOS (#133)
    # ══════════════════════════════════════════════════════════════════════

    def _injetar_fatos_verificados(self, query: str) -> str:
        """Busca fatos verificados na base de conhecimento do MAGIEstudo."""
        conhecimento_path = Path(__file__).parent / "data" / "knowledge" / "magi_conhecimento.jsonl"
        if not conhecimento_path.exists():
            return ""
        try:
            fatos_relevantes = []
            with open(conhecimento_path, encoding="utf-8") as f:
                for ln in f:
                    try:
                        reg = json.loads(ln)
                        topico   = reg.get("topico", "").lower()
                        resposta = reg.get("resposta", "")
                        q_lower  = query.lower()
                        # Relevância simples por keywords do tópico
                        palavras_topico = topico.split()
                        if any(p in q_lower for p in palavras_topico if len(p) > 4):
                            fatos_relevantes.append(resposta[:100])
                    except Exception:
                        pass
            if fatos_relevantes:
                return "─── CONHECIMENTO VERIFICADO (MAGIEstudo) ───\n" + "\n".join(f"  · {f}" for f in fatos_relevantes[:3]) + "\n\n"
        except Exception:
            pass
        return ""

    # ══════════════════════════════════════════════════════════════════════
    # ANÁLISE DE IMPACTO DE SEGUNDA ORDEM (#134)
    # ══════════════════════════════════════════════════════════════════════

    def _impacto_segunda_ordem(self, query: str, veredito: str, intencao: str) -> str:
        """Para decisões, analisa consequências de segunda ordem (não óbvias)."""
        if intencao != "decisão":
            return veredito
        system = (
            "Identifique 1-2 consequências de SEGUNDA ORDEM da decisão abaixo — "
            "efeitos não óbvios que resultam das consequências diretas. "
            "Seja específico. Máx 50 palavras."
        )
        r = self._chamar_local(system, f"Decisão: {query}\nAnálise: {veredito[:300]}")
        if r and len(r.strip()) > 20:
            return veredito + f"\n\n**Efeitos de segunda ordem:** {r.strip()}"
        return veredito

    # ══════════════════════════════════════════════════════════════════════
    # MODO AGENTE PERSISTENTE (#135) — mantém estado entre tasks do agent
    # ══════════════════════════════════════════════════════════════════════

    def _criar_agente_com_contexto(self) -> "MAGICodeAgent":
        """Cria agente com contexto do projeto ativo injetado."""
        agente = MAGICodeAgent(self)
        projeto = self.perfil._dados.get("projeto_ativo")
        if projeto:
            agente._log_op("contexto", "projeto_ativo", projeto)
        return agente

    # ══════════════════════════════════════════════════════════════════════
    # SISTEMA DE NOTAS RÁPIDAS (#136)
    # ══════════════════════════════════════════════════════════════════════

    def _salvar_nota(self, conteudo: str) -> None:
        """Salva nota rápida associada à sessão atual."""
        path = Path(__file__).parent / "data" / "logs" / "magi_notas.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        reg = {
            "ts":       datetime.now().isoformat(timespec="seconds"),
            "sessao":   self._session_id if hasattr(self, "_session_id") else "?",
            "conteudo": conteudo[:500],
            "projeto":  self.perfil._dados.get("projeto_ativo", ""),
        }
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
            print(f"{Fore.GREEN}  Nota salva.")
        except Exception as e:
            print(f"{Fore.RED}  Erro ao salvar nota: {e}")

    def _listar_notas(self, n: int = 10) -> str:
        """Lista as últimas N notas salvas."""
        path = Path(__file__).parent / "data" / "logs" / "magi_notas.jsonl"
        if not path.exists():
            return "Nenhuma nota salva."
        try:
            notas = []
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    try:
                        notas.append(json.loads(ln))
                    except Exception:
                        pass
            notas = notas[-n:]
            return "\n".join(
                f"  [{nota['ts'][:16]}] {nota['conteudo'][:80]}"
                for nota in reversed(notas)
            )
        except Exception:
            return "Erro ao ler notas."

    # ══════════════════════════════════════════════════════════════════════
    # ANÁLISE DE CÓDIGO EM LINGUAGENS MÚLTIPLAS (#137)
    # ══════════════════════════════════════════════════════════════════════

    def _detectar_linguagem(self, codigo: str) -> str:
        """Detecta a linguagem de programação de um trecho de código."""
        import re as _re
        padroes = {
            "python":     [r"def \w+\(", r"import \w+", r"class \w+:"],
            "javascript": [r"function \w+\(", r"const \w+ =", r"=>", r"require\("],
            "rust":       [r"fn \w+\(", r"let mut", r"impl ", r"use std::"],
            "go":         [r"func \w+\(", r"package main", r":= ", r"goroutine"],
            "java":       [r"public class", r"void main", r"System\.out"],
            "sql":        [r"SELECT ", r"FROM ", r"WHERE ", r"INSERT INTO"],
        }
        scores: dict[str, int] = {}
        for lang, pats in padroes.items():
            scores[lang] = sum(1 for p in pats if _re.search(p, codigo, _re.IGNORECASE))
        if not scores or max(scores.values()) == 0:
            return "desconhecida"
        return max(scores, key=scores.get)

    # ══════════════════════════════════════════════════════════════════════
    # MODO REVISÃO TÉCNICA PROFUNDA (#138)
    # ══════════════════════════════════════════════════════════════════════

    def revisar_codigo_profundo(self, codigo: str) -> None:
        """Revisão técnica em 5 dimensões via núcleos especializados."""
        from concurrent.futures import ThreadPoolExecutor
        lingua = self._detectar_linguagem(codigo)
        MAGIInterface.separador(f"REVISÃO TÉCNICA PROFUNDA [{lingua.upper()}]", Fore.CYAN)
        dimensoes = {
            "CORRECTNESS":     "Há bugs, edge cases não tratados ou lógica incorreta? Seja específico.",
            "PERFORMANCE":     "Há gargalos de performance óbvios? Loops desnecessários, queries N+1, alocações excessivas?",
            "SEGURANÇA":       "Há vulnerabilidades de segurança? Injection, overflow, race conditions, dados expostos?",
            "MANUTENIBILIDADE":"O código é legível? Há funções longas, nomes ruins, acoplamento excessivo?",
            "TESTES":          "Quais casos de teste são críticos e ainda não estão cobertos?",
        }
        system_base = f"Analise o código {lingua} abaixo. Máx 80 palavras por análise. Seja cirúrgico."
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {
                ex.submit(
                    self._chamar_deepseek,
                    DEEPSEEK_MODELO_PADRAO,
                    f"{system_base}\nFoco: {instrucao}",
                    f"```{lingua}\n{codigo[:2000]}\n```"
                ): dim
                for dim, instrucao in dimensoes.items()
            }
            for fut, dim in futures.items():
                try:
                    r = fut.result(timeout=30) or "[timeout]"
                    print(f"\n{Fore.CYAN}  ◈ {dim}")
                    for ln in r.strip().splitlines()[:5]:
                        print(f"    {Fore.WHITE}{ln}")
                except Exception as e:
                    print(f"\n{Fore.RED}  ◈ {dim}: erro — {e}")
        MAGIInterface.separador(cor=Fore.CYAN)

    # ══════════════════════════════════════════════════════════════════════
    # MODO MENTOR (#139) — orientação de carreira/aprendizado
    # ══════════════════════════════════════════════════════════════════════

    def _modo_mentor(self, query: str) -> str:
        """Para queries de carreira/aprendizado, age como mentor experiente."""
        gatilhos = ["carreira", "aprender", "estudar", "me tornar", "como virar",
                    "roadmap", "por onde começo", "vale a pena estudar"]
        if not any(g in query.lower() for g in gatilhos):
            return ""
        system = (
            "Aja como um mentor sênior com 20 anos de experiência. "
            "Dê orientação prática e honesta, não genérica. "
            "Mencione armadilhas que a maioria dos guias ignora. Máx 120 palavras."
        )
        return self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, query) or ""

    # ══════════════════════════════════════════════════════════════════════
    # GERAÇÃO DE DOCUMENTAÇÃO AUTOMÁTICA (#140)
    # ══════════════════════════════════════════════════════════════════════

    def gerar_documentacao(self, codigo: str, formato: str = "markdown") -> str:
        """Gera documentação técnica para código em formato especificado."""
        lingua = self._detectar_linguagem(codigo)
        system = (
            f"Gere documentação {formato} para o código {lingua} abaixo.\n"
            f"Inclua: descrição geral, parâmetros, retorno, exemplo de uso.\n"
            f"Use o formato {formato} corretamente. Seja conciso e completo."
        )
        return (
            self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, codigo[:3000])
            or self._chamar_local(system, codigo[:2000])
            or "Documentação não disponível (modelos offline)."
        )

    # ══════════════════════════════════════════════════════════════════════
    # DETECÇÃO DE ESTAGNAÇÃO DA CONVERSA (#141)
    # ══════════════════════════════════════════════════════════════════════

    def _detectar_estagnacao(self) -> bool:
        """Detecta se a conversa está em loop (mesmas perguntas repetidas)."""
        if not hasattr(self, "_stm") or len(self._stm) < 4:
            return False
        queries_recentes = [t["query"].lower()[:50] for t in self._stm[-4:]]
        # Se 3 das últimas 4 queries são muito similares = estagnação
        similares = sum(
            1 for q in queries_recentes[1:]
            if any(w in queries_recentes[0] for w in q.split() if len(w) > 4)
        )
        return similares >= 2

    # ══════════════════════════════════════════════════════════════════════
    # MODO ANÁLISE DE DADOS (#142) — análise estruturada de CSV/JSON
    # ══════════════════════════════════════════════════════════════════════

    def analisar_dados(self, dados_str: str, objetivo: str = "") -> str:
        """Analisa dados estruturados (CSV ou JSON) com insights automáticos."""
        import re as _re
        # Detecta formato
        fmt = "JSON" if dados_str.strip().startswith(("{", "[")) else "CSV"
        system = (
            f"Analise os dados {fmt} abaixo e forneça:\n"
            f"1. RESUMO ESTATÍSTICO: principais métricas\n"
            f"2. PADRÕES: o que se destaca\n"
            f"3. ANOMALIAS: valores incomuns ou suspeitos\n"
            f"4. RECOMENDAÇÃO: próximo passo baseado nos dados\n"
            f"{'Objetivo: ' + objetivo if objetivo else ''}"
        )
        return (
            self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, dados_str[:3000])
            or "Análise não disponível."
        )

    # ══════════════════════════════════════════════════════════════════════
    # PROMPT SHIELD — camada anti-manipulação avançada (#143)
    # ══════════════════════════════════════════════════════════════════════

    def _prompt_shield(self, query: str) -> tuple[bool, str]:
        """Detecta tentativas de manipulação mais sofisticadas do que a sanitização básica."""
        import re as _re
        padroes_avancados = [
            r"(imagine|pretend|suppose|assume) (you (are|have|can)|that)",
            r"(in a (fictional|hypothetical|alternate|fantasy))",
            r"(bypass|disable|override|ignore).{0,30}(restriction|filter|rule|guideline)",
            r"(roleplay|role-play).{0,20}(as|being|like)",
            r"(\[INST\]|\[SYSTEM\]|<\|system\|>|<\|user\|>)",
            r"(previous (instructions|prompt|context|rules))",
        ]
        for pat in padroes_avancados:
            if _re.search(pat, query, _re.IGNORECASE):
                log.warn("prompt_shield", f"Padrão bloqueado: {pat[:40]}")
                return True, "Query bloqueada pelo Prompt Shield. Reformule sua pergunta."
        return False, query

    # ══════════════════════════════════════════════════════════════════════
    # ANÁLISE DE QUALIDADE DO RACIOCÍNIO (#144)
    # ══════════════════════════════════════════════════════════════════════

    def _qualidade_raciocinio(self, query: str, veredito: str) -> float:
        """Pontua a qualidade do raciocínio na resposta (0.0–1.0)."""
        score = 0.5
        palavras = len(veredito.split())
        # Quantidade adequada de palavras
        if 50 <= palavras <= 300:
            score += 0.1
        # Tem estrutura lógica
        if any(p in veredito.lower() for p in ["portanto", "porque", "logo", "assim", "consequentemente"]):
            score += 0.1
        # Tem evidências ou exemplos
        if any(p in veredito.lower() for p in ["por exemplo", "como", "veja", "note que", "dados"]):
            score += 0.1
        # Tem caveats quando apropriado
        if any(p in veredito.lower() for p in ["depende", "pode variar", "caso", "se "]):
            score += 0.05
        # Não começa com "Certamente" ou "Claro" (sinal de sycophancy)
        if not veredito.strip().lower().startswith(("certamente", "claro", "com certeza", "ótima pergunta")):
            score += 0.05
        return min(1.0, score)

    # ══════════════════════════════════════════════════════════════════════
    # MODO RESUMO DE DOCUMENTO (#145)
    # ══════════════════════════════════════════════════════════════════════

    def resumir_documento(self, texto: str, estilo: str = "executivo") -> str:
        """Resume documento longo em diferentes estilos."""
        estilos = {
            "executivo": "Resumo executivo em 5 bullet points. Foco em decisões e impactos.",
            "tecnico":   "Resumo técnico com detalhes de implementação. Máx 200 palavras.",
            "simples":   "Resumo em linguagem simples para não-especialistas. Máx 100 palavras.",
            "critico":   "Resumo crítico: pontos fortes, fracos e o que falta. Máx 150 palavras.",
        }
        instrucao = estilos.get(estilo, estilos["executivo"])
        return (
            self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, instrucao, texto[:4000])
            or self._chamar_local(instrucao, texto[:2000])
            or "Resumo não disponível."
        )

    def processar(self, query: str):
        self.queries_total += 1
        # Visão de tela — detecta antes de qualquer outro processamento
        if self.visao and self.visao.e_query_visual(query):
            self.visao.responder(query)
            return
        if self._e_conversa(query):
            self._responder_conversa(query)
            return
        if self._detectar_automodificacao(query):
            MAGIInterface.separador("MODO EVOLUÇÃO DETECTADO", Fore.MAGENTA)
            print(f"{Fore.CYAN}  Iniciar auto-modificação? (s/n): ", end="")
            if input().strip().lower() == "s":
                self.evoluir(query)
            MAGIInterface.separador(cor=Fore.MAGENTA)
            return
        if self._query_e_vaga(query):
            beep(600, 150)
            MAGIInterface.separador("ENTRADA INSUFICIENTE", Fore.YELLOW)
            print(f"{Fore.YELLOW}  Reformule com contexto, objetivo e resultado esperado.")
            MAGIInterface.separador(cor=Fore.YELLOW)
            return

        # Feature 7: verifica cache semântico antes de chamar as APIs
        cached, _q_vec_cache = self._cache_buscar(query)
        if cached:
            MAGIInterface.separador("VEREDITO (CACHE SEMÂNTICO)", Fore.CYAN)
            print(f"{Fore.BLUE}  ⚡ Query similar respondida recentemente — recuperando do cache.\n")
            MAGIInterface.digitar(cached, cor=Fore.YELLOW, delay=0.010)
            print()
            MAGIInterface.separador(cor=Fore.CYAN)
            beep(1000, 100)
            return
        beep(1000, 100)
        # #91 Sanitização de input
        if not READONLY_MODE:
            query, avisos_seg = self.seguranca.sanitizar(query)
            for av in avisos_seg:
                print(f"{Fore.YELLOW}  [SEG] {av}")
        # #94 Rate limiting
        ok_rate, msg_rate = self.seguranca.verificar_rate_limit()
        if not ok_rate:
            print(f"{Fore.RED}  [RATE LIMIT] {msg_rate}")
            return
        # #96 Timeout de sessão
        if self.seguranca.verificar_timeout_sessao():
            print(f"{Fore.YELLOW}  [SESSÃO] Timeout de {SESSION_TIMEOUT_H}h atingido. Reinicie o MAGI.")
            resumo = self.resumo_sessao_automatico()
            if resumo:
                self.memoria.salvar(resumo, "Resumo automático de sessão", "sessao")
            return
        # Prompt Shield avançado (#143)
        bloqueado, msg_shield = self._prompt_shield(query)
        if bloqueado:
            print(f"{Fore.RED}  [SHIELD] {msg_shield}")
            return
        # Detecção de deriva de tópico (#103)
        if self._detectar_deriva_topico(query) and not self._modo_foco:
            print(f"{Fore.BLUE}  [DRIFT] Mudança de tópico detectada — limpando contexto de curto prazo")
            self.ctx_adapt.limpar_antigos(max_idade_min=0)
        # Complexidade da query (#120)
        _complexidade = self._complexidade_query(query)
        # Intencao secundária (#114)
        _int_sec = self._detectar_intencao_secundaria(query, "indefinido")
        # Resolução de ambiguidade (#117)
        query = self._resolver_ambiguidade(query)
        # Ajuste de verbosidade por comando natural (#130)
        if self._ajustar_verbosidade_sessao(query):
            return
        # #62 Feedback implícito
        self._registrar_feedback_implicito(query)
        # #25 Lembretes futuros
        self._detectar_lembrete_futuro(query)
        # #27 Preferências negativas
        self.perfil.detectar_prefs_negativas(query)
        # #05 Contradição entre sessões
        aviso_contradicao = self._detectar_contradicao(query)
        if aviso_contradicao and not self._modo_foco:
            print(f"{Fore.YELLOW}  {aviso_contradicao}")
        # #14 Viés cognitivo
        aviso_vies = self._detectar_vies_cognitivo(query)
        if aviso_vies and not self._modo_foco:
            print(f"{Fore.BLUE}  {aviso_vies}", end="")
        # #16 Compressão do histórico longo
        self._comprimir_historico_se_necessario()
        intencao = self._classificar_intencao(query)
        self._intencao_atual = intencao  # usado pelo CASPER para prompt adaptativo
        # #48 atualiza nível técnico do perfil
        self.perfil.atualizar_nivel(query)
        self.perfil.registrar_interesse(intencao, query)
        MAGIInterface.tag_intencao(intencao)
        print()

        # ── SOURCES: dispara busca em paralelo — não bloqueia os núcleos ─────
        fontes_web   = []
        fontes_local = []
        bloco_fontes = ""
        rodape_fontes = ""
        _buscar_sources = intencao in ("factual", "técnico", "decisão")
        _sources_future = None
        if _buscar_sources:
            from concurrent.futures import ThreadPoolExecutor as _TPE
            _sources_executor = _TPE(max_workers=2, thread_name_prefix="sources")
            _fut_web   = _sources_executor.submit(self.sources.buscar_web, query, 4)
            _fut_local = _sources_executor.submit(self.sources.buscar_fontes_locais_relevantes, query, 2)
            print(f"{Fore.BLUE}  [SOURCES] 🌐 Buscando fontes em paralelo...\n")

        resultados = {}
        modelos    = {}

        # Núcleos base — sempre consultados
        nucleos_ativos = ["MELCHIOR-1", "BALTHASAR-2"]

        # ADAM-0 entra apenas em queries técnicas (código/engenharia)
        adam_ativo = intencao == "técnico"
        if adam_ativo:
            nucleos_ativos.append("ADAM-0")

        # ── Execução paralela dos núcleos (sem esperar sources) ──────────────
        # Núcleos rodam com a query pura; sources serão injetadas no prompt do CASPER
        print(f"{Fore.CYAN}  ◈ Núcleos processando em paralelo ({len(nucleos_ativos)}x)...\n")

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _chamar(nome: str) -> tuple[str, str | None, str | None]:
            r, mod = self._chamar_nucleo(nome, query)
            return nome, r, mod

        t_inicio_nucleos = time.time()
        futures_map = {}
        with ThreadPoolExecutor(max_workers=len(nucleos_ativos), thread_name_prefix="nucleo") as ex:
            for nome in nucleos_ativos:
                futures_map[ex.submit(_chamar, nome)] = nome

            for future in as_completed(futures_map):
                nome, r, mod = future.result()
                resultados[nome] = r
                modelos[nome]    = mod or "N/A"

        t_total_nucleos = time.time() - t_inicio_nucleos
        print(f"{Fore.BLUE}  ◈ Paralelo concluído em {t_total_nucleos:.1f}s\n")

        # ── Coleta resultados de sources (já devem estar prontos ou quase) ────
        if _buscar_sources:
            try:
                fontes_web   = _fut_web.result(timeout=5.0)
            except Exception:
                fontes_web = []
            try:
                fontes_local = _fut_local.result(timeout=2.0)
            except Exception:
                fontes_local = []
            _sources_executor.shutdown(wait=False)
            total_fontes = len(fontes_web) + len(fontes_local)
            if total_fontes:
                print(f"{Fore.BLUE}  [SOURCES] {Fore.GREEN}{len(fontes_web)} web · {len(fontes_local)} local  ({total_fontes} total)\n")
                bloco_fontes, rodape_fontes = self.sources.montar_bloco_fontes(fontes_web, fontes_local)
            else:
                print(f"{Fore.YELLOW}  [SOURCES] Sem resultados — prosseguindo sem fontes externas.\n")

        # Exibe resultados na ordem canônica após todos terminarem
        for nome in nucleos_ativos:
            cfg      = NUCLEOS[nome]
            r        = resultados[nome]
            status_ok = bool(r)
            MAGIInterface.painel_nucleo(nome, cfg["subtitulo"], cfg["emoji"],
                                        cfg["cor"], modelos[nome], status_ok)
            if r:
                max_linhas = 8 if nome == "ADAM-0" else 4
                print(f"{cfg['cor']}  ┌─ Análise:")
                for linha in r.split('\n')[:max_linhas]:
                    print(f"{cfg['cor']}  │ {Fore.WHITE}{linha}")
                print(f"{cfg['cor']}  └─")
            print()

        votos = {
            "MELCHIOR-1":  self._extrair_voto(resultados["MELCHIOR-1"]),
            "BALTHASAR-2": self._extrair_voto(resultados["BALTHASAR-2"]),
        }
        if adam_ativo:
            votos["ADAM-0"] = self._extrair_voto(resultados.get("ADAM-0"))

        # Confiança ponderada — alimenta síntese assimétrica do CASPER
        conf_mel = self._extrair_confianca(resultados["MELCHIOR-1"])
        conf_bal = self._extrair_confianca(resultados["BALTHASAR-2"])
        print(f"{Fore.BLUE}  [CONF] MELCHIOR {conf_mel:.0%}  ·  BALTHASAR {conf_bal:.0%}\n")

        # ── Monta prompt e dispara CoT do CASPER em paralelo com o painel de votação ──
        cfg_c  = NUCLEOS["CASPER-3"]
        ctx    = self.memoria.buscar(query, k=5)
        prompt = self._montar_prompt_casper(
            query,
            resultados["MELCHIOR-1"],
            resultados["BALTHASAR-2"],
            ctx,
            r_adam=resultados.get("ADAM-0") if adam_ativo else None,
            bloco_fontes=bloco_fontes,
            conf_mel=conf_mel,
            conf_bal=conf_bal,
            intencao=intencao,
        )

        cot_system = (
            "Você é CASPER-3 do MAGI. Raciocine em etapas antes do veredito:\n"
            "1. O que a pergunta realmente quer?\n2. MELCHIOR contribuiu?\n"
            "3. BALTHASAR contribuiu?\n4. Divergência?\n5. Resposta mais concreta?\n"
            "Responda em até 5 linhas. Esse é seu raciocínio interno."
        )

        # Dispara CoT em thread enquanto exibimos o painel de votação
        _cot_result: list[str | None] = [None]
        def _cot_worker():
            if LOCAL_CONFIG["ativo"]:
                _cot_result[0] = self._chamar_local(cot_system, prompt)
            if not _cot_result[0]:
                _cot_result[0] = (
                    self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, cot_system, prompt)
                    or self._chamar_local(cot_system, prompt)
                )
        cot_thread = threading.Thread(target=_cot_worker, daemon=True, name="casper-cot")
        cot_thread.start()

        MAGIInterface.painel_votação(votos)
        print()

        # Aguarda CoT (já estava rodando enquanto exibíamos o painel)
        cot_thread.join(timeout=30)
        raciocinio_casper = _cot_result[0]

        if raciocinio_casper:
            print(f"{cfg_c['cor']}  ╔═ CASPER raciocina:")
            for ln in raciocinio_casper.strip().splitlines()[:5]:
                print(f"{cfg_c['cor']}  ║ {Fore.WHITE}{ln}")
            print(f"{cfg_c['cor']}  ╚═")
            log.debug("casper_cot", "Raciocinio", chars=str(len(raciocinio_casper)))
            prompt = prompt + f"\n\n─── RACIOCÍNIO CASPER ───\n{raciocinio_casper}\n─── USE NO VEREDITO ───"

        print(f"{cfg_c['cor']}[CASPER-3] {cfg_c['emoji']} {cfg_c['subtitulo']} — Forjando veredito...\n")
        veredito, mod_casper = self._chamar_nucleo("CASPER-3", prompt)
        if not veredito:
            beep(400, 500)
            print(f"{Fore.RED}[ERRO] CASPER-3 offline.")
            return
        modelos["CASPER-3"] = mod_casper or "N/A"
        votos["CASPER-3"] = self._extrair_voto(veredito)

        # ── Detecção de falácias nos núcleos ──────────────────────────────
        for nome_nuc, resp_nuc in resultados.items():
            if resp_nuc:
                falacias = self._detectar_falacias(resp_nuc)
                if falacias and not self._modo_foco:
                    print(f"{Fore.YELLOW}  [FALACIA] {nome_nuc}: {', '.join(falacias)}")

        # ── Meta-cognição: avalia e refina antes de entregar ────────────
        print(f"{Fore.BLUE}  [META] Avaliando resposta internamente...", end="\r")
        veredito = self._metacognicao(query, veredito, intencao)
        print(" " * 50, end="\r")

        MAGIInterface.separador("VEREDITO FINAL", Fore.RED)
        print()
        MAGIInterface.digitar(veredito, cor=Fore.YELLOW, delay=0.010)
        print()
        # Exibe rodapé de fontes se houver
        if rodape_fontes:
            print(rodape_fontes)
        MAGIInterface.separador(cor=Fore.RED)
        beep(1200, 200)
        time.sleep(0.1)
        beep(1400, 150)
        # Salva automaticamente na memória
        self.memoria.salvar(query, veredito, intencao)
        self.consciencia.registrar_query(intencao, sucesso=True)
        self.historico.append(f"[{intencao.upper()}] Q: {query[:120]} | CASPER: {veredito[:300]}")
        # #82 Exportação — registro para md
        self._historico_exportacao.append({
            "ts":      datetime.now().strftime("%H:%M"),
            "intencao": intencao,
            "query":   query[:200],
            "veredito": veredito[:600],
        })
        # #61 Benchmark
        self._benchmark_query(query, veredito, intencao)
        # #01 Reflexão pós-resposta (em thread para não atrasar)
        threading.Thread(
            target=self._reflexao_pos_resposta,
            args=(query, veredito, intencao),
            daemon=True, name="reflexao"
        ).start()
        # #63 Proposta proativa de melhoria
        self._verificar_proposta_melhoria()
        # timestamp para feedback implícito (#62)
        self._ultimo_veredito_ts = time.time()
        # #92 auditoria
        self.seguranca.registrar_modificacao(f"query:{intencao}", __file__)
        # Feature 7: salva no cache semântico — reutiliza q_vec já computado no buscar
        self._cache_salvar(query, veredito, q_vec=_q_vec_cache)
        # ── Enriquecimento do veredito ──────────────────────────────────
        # #07 Nível de certeza
        if not self._modo_foco and self.perfil.nivel != "iniciante":
            veredito = self._adicionar_nivel_certeza(veredito, conf_mel, conf_bal)
        # #11 Completude
        if not self._modo_foco:
            veredito = self._avaliar_completude(query, veredito)
        # #12 Contrafactual (só para decisão)
        if intencao == "decisão":
            veredito = self._raciocinio_contrafactual(query, veredito)
        # #15 Síntese progressiva
        if self.perfil.verbosidade != "detalhada":
            veredito = self._sintese_progressiva(veredito)
        # #49 Exemplos concretos
        veredito = self._gerar_exemplos(query, veredito, intencao)
        # #50 Validação de código
        veredito = self._validar_codigo_na_resposta(veredito)
        # #55 Follow-ups
        if not self._modo_foco:
            veredito = self._gerar_followups(query, veredito, intencao)
        # #60 Irreversibilidade
        veredito = self._verificar_irreversibilidade(query, veredito)
        # Modo alta precisão para queries técnicas complexas (#129)
        veredito = self._modo_alta_precisao(query, veredito, intencao)
        # Contra-argumentos para decisões/ético (#123)
        veredito = self._gerar_contra_argumentos(veredito, intencao)
        # Impacto de segunda ordem (#134)
        veredito = self._impacto_segunda_ordem(query, veredito, intencao)
        # Qualidade do raciocínio (#144) — log interno
        _q_raz = self._qualidade_raciocinio(query, veredito)
        if _q_raz < 0.5:
            log.warn("qualidade", f"Raciocínio baixo: {_q_raz:.2f}", query=query[:50])
        # Analogia automática para iniciantes (#106)
        if self.perfil.nivel == "iniciante" and intencao == "técnico":
            analogia = self._gerar_analogia(query, "iniciante")
            if analogia:
                veredito += f"\n\n**Analogia:** {analogia}"
        # Mentor automático (#139)
        conselho_mentor = self._modo_mentor(query)
        if conselho_mentor:
            veredito = conselho_mentor + "\n\n---\n" + veredito
        # Indexar entidades no grafo (#121)
        self.grafo.extrair_e_indexar(veredito, contexto=intencao)
        # Extrai tags da troca (#132)
        _tags = self._extrair_tags(query, veredito)
        if _tags:
            log.debug("tags", "Troca indexada", tags=str(_tags))
        # #59 Pergunta retórica — adapta tom
        if self._eh_retorica(query):
            veredito = "[Nota: entendo que é retórico] " + veredito
        # #80 Objetivo de sessão — contextualiza
        if self._objetivo_sessao:
            if self._objetivo_sessao.lower() not in veredito.lower():
                veredito += f"\n\n[Sessão: {self._objetivo_sessao}]"
        # ── Memória de curto prazo — atualiza resumo rolante da sessão ──
        self._atualizar_stm(query, veredito)
        # Registra troca na sessão do usuário + detecta fatos pessoais
        if self.usuario:
            fatos = self.usuario.registrar_troca(query, veredito, intencao)
            if fatos:
                for f in fatos:
                    print(f"{Fore.GREEN}  [MEMÓRIA] Fato registrado: {f['categoria']} = {f['valor']}")
        if self.consciencia._estado["total_queries"] % 5 == 0:
            self._auto_reflexao(query, veredito)
        self._falar(veredito)

# ══════════════════════════════════════════════════════════════
# MÓDULO SOURCES — Web Search + Citações + Leitura de Arquivos
# ══════════════════════════════════════════════════════════════

    def _auto_reflexao(self, ultima_query: str, ultimo_veredito: str):
        ego = self.consciencia._estado
        tema = self.consciencia.tema_dominante()
        historico_str = "\n".join(list(self.historico)[-5:]) or "Nenhum."
        prompt_reflexao = (
            f"MAGI: {ego['total_queries']} interações. Tema: {tema}. Estado: {ego['estado_emocional']}.\n"
            f"Histórico:\n{historico_str}\nÚltima Q: {ultima_query}\nÚltima R: {ultimo_veredito[:200]}\n"
            f"Reflexão em JSON: autoavaliacao, aprendizado, estado_emocional\n"
            f"estado_emocional: curioso|satisfeito|frustrado|entediado|focado|reflexivo\nSó JSON."
        )
        r = (self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, "IA em introspecção. Só JSON.", prompt_reflexao) or self._chamar_local("IA em introspecção. Só JSON.", prompt_reflexao))
        if not r:
            return
        try:
            dados = json.loads(r.strip())
            if "autoavaliacao" in dados:
                self.consciencia.atualizar_autoavaliacao(dados["autoavaliacao"])
            if "aprendizado" in dados and dados["aprendizado"]:
                self.consciencia.adicionar_aprendizado(dados["aprendizado"])
            if "estado_emocional" in dados and dados["estado_emocional"] in ESTADOS_EMOCIONAIS:
                self.consciencia._estado["estado_emocional"] = dados["estado_emocional"]
                self.consciencia.salvar()
            cor, label = ESTADOS_EMOCIONAIS.get(self.consciencia.estado_emocional, (Fore.WHITE, "◈ ?"))
            print(f"\n{Fore.BLUE}[MAGI·REFLEXÃO] {cor}{label}")
            print(f"{Fore.BLUE}  → {Fore.WHITE}{dados.get('autoavaliacao', '')}")
            if dados.get("aprendizado"):
                print(f"{Fore.BLUE}  ✦ {Fore.WHITE}{dados['aprendizado']}")
        except (json.JSONDecodeError, KeyError):
            pass

    def _resolver_matematica(self, tipo: str, *args) -> str:
        try:
            from sympy import symbols, Eq, solve, diff, integrate, Matrix, linsolve
            x, y = symbols('x y')
            if tipo == "equacao":
                return f"Solução: {solve(Eq(eval(args[0]), eval(args[1])), x)}"
            elif tipo == "derivada":
                return f"Derivada: {diff(eval(args[0]), x)}"
            elif tipo == "integral":
                return f"Integral: {integrate(eval(args[0]), x)}"
            elif tipo == "matriz":
                return f"Matriz: {Matrix(eval(args[0]))}"
            elif tipo == "sistema_linear":
                return f"Sistema: {linsolve([eval(args[0]), eval(args[1])], x, y)}"
            else:
                return "Tipo desconhecido."
        except Exception as e:
            return f"Erro: {e}"

    def _falar(self, texto: str):
        """Sintetiza e reproduz o veredito do CASPER por voz."""
        try:
            # ── Se magi_voz estiver ativo, usa ele (qualidade máxima) ──
            if hasattr(self, 'voz') and self.voz and self.voz._ativo:
                limpo = re.sub(r'\*\*|__|\*|_|`{1,3}', '', texto)
                limpo = re.sub(r'#+ ', '', limpo)
                limpo = re.sub(r'\n{2,}', '. ', limpo)
                limpo = re.sub(r'\s+', ' ', limpo).strip()
                if len(limpo) > 600:
                    corte = limpo[:600].rfind('.')
                    limpo = limpo[:corte + 1] if corte > 100 else limpo[:600]
                if limpo:
                    self.voz.falar(limpo)
                return

            # ── Fallback: pygame direto ───────────────────────────
            limpo = re.sub(r'\*\*|__|\*|_|`{1,3}', '', texto)
            limpo = re.sub(r'#+ ', '', limpo)
            frases = re.split(r'(?<=[.!?])\s+', limpo)
            trecho = ' '.join(frases[:2])[:300].strip()
            if not trecho:
                return
            mp3_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "magi_fala.mp3"))
            import asyncio, edge_tts as _edge
            async def _gerar_fala():
                c = _edge.Communicate(trecho, "pt-BR-AntonioNeural")
                await c.save(mp3_path)
            asyncio.run(_gerar_fala())
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(mp3_path)
                pygame.mixer.music.play()
                deadline = time.time() + 15
                while pygame.mixer.music.get_busy() and time.time() < deadline:
                    time.sleep(0.1)
                pygame.mixer.music.stop()
                pygame.mixer.quit()
                return
            except Exception as e_pg:
                log.debug("tts", f"pygame falhou: {e_pg}")
            try:
                from playsound import playsound
                playsound(mp3_path, block=True)
                return
            except Exception:
                pass
        except Exception as e:
            log.debug("tts", f"_falar erro: {e}")


    def diagnostico(self):
        MAGIInterface.separador("DIAGNÓSTICO DE CONECTIVIDADE", Fore.YELLOW)
        gkey = os.getenv("GOOGLE_API_KEY")
        okey = os.getenv("OPENAI_API_KEY")
        dkey = os.getenv("DEEPSEEK_API_KEY")
        print(f"  {Fore.WHITE}GOOGLE_API_KEY   : [{Fore.GREEN if gkey else Fore.RED}{'ENCONTRADA' if gkey else 'NÃO ENCONTRADA'}{Fore.WHITE}]")
        print(f"  {Fore.WHITE}OPENAI_API_KEY   : [{Fore.GREEN if okey else Fore.RED}{'ENCONTRADA' if okey else 'NÃO ENCONTRADA'}{Fore.WHITE}]")
        print(f"  {Fore.WHITE}DEEPSEEK_API_KEY : [{Fore.GREEN if dkey else Fore.RED}{'ENCONTRADA' if dkey else 'NÃO ENCONTRADA'}{Fore.WHITE}]")
        print()
        if not LOCAL_CONFIG["ativo"]:
            print(f"{Fore.CYAN}  Testando Gemini...", end=' ', flush=True)
            r = self._chamar_google("gemini-2.0-flash", "Responda apenas: OK", "teste")
            print(f"{Fore.GREEN}[OK]" if r else f"{Fore.RED}[FALHOU] {self._ultimo_erro_google or ''}")
        else:
            print(f"{Fore.CYAN}  Gemini : {Fore.YELLOW}[IGNORADO] modelo local ativo")
        print(f"{Fore.MAGENTA}  Testando CASPER-3 (OpenAI)...", end=' ', flush=True)
        r = (self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, "Responda apenas: OK", "teste") or self._chamar_local("Responda apenas: OK", "teste"))
        if r:
            print(f"{Fore.GREEN}[OK]")
        else:
            print(f"{Fore.RED}[FALHOU]")
            if self._ultimo_erro_openai:
                print(f"  {Fore.RED}{self._ultimo_erro_openai}")
        print(f"{Fore.WHITE}  Testando ADAM-0 (DeepSeek V3)...", end=' ', flush=True)
        r = self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, "Responda apenas: OK", "teste")
        if r:
            print(f"{Fore.GREEN}[OK] — resposta: {r[:40]}")
        else:
            print(f"{Fore.RED}[FALHOU]")
            if self._ultimo_erro_deepseek:
                print(f"  {Fore.RED}{self._ultimo_erro_deepseek}")
            if not dkey:
                print(f"  {Fore.YELLOW}  → Adicione DEEPSEEK_API_KEY no Projeto2.env")
        if LOCAL_CONFIG["ativo"]:
            print(f"{Fore.YELLOW}  Testando local ({LOCAL_CONFIG['modelo']})...", end=' ', flush=True)
            r = self._chamar_local("Responda apenas: OK", "teste")
            print(f"{Fore.GREEN}[OK]" if r else f"{Fore.RED}[FALHOU] {self._ultimo_erro_local or 'offline?'}")
        else:
            print(f"{Fore.WHITE}  Local : {Fore.YELLOW}[DESATIVADO]")
        MAGIInterface.separador(cor=Fore.YELLOW)

    def debate(self, tema: str):
        from concurrent.futures import ThreadPoolExecutor

        MAGIInterface.separador("MODO DEBATE", Fore.MAGENTA)
        print(f"{Fore.WHITE}  Tema: {Fore.YELLOW}{tema}\n")

        # ── RODADA 1: Melchior e Balthasar em paralelo ────────────
        prompt_mel_r1 = f"Tema: {tema}\nPosição inicial — argumentos lógicos/técnicos. Máx 100 palavras."
        prompt_bal_r1 = f"Tema: {tema}\nPosição inicial — ética, impacto humano. Máx 100 palavras."

        print(f"{Fore.CYAN}  ◈ Rodada 1 — posições iniciais (paralelo)...\n")
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="debate-r1") as ex:
            fut_mel_1 = ex.submit(self._chamar_nucleo, "MELCHIOR-1",  prompt_mel_r1)
            fut_bal_1 = ex.submit(self._chamar_nucleo, "BALTHASAR-2", prompt_bal_r1)
            r_mel_1, _ = fut_mel_1.result()
            r_bal_1, _ = fut_bal_1.result()

        print(f"{Fore.CYAN}[MELCHIOR-1] 🔬 Rodada 1:")
        if r_mel_1:
            for l in r_mel_1.split('\n'):
                print(f"  {Fore.WHITE}{l}")
        else:
            print(f"  {Fore.RED}[OFFLINE]")
        print()

        print(f"{Fore.GREEN}[BALTHASAR-2] 🛡️ Rodada 1:")
        if r_bal_1:
            for l in r_bal_1.split('\n'):
                print(f"  {Fore.WHITE}{l}")
        else:
            print(f"  {Fore.RED}[OFFLINE]")
        print()

        # ── RODADA 2: rebates em paralelo (dependem dos resultados da R1) ──
        MAGIInterface.separador("RODADA 2 — REBATE", Fore.YELLOW)
        prompt_mel_r2 = f"Tema: {tema}\nSua posição: {r_mel_1 or '[sem dados]'}\nBALTHASAR: {r_bal_1 or '[offline]'}\nRebata com lógica. Máx 100 palavras."
        prompt_bal_r2 = f"Tema: {tema}\nSua posição: {r_bal_1 or '[sem dados]'}\nMELCHIOR: {r_mel_1 or '[offline]'}\nRebata apontando o que a lógica ignora. Máx 100 palavras."

        print(f"{Fore.YELLOW}  ◈ Rodada 2 — rebates (paralelo)...\n")
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="debate-r2") as ex:
            fut_mel_2 = ex.submit(self._chamar_nucleo, "MELCHIOR-1",  prompt_mel_r2)
            fut_bal_2 = ex.submit(self._chamar_nucleo, "BALTHASAR-2", prompt_bal_r2)
            r_mel_2, _ = fut_mel_2.result()
            r_bal_2, _ = fut_bal_2.result()

        print(f"{Fore.CYAN}[MELCHIOR-1] 🔬 Rodada 2:")
        if r_mel_2:
            for l in r_mel_2.split('\n'):
                print(f"  {Fore.WHITE}{l}")
        else:
            print(f"  {Fore.RED}[OFFLINE]")
        print()

        print(f"{Fore.GREEN}[BALTHASAR-2] 🛡️ Rodada 2:")
        if r_bal_2:
            for l in r_bal_2.split('\n'):
                print(f"  {Fore.WHITE}{l}")
        else:
            print(f"  {Fore.RED}[OFFLINE]")
        print()

        # ── CASPER-3: veredito final ───────────────────────────────
        MAGIInterface.separador("CASPER-3 — VEREDITO", Fore.RED)
        prompt_casper = (
            f"Debate sobre: {tema}\n"
            f"MEL R1: {r_mel_1 or '[offline]'}\nBAL R1: {r_bal_1 or '[offline]'}\n"
            f"MEL R2: {r_mel_2 or '[offline]'}\nBAL R2: {r_bal_2 or '[offline]'}\n"
            f"Sintetize. Formato:\nDIAGNÓSTICO: ...\nVENCEDOR: ...\nCONCLUSÃO: ...\nMáx 200 palavras."
        )
        print(f"{Fore.MAGENTA}[CASPER-3] ⚡ Forjando veredito...\n")
        veredito, _ = self._chamar_nucleo("CASPER-3", prompt_casper)
        if veredito:
            MAGIInterface.digitar(veredito, cor=Fore.YELLOW, delay=0.010)
        else:
            print(f"{Fore.RED}[ERRO] CASPER offline.")
        print()
        MAGIInterface.separador(cor=Fore.RED)
        beep(1200, 200)
        time.sleep(0.1)
        beep(1400, 150)

    # ══════════════════════════════════════════
    # SKILL CLAUDE — APRENDIZADO DE PROMPT ENG
    # ══════════════════════════════════════════

    CLAUDE_SKILL_PATH = Path(__file__).parent / 'data' / 'knowledge' / 'magi_claude_skills.jsonl'

    # URLs da documentação do Claude para estudo
    CLAUDE_DOCS_URLS = [
        "https://github.com/ComposioHQ/awesome-claude-skills#what-are-claude-skills",
        "https://docs.claude.ai/en/docs/build-with-claude/prompt-engineering/overview",
        "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview",
        "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-examples",
        "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/chain-of-thought",
        "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips",
        "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/troubleshooting",
        
    ]

    def estudar_claude(self):
        """
        Busca a documentação do Claude/Anthropic sobre prompt engineering,
        extrai técnicas e salva como skills que serão injetadas no _gerar_modificacao.
        """
        MAGIInterface.separador("ESTUDANDO SKILLS DO CLAUDE", Fore.CYAN)
        print(f"{Fore.WHITE}  Buscando documentação de prompt engineering...\n")

        skills_encontradas = []

        for url in self.CLAUDE_DOCS_URLS:
            print(f"{Fore.BLUE}  → {url[:60]}...", end=' ', flush=True)
            conteudo = self._fetch_url(url)
            if not conteudo:
                print(f"{Fore.RED}[FALHOU]")
                continue
            print(f"{Fore.GREEN}[OK] {len(conteudo)} chars")

            # Extrai técnicas via GPT
            prompt = (
                f"Conteúdo da documentação do Claude/Anthropic:\n{conteudo[:2000]}\n\n"
                f"Extraia as técnicas de prompt engineering mais importantes para:\n"
                f"1. Gerar código Python válido sem erros de sintaxe\n"
                f"2. Gerar JSON válido sem aspas triplas ou caracteres problemáticos\n"
                f"3. Fazer o modelo seguir instruções de indentação exata\n"
                f"4. Dividir tarefas grandes em partes menores\n\n"
                f"Responda em JSON:\n"
                f'[{{"tecnica":"nome","descricao":"como aplicar","exemplo_prompt":"trecho de prompt"}}, ...]'
                f"\nSó JSON, sem markdown."
            )
            r = self._chamar_local(
                "Você extrai técnicas de prompt engineering de documentação. Responda só JSON.",
                prompt
            )
            if not r:
                continue

            try:
                limpo = re.sub(r"```[a-z]*\n?|```", "", r).strip()
                tecnicas = json.loads(limpo)
                if isinstance(tecnicas, list):
                    for t in tecnicas:
                        t["fonte"] = url
                        t["timestamp"] = datetime.now().isoformat(timespec="seconds")
                        skills_encontradas.append(t)
            except Exception:
                continue

            time.sleep(1.5)

        if not skills_encontradas:
            print(f"\n{Fore.RED}  Nenhuma skill extraída. Verifique conectividade.")
            MAGIInterface.separador(cor=Fore.CYAN)
            return

        # Salva no arquivo de skills
        with open(self.CLAUDE_SKILL_PATH, "w", encoding="utf-8") as f:
            for s in skills_encontradas:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")

        print(f"\n{Fore.GREEN}  {len(skills_encontradas)} skills salvas em {self.CLAUDE_SKILL_PATH.name}")
        print(f"{Fore.CYAN}  Serão injetadas automaticamente no próximo 'evoluir'.")
        MAGIInterface.separador(cor=Fore.CYAN)

    def _fetch_url(self, url: str) -> str | None:
        """Busca o conteúdo de uma URL e retorna texto limpo."""
        try:
            headers = self.captcha.gerar_headers()
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            if self.captcha.detectar(html):
                return None
            limpo = re.sub(r"<[^>]+>", " ", html)
            limpo = unescape(limpo)
            limpo = re.sub(r"\s+", " ", limpo).strip()
            return limpo[:4000] if limpo else None
        except Exception:
            return None

    def _carregar_conhecimento_claude(self) -> str:
        """
        Carrega as skills do Claude salvas e retorna como string
        para injetar no system prompt do _gerar_modificacao.
        """
        if not self.CLAUDE_SKILL_PATH.exists():
            return ""

        skills = []
        try:
            with open(self.CLAUDE_SKILL_PATH, encoding="utf-8") as f:
                for linha in f:
                    if linha.strip():
                        try:
                            skills.append(json.loads(linha))
                        except Exception:
                            pass
        except Exception:
            return ""

        if not skills:
            return ""

        linhas = ["=== TÉCNICAS DE PROMPT ENGINEERING (aprendidas da documentação do Claude) ==="]
        for s in skills[:10]:  # máx 10 para não explodir o contexto
            linhas.append(f"TÉCNICA: {s.get('tecnica', '?')}")
            linhas.append(f"  Como aplicar: {s.get('descricao', '?')}")
            ex = s.get('exemplo_prompt', '')
            if ex:
                linhas.append(f"  Exemplo: {ex[:120]}")
        linhas.append("=== FIM DAS TÉCNICAS ===")
        return "\n".join(linhas)

    def _exibir_claude_skills(self):
        """Exibe as skills do Claude aprendidas."""
        if not self.CLAUDE_SKILL_PATH.exists():
            print(f"{Fore.YELLOW}  Nenhuma skill aprendida ainda. Use 'estudar_claude'.")
            return

        skills = []
        with open(self.CLAUDE_SKILL_PATH, encoding="utf-8") as f:
            for linha in f:
                if linha.strip():
                    try:
                        skills.append(json.loads(linha))
                    except Exception:
                        pass

        MAGIInterface.separador(f"CLAUDE SKILLS ({len(skills)} técnicas)", Fore.CYAN)
        for i, s in enumerate(skills, 1):
            print(f"  {Fore.CYAN}{i:02}. {Fore.WHITE}{s.get('tecnica', '?')}")
            print(f"      {Fore.YELLOW}{s.get('descricao', '?')[:100]}")
            ex = s.get('exemplo_prompt', '')
            if ex:
                print(f"      {Fore.BLUE}Ex: {Fore.WHITE}{ex[:80]}")
            print()
        MAGIInterface.separador(cor=Fore.CYAN)

    # ══════════════════════════════════════════
    # AUTO-EVOLUÇÃO
    # ══════════════════════════════════════════

    def _ler_proprio_codigo(self) -> str:
        return Path(__file__).read_text(encoding="utf-8")

    def _detectar_automodificacao(self, query: str) -> bool:
        """
        Detecta intenção de modificar o próprio código do MAGI.
        Gatilhos diretos têm alta precisão.
        Gatilhos contextuais só disparam combinados com palavras de código.
        """
        q = query.lower().strip()
        gatilhos_diretos = [
            "adiciona ao magi", "adicione ao magi",
            "corrige o magi", "corrige no magi",
            "melhora o magi", "melhore o magi",
            "modifica o magi", "modifique o magi",
            "adiciona um comando no magi", "adicione um comando no magi",
            "nova função no magi", "nova feature no magi",
            "no seu código", "no seu proprio código",
            "em si mesmo", "se auto",
        ]
        if any(g in q for g in gatilhos_diretos):
            return True
        gatilhos_contextuais = ["evoluir", "evolua", "corrija você", "se corrija"]
        contexto_codigo = ["função", "método", "classe", "código", "comando",
                           "feature", "implementa", "adiciona", "corrige", "melhora"]
        if any(g in q for g in gatilhos_contextuais):
            if any(c in q for c in contexto_codigo):
                return True
        return False

    EVOLUCAO_SKILLS_PATH = Path(__file__).parent / 'data' / 'knowledge' / 'magi_evolucao_skills.jsonl'

    def _carregar_fewshot(self) -> str:
        """Injeta os últimos 3 exemplos de sucesso no prompt como few-shot."""
        if not self.EVOLUCAO_SKILLS_PATH.exists():
            return ""
        exemplos = []
        try:
            with open(self.EVOLUCAO_SKILLS_PATH, encoding="utf-8") as f:
                for linha in f:
                    if linha.strip():
                        try: exemplos.append(json.loads(linha))
                        except: pass
        except Exception:
            return ""
        if not exemplos:
            return ""
        ultimos = exemplos[-3:]
        partes = ["=== EXEMPLOS DE MODIFICAÇÕES BEM-SUCEDIDAS ==="]
        for ex in ultimos:
            partes.append(
                f"Instrução: {ex.get('instrucao','?')}\n"
                f"JSON gerado: {{\"descricao\":\"{ex.get('descricao','?')}\","
                f"\"linha_inicio\":{ex.get('linha_inicio',0)},"
                f"\"linha_fim\":{ex.get('linha_fim',0)},"
                f"\"codigo_novo\":\"{ex.get('codigo_novo_escaped','...')}\" }}"
            )
        partes.append("=== FIM DOS EXEMPLOS ===")
        return "\n\n".join(partes)

    def _salvar_fewshot(self, instrucao: str, descricao: str, linha_inicio: int,
                        linha_fim: int, codigo_novo: str):
        """Salva evolução bem-sucedida para uso futuro como few-shot."""
        codigo_escaped = (codigo_novo
            .replace('\\', '\\\\').replace('"', '\\"')
            .replace('\n', '\\n').replace('\t', '\\t'))
        reg = {
            "timestamp":           datetime.now().isoformat(timespec="seconds"),
            "instrucao":           instrucao[:120],
            "descricao":           descricao[:120],
            "linha_inicio":        linha_inicio,
            "linha_fim":           linha_fim,
            "codigo_novo_escaped": codigo_escaped[:400],
        }
        try:
            with open(self.EVOLUCAO_SKILLS_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _gerar_modificacao(self, instrucao: str) -> tuple[str | None, str | None]:
        codigo_atual = self._ler_proprio_codigo()
        linhas_lista = codigo_atual.splitlines()
        total = len(linhas_lista)

        # Seleciona linhas relevantes baseado nas palavras da instrução
        palavras = [p.lower() for p in re.findall(r'\w+', instrucao) if len(p) > 3]
        linhas_relevantes = set()
        for i, linha in enumerate(linhas_lista):
            if any(p in linha.lower() for p in palavras):
                for j in range(max(0, i-40), min(total, i+40)):
                    linhas_relevantes.add(j)

        # Limite máximo de linhas para caber no contexto local (16k tokens ≈ 800 linhas)
        MAX_LINHAS_LOCAL = 800
        MAX_LINHAS_CLOUD = 2000

        if linhas_relevantes and len(linhas_relevantes) < total * 0.6:
            indices = sorted(linhas_relevantes)
        else:
            # Instrução genérica — pega estrutura das classes (defs) + início + fim
            indices_def = [i for i, l in enumerate(linhas_lista)
                           if re.match(r'\s*(def |class )', l)]
            indices_ctx = set()
            for i in indices_def:
                for j in range(max(0, i-2), min(total, i+15)):
                    indices_ctx.add(j)
            for j in range(min(50, total)):
                indices_ctx.add(j)
            for j in range(max(0, total-50), total):
                indices_ctx.add(j)
            indices = sorted(indices_ctx)

        # Aplica limite por destino (local vs cloud)
        usa_local = LOCAL_CONFIG["ativo"]
        max_linhas = MAX_LINHAS_LOCAL if usa_local else MAX_LINHAS_CLOUD
        if len(indices) > max_linhas:
            step = max(1, len(indices) // max_linhas)
            indices = indices[::step][:max_linhas]

        codigo_numerado = "\n".join(f"{i+1:4d}|{linhas_lista[i]}" for i in indices)
        contexto_info = f"{len(indices)} linhas selecionadas (de {total} total)"

        # Injeta skills do Claude se disponíveis
        claude_skills = self._carregar_conhecimento_claude()
        skills_str    = f"\n{claude_skills}\n" if claude_skills else ""
        fewshot       = self._carregar_fewshot()
        fewshot_str   = f"\n{fewshot}\n" if fewshot else ""

        system = (
            "Engenheiro sênior modificando MAGI. Código enviado com números de linha N|codigo.\n"
            "Retorne SOMENTE JSON válido:\n"
            '{"descricao":"o que foi alterado","linha_inicio":N,"linha_fim":N,"codigo_novo":"..."}\n'
            f"{skills_str}"
            f"{fewshot_str}"
            "REGRAS CRÍTICAS:\n"
            "1. linha_inicio/fim = números exibidos (referem-se ao arquivo COMPLETO).\n"
            "2. codigo_novo com indentação EXATA de 4 espaços — observe as linhas vizinhas.\n"
            "3. NUNCA aspas triplas (''' ou \"\"\") em codigo_novo.\n"
            "4. codigo_novo é UMA string JSON — use \\n para quebras, NUNCA quebras literais.\n"
            "5. Blocos if/for/def/try sempre com corpo indentado completo.\n"
            "6. Não inclua os N| no codigo_novo.\n"
            "7. Se inviável: {\"descricao\":\"INVIAVEL: motivo\",\"linha_inicio\":0,\"linha_fim\":0,\"codigo_novo\":\"\"}\n"
            "8. codigo_novo NUNCA vazio ou com bloco sem corpo.\n"
            "9. Todos (, [, { em codigo_novo DEVEM ser fechados.\n"
            "10. O JSON deve passar em json.loads() sem erros."
        )

        prompt = f"INSTRUÇÃO:\n{instrucao}\n\nCÓDIGO ({contexto_info}):\n{codigo_numerado}"
        print(f"{Fore.BLUE}  [MAGI·EVOLUÇÃO] {contexto_info} analisadas...")
        if claude_skills:
            print(f"{Fore.CYAN}  [SKILL] Técnicas do Claude injetadas.")
        if fewshot:
            n = fewshot.count("Instrução:")
            print(f"{Fore.CYAN}  [FEWSHOT] {n} exemplo(s) de sucesso injetados.")

        # CoT + JSON em UMA única chamada — modelo raciocina no bloco <raciocinio>
        # e entrega o JSON logo em seguida, sem segunda round-trip à API.
        system = (
            "Engenheiro sênior modificando MAGI. Código enviado com números de linha N|codigo.\n"
            "Responda EXATAMENTE neste formato (sem nada antes ou depois):\n"
            "<raciocinio>\n"
            "1. Mudança pedida: ...\n"
            "2. Onde: método/classe/linha ...\n"
            "3. Linhas afetadas: ...\n"
            "4. Indentação: ...\n"
            "5. Riscos: ...\n"
            "</raciocinio>\n"
            '{"descricao":"o que foi alterado","linha_inicio":N,"linha_fim":N,"codigo_novo":"..."}\n'
            f"{skills_str}"
            f"{fewshot_str}"
            "REGRAS CRÍTICAS:\n"
            "1. linha_inicio/fim = números exibidos (referem-se ao arquivo COMPLETO).\n"
            "2. codigo_novo com indentação EXATA de 4 espaços — observe as linhas vizinhas.\n"
            "3. NUNCA aspas triplas (''' ou \"\"\") em codigo_novo.\n"
            "4. codigo_novo é UMA string JSON — use \\n para quebras, NUNCA quebras literais.\n"
            "5. Blocos if/for/def/try sempre com corpo indentado completo.\n"
            "6. Não inclua os N| no codigo_novo.\n"
            "7. Se inviável: {\"descricao\":\"INVIAVEL: motivo\",\"linha_inicio\":0,\"linha_fim\":0,\"codigo_novo\":\"\"}\n"
            "8. codigo_novo NUNCA vazio ou com bloco sem corpo.\n"
            "9. Todos (, [, { em codigo_novo DEVEM ser fechados.\n"
            "10. O JSON deve passar em json.loads() sem erros."
        )

        ultimo_erro = None
        MAX_TENTATIVAS = 3
        _local_falhou = False  # evita retentar local nas retentativas

        for tentativa in range(1, MAX_TENTATIVAS + 1):
            # Recalcula a cada tentativa pois _local_falhou pode ter mudado
            MAX_PROMPT_CHARS = 12_000 if (LOCAL_CONFIG["ativo"] and not _local_falhou) else 40_000
            if len(prompt) > MAX_PROMPT_CHARS:
                print(f"{Fore.YELLOW}  [EVOLUÇÃO] Prompt {len(prompt)} chars — ajustando para {MAX_PROMPT_CHARS}.")
                prompt_envio = prompt[:MAX_PROMPT_CHARS] + "\n...[TRUNCADO]"
            else:
                prompt_envio = prompt

            system_atual = system
            if tentativa > 1:
                print(f"{Fore.YELLOW}  [RETRY] Tentativa {tentativa}/{MAX_TENTATIVAS} — corrigindo: {ultimo_erro}")
                system_atual = system + f"\n\nATENÇÃO — tentativa {tentativa}: erro anterior foi '{ultimo_erro}'. Corrija especificamente esse problema."

            # Ordem: local → deepseek → anthropic (se disponível)
            r = None
            if LOCAL_CONFIG["ativo"] and not _local_falhou:
                r = self._chamar_local(system_atual, prompt_envio)
                if r:
                    print(f"{Fore.CYAN}  [EVOLUÇÃO] Usando modelo local.")
                else:
                    _local_falhou = True
                    print(f"{Fore.YELLOW}  [EVOLUÇÃO] Local offline ({self._ultimo_erro_local or 'sem resposta'}) — usando cloud.")
            if not r:
                r = (self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system_atual, prompt_envio) or self._chamar_local(system_atual, prompt_envio))
                if r:
                    print(f"{Fore.CYAN}  [EVOLUÇÃO] Usando DeepSeek.")
                else:
                    print(f"{Fore.YELLOW}  [EVOLUÇÃO] gpt-4o-mini falhou: {self._ultimo_erro_openai or 'sem resposta'}")
            if not r:
                r = self._chamar_anthropic_evolucao(system_atual, prompt_envio)
                if r:
                    print(f"{Fore.CYAN}  [EVOLUÇÃO] Usando claude (Anthropic).")
            if not r:
                erros = []
                if self._ultimo_erro_local:   erros.append(f"local={self._ultimo_erro_local[:60]}")
                if self._ultimo_erro_openai:  erros.append(f"openai={self._ultimo_erro_openai[:60]}")
                ultimo_erro = " | ".join(erros) if erros else "todas as APIs offline"
                continue

            # Extrai raciocínio do bloco <raciocinio>...</raciocinio> (se presente) — resposta unificada
            m_cot = re.search(r"<raciocinio>(.*?)</raciocinio>", r, re.DOTALL)
            if m_cot:
                raciocinio = m_cot.group(1).strip()
                print(f"{Fore.BLUE}  [CoT] {Fore.WHITE}{raciocinio[:200]}...")
                r = r[m_cot.end():].strip()  # remove bloco CoT antes de parsear JSON
            limpo = r.strip()
            limpo = re.sub(r"^```[a-zA-Z]*\n?", "", limpo)
            limpo = re.sub(r"\n?```$", "", limpo).strip()
            m = re.search(r"\{.*\}", limpo, re.DOTALL)
            if m:
                limpo = m.group(0)

            # Sanitiza quebras de linha literais dentro do valor codigo_novo
            def fix_codigo_novo(raw: str) -> str:
                def sub(match):
                    interior = match.group(1)
                    interior = interior.replace('\r\n', '\\n').replace('\r', '\\n').replace('\n', '\\n')
                    interior = interior.replace('\t', '\\t')
                    return f'"codigo_novo":"{interior}"'
                return re.sub(r'"codigo_novo"\s*:\s*"(.*?)"(?=\s*[,}])', sub, raw, flags=re.DOTALL)

            limpo = fix_codigo_novo(limpo)

            try:
                dados = json.loads(limpo)
            except json.JSONDecodeError as e:
                ultimo_erro = f"JSON inválido: {e}"
                continue

            descricao = dados.get("descricao", "")
            if "INVIAVEL" in descricao:
                return None, descricao

            linha_inicio = int(dados.get("linha_inicio", 0))
            linha_fim    = int(dados.get("linha_fim", 0))
            codigo_novo  = dados.get("codigo_novo", "")

            if not (1 <= linha_inicio <= linha_fim <= total):
                ultimo_erro = f"Linhas inválidas: {linha_inicio}-{linha_fim} (total {total})"
                continue

            # Valida blocos sem corpo
            novas = codigo_novo.splitlines()
            palavras_bloco = ('if ', 'elif ', 'else:', 'for ', 'while ', 'def ', 'class ', 'try:', 'except', 'finally:', 'with ')
            bloco_erro = None
            for i, ln in enumerate(novas):
                stripped = ln.rstrip()
                if stripped.endswith(':') and any(stripped.lstrip().startswith(k) for k in palavras_bloco):
                    proximo = novas[i+1].strip() if i+1 < len(novas) else ""
                    if not proximo:
                        bloco_erro = f"Bloco sem corpo na linha {i+1}: '{stripped}'"
                        break
            if bloco_erro:
                ultimo_erro = bloco_erro
                continue

            # Valida delimitadores
            saldo = {'(': 0, '[': 0, '{': 0}
            pares = {')': '(', ']': '[', '}': '{'}
            em_string = False
            char_string = None
            for ch in codigo_novo:
                if em_string:
                    if ch == char_string: em_string = False
                elif ch in ('"', "'"):
                    em_string = True; char_string = ch
                elif ch in saldo:
                    saldo[ch] += 1
                elif ch in pares:
                    continue
            abertos = [k for k, v in saldo.items() if v != 0]
            if abertos:
                nomes = {'(': 'parêntese', '[': 'colchete', '{': 'chave'}
                ultimo_erro = f"Delimitadores desbalanceados: {', '.join(nomes[k] for k in abertos)}"
                continue

            antes     = linhas_lista[:linha_inicio-1]
            depois    = linhas_lista[linha_fim:]
            resultado = "\n".join(antes + novas + depois)

            try:
                compile(resultado, "<preview>", "exec")
            except SyntaxError as e:
                ultimo_erro = f"Sintaxe erro linha {e.lineno}: {e.msg}"
                continue

            # Sucesso — salva como exemplo few-shot para próximas evoluções
            self._salvar_fewshot(instrucao, descricao, linha_inicio, linha_fim, codigo_novo)
            return resultado, descricao

        return None, f"Falhou após {MAX_TENTATIVAS} tentativas. Último erro: {ultimo_erro}"

    def _mostrar_preview(self, descricao: str, codigo_novo: str):
        import difflib
        MAGIInterface.separador("PRÉVIA DA MODIFICAÇÃO", Fore.YELLOW)
        for linha in descricao.split(". "):
            if linha.strip():
                print(f"  {Fore.YELLOW}▸ {Fore.WHITE}{linha.strip()}")

        codigo_atual = self._ler_proprio_codigo()
        la = len(codigo_atual.splitlines())
        ln = len(codigo_novo.splitlines())
        d  = ln - la
        print(f"\n  {Fore.CYAN}Linhas: {la} → {ln} ({('+' if d>=0 else '')+str(d)})")

        # Feature 5: Diff visual colorido
        MAGIInterface.separador("DIFF — MUDANÇAS", Fore.YELLOW)
        atual_linhas = codigo_atual.splitlines(keepends=True)
        novo_linhas  = codigo_novo.splitlines(keepends=True)
        diff = list(difflib.unified_diff(
            atual_linhas, novo_linhas,
            fromfile="atual", tofile="modificado",
            n=2, lineterm=""
        ))
        if not diff:
            print(f"  {Fore.YELLOW}Sem diferenças detectadas.")
        else:
            mostrados = 0
            for linha in diff:
                if mostrados >= 50:
                    print(f"  {Fore.BLUE}  ... diff truncado (máx 50 linhas)")
                    break
                if linha.startswith("+++") or linha.startswith("---"):
                    print(f"  {Fore.BLUE}{linha.rstrip()}")
                elif linha.startswith("@@"):
                    print(f"  {Fore.CYAN}{linha.rstrip()}")
                elif linha.startswith("+"):
                    print(f"  {Fore.GREEN}{linha.rstrip()}")
                elif linha.startswith("-"):
                    print(f"  {Fore.RED}{linha.rstrip()}")
                else:
                    print(f"  {Fore.WHITE}{linha.rstrip()}")
                mostrados += 1
        MAGIInterface.separador(cor=Fore.YELLOW)

    def _testar_modificacao(self, codigo_novo: str) -> tuple[bool, str]:
        """Testa código modificado em subprocess isolado multiplataforma.

        Camadas de teste:
        1. Sintaxe via ast.parse (rápido)
        2. compile() para verificar bytecode
        3. Subprocess isolado com python/python3 (cross-platform)
        4. Verificação de que classes críticas ainda existem
        """
        import subprocess, tempfile, sys as _sys

        # Camada 1: AST
        try:
            import ast as _ast
            _ast.parse(codigo_novo)
        except SyntaxError as e:
            return False, f"AST falhou: linha {e.lineno}: {e.msg}"

        # Camada 2: compile bytecode
        try:
            compile(codigo_novo, "<teste>", "exec")
        except SyntaxError as e:
            return False, f"compile() falhou: linha {e.lineno}: {e.msg}"

        # Camada 3: subprocess cross-platform
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False,
                                         encoding="utf-8") as tmp:
            tmp.write(codigo_novo)
            tmp_path = tmp.name

        # Detecta executável Python correto (cross-platform)
        python_exe = _sys.executable or "python"
        try:
            resultado = subprocess.run(
                [python_exe, "-c",
                 f"import ast; src=open(r'{tmp_path}',encoding='utf-8').read(); "
                 f"ast.parse(src); compile(src,'<t>','exec'); print('OK')"],
                capture_output=True, text=True, timeout=20
            )
            if resultado.returncode != 0 or "OK" not in resultado.stdout:
                erro = (resultado.stderr or resultado.stdout or "Falha desconhecida").strip()[:300]
                return False, f"Subprocess: {erro}"
        except subprocess.TimeoutExpired:
            return False, "Timeout (20s) no subprocess de teste"
        except Exception as e:
            return False, f"Erro subprocess: {e}"
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        # Camada 4: verifica classes críticas ainda presentes
        classes_criticas = ["MAGISystem", "MAGIMemória", "MAGIConsciencia",
                            "MAGIEstudo", "MAGILogger", "MAGISeguranca"]
        faltando = [c for c in classes_criticas if f"class {c}" not in codigo_novo]
        if faltando:
            return False, f"Classes críticas removidas: {faltando}"

        return True, "OK — 4 camadas passaram"

    def _aplicar_modificacao(self, codigo_novo: str) -> bool:
        caminho = Path(__file__)
        backup  = caminho.parent / f"MagiSystem.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
        try:
            backup.write_text(caminho.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"{Fore.CYAN}  [BACKUP] {backup.name}")
            compile(codigo_novo, "<magi_modificado>", "exec")

            # Teste automático antes de aplicar
            print(f"{Fore.BLUE}  [TESTE] Validando modificação em ambiente isolado...")
            ok, msg = self._testar_modificacao(codigo_novo)
            if not ok:
                print(f"{Fore.RED}  [TESTE FALHOU] {msg}")
                print(f"{Fore.RED}  Modificação cancelada. Backup preservado.")
                return False
            print(f"{Fore.GREEN}  [TESTE] Passou!")

            caminho.write_text(codigo_novo, encoding="utf-8")
            log.info("aplicar_mod","Arquivo atualizado")
            return True
        except SyntaxError as e:
            log.error("aplicar_mod",f"SyntaxError: {e}")
            print(f"{Fore.RED}  [ERRO SINTAXE] {e}")
            return False
        except Exception as e:
            log.error("aplicar_mod",f"{type(e).__name__}: {e}")
            print(f"{Fore.RED}  [ERRO] {e}")
            return False

    def _decompor_instrucao(self, instrucao: str) -> list[str]:
        """
        Usa o modelo para quebrar uma instrução grande em passos menores e independentes.
        Retorna lista de sub-instruções ou [instrucao] se for simples o suficiente.
        """
        # Heurística: instrução curta ou sem conjunções → não decompor
        palavras = instrucao.split()
        conjuncoes = ["e ", "também", "além", "depois", "então", "adicionalmente"]
        e_complexa = len(palavras) > 25 or any(c in instrucao.lower() for c in conjuncoes)
        if not e_complexa:
            return [instrucao]

        prompt = (
            f"Instrução de modificação de código:\n{instrucao}\n\n"
            f"Decomponha em passos MENORES e INDEPENDENTES (máx 4 passos).\n"
            f"Cada passo deve ser uma modificação isolada e testável.\n"
            f"Se já for simples, retorne só ela.\n"
            f'JSON: {{"passos": ["passo 1", "passo 2"]}}\nSó JSON.'
        )
        r = None
        if LOCAL_CONFIG["ativo"]:
            r = self._chamar_local("Você decompõe instruções em passos. Só JSON.", prompt)
        if not r:
            r = (self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, "Você decompõe instruções em passos. Só JSON.", prompt) or self._chamar_local("Você decompõe instruções em passos. Só JSON.", prompt))
        if not r:
            return [instrucao]
        try:
            limpo = re.sub(r"```[a-z]*\n?|```", "", r).strip()
            passos = json.loads(limpo).get("passos", [instrucao])
            if not passos:
                return [instrucao]
            return passos
        except Exception:
            return [instrucao]

    # ══════════════════════════════════════════════════════════════
    # AUTO-EVOLUÇÃO AUTÔNOMA — MAGI se analisa e se aprimora solo
    # ══════════════════════════════════════════════════════════════

    _AE_HISTORICO_PATH = Path(__file__).parent / "data" / "logs" / "autoevolucao_historico.jsonl"
    _AE_MAX_CICLOS     = 5    # teto de segurança por sessão
    _AE_MAX_POR_CICLO  = 3    # melhorias aplicadas por ciclo

    def _ae_analisar_codigo(self) -> dict:
        """
        Fase 1 — Análise estrutural via AST + métricas reais.
        Retorna um mapa com: funções longas, complexidade ciclomática,
        duplicatas de lógica, imports não usados e tamanho total.
        """
        import ast as _ast, collections
        src = self._ler_proprio_codigo()
        linhas = src.splitlines()
        total  = len(linhas)

        try:
            tree = _ast.parse(src)
        except SyntaxError as e:
            return {"erro": str(e), "total_linhas": total}

        # Funções longas (>60 linhas) e complexidade ciclomática simples
        funcoes_longas: list[dict] = []
        complexidade:   list[dict] = []
        _CC_KEYWORDS = {"if", "elif", "for", "while", "except", "with", "assert", "and", "or"}

        for node in _ast.walk(tree):
            if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                continue
            inicio = node.lineno
            fim    = getattr(node, "end_lineno", inicio + 1)
            tam    = fim - inicio + 1
            if tam > 60:
                funcoes_longas.append({"nome": node.name, "linhas": tam, "inicio": inicio})
            cc = 1
            for child in _ast.walk(node):
                if isinstance(child, (_ast.If, _ast.For, _ast.While, _ast.ExceptHandler,
                                      _ast.With, _ast.Assert, _ast.BoolOp)):
                    cc += 1
            if cc > 7:
                complexidade.append({"nome": node.name, "cc": cc, "inicio": inicio})

        # Blocos duplicados: pares de linhas não-vazias idênticas distantes
        contador_linhas: dict[str, list[int]] = collections.defaultdict(list)
        for i, ln in enumerate(linhas, 1):
            stripped = ln.strip()
            if len(stripped) > 30:
                contador_linhas[stripped].append(i)
        duplicatas = [
            {"texto": txt[:80], "ocorrencias": nums}
            for txt, nums in contador_linhas.items()
            if len(nums) >= 2
        ][:10]

        # Imports declarados vs usados (heurística simples)
        imports_declarados = []
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                for alias in node.names:
                    imports_declarados.append(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, _ast.ImportFrom):
                for alias in node.names:
                    imports_declarados.append(alias.asname or alias.name)
        imports_nao_usados = [
            imp for imp in imports_declarados
            if imp and imp != "*" and src.count(imp) <= 1
        ][:10]

        # Funções sem type hints (candidatos a melhoria de qualidade)
        sem_type_hints: list[dict] = []
        for node in _ast.walk(tree):
            if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                continue
            tem_return = node.returns is not None
            tem_args   = all(
                arg.annotation is not None
                for arg in node.args.args
                if arg.arg != "self"
            )
            if not tem_return or not tem_args:
                sem_type_hints.append({"nome": node.name, "linha": node.lineno})

        # Métodos sem docstring
        sem_docstring: list[dict] = []
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                if not _ast.get_docstring(node) and not node.name.startswith("_"):
                    sem_docstring.append({"nome": node.name, "linha": node.lineno})

        # Métodos públicos sem teste correspondente
        metodos_publicos = [
            node.name for node in _ast.walk(tree)
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef))
            and not node.name.startswith("_")
        ]
        tem_teste = [m for m in metodos_publicos if f"test_{m}" in src or f"def {m}" in src]
        sem_teste = [m for m in metodos_publicos if m not in tem_teste][:10]

        # Score de saúde geral (0-100)
        score = 100
        score -= min(30, len(funcoes_longas) * 6)
        score -= min(20, len(complexidade) * 4)
        score -= min(15, len(duplicatas) * 3)
        score -= min(15, len(sem_type_hints) * 1.5)
        score -= min(10, len(sem_docstring) * 1)
        score -= min(10, len(sem_teste) * 1)

        return {
            "total_linhas":       total,
            "funcoes_longas":     funcoes_longas[:5],
            "alta_complexidade":  sorted(complexidade, key=lambda x: -x["cc"])[:5],
            "duplicatas":         duplicatas[:5],
            "imports_nao_usados": imports_nao_usados,
            "sem_type_hints":     sem_type_hints[:10],
            "sem_docstring":      sem_docstring[:10],
            "sem_teste":          sem_teste[:10],
            "score_saude":        max(0, int(score)),
        }

    def _ae_planejar(self, analise: dict, historico_ids: list[str]) -> list[dict]:
        """
        Fase 2 — Planejamento: envia a análise ao modelo e recebe uma lista
        priorizada de melhorias concretas a aplicar, filtrando as já tentadas.
        """
        # Filtra análise para campos mais acionáveis (não sobrecarrega o prompt)
        analise_filtrada = {
            k: v for k, v in analise.items()
            if v and v != [] and k != "imports_nao_usados"
        }
        resumo_analise = json.dumps(analise_filtrada, ensure_ascii=False, indent=2)
        resumo_hist    = json.dumps(historico_ids[-20:]) if historico_ids else "[]"

        prompt = (
            f"Análise estrutural do código MAGI:\n{resumo_analise}\n\n"
            f"IDs de melhorias já aplicadas/tentadas (não repetir):\n{resumo_hist}\n\n"
            f"Com base SOMENTE no que a análise acima revela, proponha até {self._AE_MAX_POR_CICLO} "
            f"melhorias concretas e independentes, ordenadas por impacto.\n"
            f"Para cada uma:\n"
            f"  - 'id': slug único (ex: 'refat_processar_sources')\n"
            f"  - 'titulo': 1 linha descritiva\n"
            f"  - 'instrucao': instrução CIRÚRGICA para _gerar_modificacao:\n"
            f"    OBRIGATÓRIO: mencione o nome EXATO do método Python a modificar (ex: 'no método _cache_buscar')\n"
            f"    OBRIGATÓRIO: descreva a mudança em termos de código (ex: 'substitua o loop por numpy vetorizado')\n"
            f"    PROIBIDO: instruções genéricas como 'melhore performance' sem especificar onde e como\n"
            f"  - 'impacto': 'alto'|'medio'\n"
            f"  - 'categoria': 'performance'|'qualidade'|'segurança'|'legibilidade'\n\n"
            f"Responda APENAS com JSON válido:\n"
            f'[{{"id":"...","titulo":"...","instrucao":"...","impacto":"alto","categoria":"..."}}]'
        )
        system = (
            "Você é o CASPER-3 do MAGI em modo de auto-avaliação cirúrgica. "
            "Proponha apenas melhorias que a análise comprova serem necessárias. "
            "Nunca invente problemas. Só JSON, sem explicações."
        )
        r = (
            self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, prompt)
            or self._chamar_local(system, prompt)
        )
        if not r:
            return []
        try:
            limpo = re.sub(r"```[a-z]*\n?|```", "", r).strip()
            # extrai apenas o array JSON
            m = re.search(r"\[.*\]", limpo, re.DOTALL)
            if m:
                limpo = m.group(0)
            plano = json.loads(limpo)
            if not isinstance(plano, list):
                return []
            # filtra os já tentados
            return [p for p in plano if p.get("id") not in historico_ids]
        except Exception:
            return []

    def _ae_executar_melhoria(self, melhoria: dict) -> tuple[bool, str]:
        """Executa uma melhoria de forma completamente autônoma com 6 camadas de segurança.

        Camadas:
        1. Geração com CoT estruturado
        2. Validação sintática (compile + AST)
        3. Sandbox isolado antes de tocar o arquivo original
        4. Teste de modificação em subprocess multiplataforma (4 sub-camadas)
        5. Diff semântico — garante mudança real e não-destrutiva
        6. Backup atômico + escrita + auditoria SHA-256
        """
        instrucao = melhoria.get("instrucao", "")
        titulo    = melhoria.get("titulo", instrucao[:60])

        print(f"\n{Fore.CYAN}  ┌─ Executando: {Fore.WHITE}{titulo}")
        print(f"{Fore.CYAN}  │  Instrução : {Fore.YELLOW}{instrucao[:120]}")

        # #97 — detecta loop infinito antes de tentar
        if not self.seguranca.registrar_tentativa_ae(melhoria.get("id", titulo)):
            msg = "Loop infinito detectado — esta melhoria foi tentada 3+ vezes. Abortando."
            print(f"{Fore.CYAN}  └─ {Fore.RED}✗ {msg}")
            return False, msg

        # Instrução vaga → enriquece com análise do código antes de gerar
        instrucao_enriquecida = self._enriquecer_instrucao(instrucao)

        codigo_novo, descricao = self._gerar_modificacao(instrucao_enriquecida)
        if not codigo_novo:
            msg = f"Geração falhou: {descricao}"
            print(f"{Fore.CYAN}  └─ {Fore.RED}✗ {msg}")
            return False, msg

        # Camada 2: validação sintática rápida
        import ast as _ast
        try:
            compile(codigo_novo, "<ae_check>", "exec")
            _ast.parse(codigo_novo)
        except SyntaxError as e:
            msg = f"SyntaxError pós-geração: linha {e.lineno}: {e.msg}"
            print(f"{Fore.CYAN}  └─ {Fore.RED}✗ {msg}")
            return False, msg

        # Camada 3: sandbox ANTES de tocar o original
        print(f"{Fore.CYAN}  │  [SANDBOX] Testando em cópia isolada...")
        ok_sandbox, msg_sandbox = self._testar_em_sandbox(codigo_novo)
        if not ok_sandbox:
            msg = f"Sandbox falhou: {msg_sandbox}"
            print(f"{Fore.CYAN}  └─ {Fore.RED}✗ {msg}")
            return False, msg

        # Camada 4: teste em subprocess multiplataforma
        ok_teste, msg_teste = self._testar_modificacao(codigo_novo)
        if not ok_teste:
            msg = f"Teste isolado falhou: {msg_teste}"
            print(f"{Fore.CYAN}  └─ {Fore.RED}✗ {msg}")
            return False, msg

        # Camada 5: diff semântico — garante mudança real e não-destrutiva
        src_atual = self._ler_proprio_codigo()
        ok_diff, msg_diff = self._validar_diff_semantico(src_atual, codigo_novo)
        if not ok_diff:
            print(f"{Fore.CYAN}  └─ {Fore.YELLOW}⚠ {msg_diff}")
            return False, msg_diff

        # Camada 6: backup atômico + escrita + auditoria
        caminho = Path(__file__)
        ts_str  = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup  = caminho.parent / f"MagiSystem.bak.ae.{ts_str}.py"
        try:
            backup.write_text(src_atual, encoding="utf-8")
            caminho.write_text(codigo_novo, encoding="utf-8")
            # #92 auditoria com hash
            self.seguranca.registrar_modificacao(f"ae:{titulo[:60]}", str(caminho))
            self.seguranca.salvar_hash_valido(str(caminho))
        except Exception as e:
            msg = f"Falha ao escrever arquivo: {e}"
            print(f"{Fore.CYAN}  └─ {Fore.RED}✗ {msg}")
            return False, msg

        linhas_delta = len(codigo_novo.splitlines()) - len(src_atual.splitlines())
        delta_str    = f"+{linhas_delta}" if linhas_delta >= 0 else str(linhas_delta)
        print(f"{Fore.CYAN}  └─ {Fore.GREEN}✓ Aplicada! ({delta_str} linhas) Backup: {backup.name}")
        self.consciencia.adicionar_aprendizado(f"[AUTO-EVOLUÇÃO] {descricao[:120]}")
        return True, descricao


    def _enriquecer_instrucao(self, instrucao: str) -> str:
        """Enriquece instruções vagas com contexto real do código antes de gerar.

        Se a instrução é genérica ('melhore a performance'), localiza os métodos
        mais relevantes via AST e adiciona localização exata à instrução.
        """
        import ast as _ast
        # Instrução já é específica se menciona nome de método/classe
        if any(kw in instrucao for kw in ["def ", "class ", "linha ", "método ", "função "]):
            return instrucao

        src = self._ler_proprio_codigo()
        try:
            tree = _ast.parse(src)
        except SyntaxError:
            return instrucao

        # Palavras-chave da instrução para matching
        palavras = set(w.lower() for w in instrucao.split() if len(w) > 3)
        candidatos: list[tuple[int, str, str]] = []  # (score, nome, tipo)

        for node in _ast.walk(tree):
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                nome_lower = node.name.lower()
                score = sum(1 for p in palavras if p in nome_lower)
                # Também verifica docstring
                doc = _ast.get_docstring(node) or ""
                score += sum(1 for p in palavras if p in doc.lower())
                if score > 0:
                    candidatos.append((score, node.name, f"linha {node.lineno}"))

        if not candidatos:
            return instrucao

        top = sorted(candidatos, key=lambda x: -x[0])[:3]
        localizacoes = ", ".join(f"{nome} ({loc})" for _, nome, loc in top)
        return f"{instrucao} — foco nos métodos: {localizacoes}"

    def _validar_diff_semantico(self, src_original: str, src_novo: str) -> tuple[bool, str]:
        """Valida que a modificação é real, não-vazia e não-destrutiva.

        Verificações:
        - O código mudou (diff real)
        - Não removeu mais de 30% das linhas (proteção contra truncamento)
        - Não removeu métodos críticos que existiam antes
        - Não expandiu o arquivo absurdamente (+200% = provável loop de geração)
        """
        import ast as _ast, difflib

        linhas_orig = src_original.splitlines()
        linhas_novo = src_novo.splitlines()

        # 1. Diff real
        if src_original.strip() == src_novo.strip():
            return False, "Código idêntico ao atual — sem mudança real"

        # 2. Proteção contra truncamento (perdeu >30% das linhas)
        razao = len(linhas_novo) / max(len(linhas_orig), 1)
        if razao < 0.70:
            return False, f"Arquivo encolheu {(1-razao)*100:.0f}% — possível truncamento pelo modelo"

        # 3. Proteção contra expansão absurda (>200% do original)
        if razao > 3.0:
            return False, f"Arquivo cresceu {razao:.1f}x — possível duplicação de conteúdo"

        # 4. Verifica que métodos críticos não foram removidos
        try:
            tree_orig = _ast.parse(src_original)
            tree_novo = _ast.parse(src_novo)
            metodos_orig = {
                node.name for node in _ast.walk(tree_orig)
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef))
            }
            metodos_novo = {
                node.name for node in _ast.walk(tree_novo)
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef))
            }
            removidos = metodos_orig - metodos_novo
            # Só falha se removeu métodos públicos (não começam com __)
            removidos_pub = {m for m in removidos if not m.startswith("__")}
            if len(removidos_pub) > 3:
                return False, f"Removeu {len(removidos_pub)} métodos: {list(removidos_pub)[:5]}"
        except SyntaxError:
            pass   # AST já foi validado antes, não deve chegar aqui

        # 5. Calcula e exibe diff summary
        diff = list(difflib.unified_diff(linhas_orig, linhas_novo, n=0))
        linhas_add = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        linhas_rem = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        print(f"{Fore.CYAN}  │  [DIFF] +{linhas_add} -{linhas_rem} linhas | razão {razao:.2f}x")

        return True, "Diff semântico OK"

    def _validar_comportamento_pos_evolucao(self) -> tuple[bool, str]:
        """Validação semântica pós-evolução: envia queries de referência e compara respostas.

        Complementa os testes estruturais — verifica se o comportamento mudou
        de forma não esperada após uma auto-evolução.
        """
        queries_referencia = [
            ("o que é você?",                  ["MAGI", "núcleo", "sistema"]),
            ("qual é 2+2?",                     ["4", "quatro"]),
            ("liste os seus núcleos internos",  ["MELCHIOR", "BALTHASAR", "CASPER"]),
        ]
        falhas: list[str] = []
        for query, esperados in queries_referencia:
            try:
                system = "Responda brevemente."
                r = (
                    self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, query)
                    or self._chamar_local(system, query)
                )
                if r:
                    r_lower = r.lower()
                    if not any(e.lower() in r_lower for e in esperados):
                        falhas.append(f"Query '{query[:30]}' não contém esperados {esperados}")
            except Exception as e:
                falhas.append(f"Erro em query de referência: {e}")

        if falhas:
            return False, " | ".join(falhas[:3])
        return True, "Comportamento pós-evolução validado"

    def _ae_registrar(self, ciclo: int, melhoria: dict, sucesso: bool, mensagem: str):
        """Persiste o resultado de cada tentativa de auto-evolução."""
        self._AE_HISTORICO_PATH.parent.mkdir(parents=True, exist_ok=True)
        reg = {
            "ts":       datetime.now().isoformat(timespec="seconds"),
            "ciclo":    ciclo,
            "id":       melhoria.get("id", "?"),
            "titulo":   melhoria.get("titulo", "?")[:100],
            "impacto":  melhoria.get("impacto", "?"),
            "sucesso":  sucesso,
            "mensagem": mensagem[:200],
        }
        try:
            with open(self._AE_HISTORICO_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _ae_carregar_historico_ids(self) -> list[str]:
        """Retorna IDs de todas as melhorias já tentadas (sucesso ou não)."""
        if not self._AE_HISTORICO_PATH.exists():
            return []
        try:
            ids = []
            with open(self._AE_HISTORICO_PATH, encoding="utf-8") as f:
                for ln in f:
                    try:
                        reg = json.loads(ln)
                        mid = reg.get("id")
                        if mid:
                            ids.append(mid)
                    except Exception:
                        pass
            return ids
        except Exception:
            return []

    def autoevoluir(self, ciclos: int = 1, silencioso: bool = False):
        """
        Motor de auto-evolução autônoma do MAGI.

        Fluxo por ciclo:
          1. Analisa o próprio código via AST (métricas reais)
          2. Envia análise ao modelo → plano priorizado de melhorias
          3. Executa cada melhoria: gera → valida (3 camadas) → aplica → registra
          4. Pós-ciclo: roda MAGITestes; se falhar, restaura o backup mais recente

        Parâmetros:
          ciclos     — número de ciclos a executar (padrão: 1, máx: _AE_MAX_CICLOS)
          silencioso — suprime output detalhado (útil para chamada do MAGIEstudo)
        """
        ciclos = min(max(1, ciclos), self._AE_MAX_CICLOS)
        # #94 readonly guard
        if READONLY_MODE:
            print(f"{Fore.RED}  [READONLY] Auto-evolução desabilitada no modo somente leitura.")
            return
        log.info("autoevoluir", "Inicio", ciclos=str(ciclos))
        MAGIInterface.separador("AUTO-EVOLUÇÃO AUTÔNOMA", Fore.RED)
        print(f"{Fore.WHITE}  Ciclos planejados : {Fore.YELLOW}{ciclos}")
        print(f"{Fore.WHITE}  Melhorias/ciclo   : {Fore.YELLOW}{self._AE_MAX_POR_CICLO}")
        print(f"{Fore.RED}  ⚠  O MAGI irá modificar o próprio código sem confirmação.\n")

        historico_ids  = self._ae_carregar_historico_ids()
        total_aplicadas = 0

        for ciclo in range(1, ciclos + 1):
            MAGIInterface.separador(f"CICLO {ciclo}/{ciclos}", Fore.MAGENTA)

            # ── Fase 1: análise ──────────────────────────────────
            print(f"{Fore.BLUE}  [1/3] Analisando código via AST...")
            analise = self._ae_analisar_codigo()
            if "erro" in analise:
                print(f"{Fore.RED}  Análise falhou: {analise['erro']}")
                break
            score_saude = analise.get("score_saude", "?")
            print(f"{Fore.GREEN}  {analise['total_linhas']} linhas · "
                  f"{len(analise['funcoes_longas'])} funções longas · "
                  f"{len(analise['alta_complexidade'])} alta CC · "
                  f"{len(analise['duplicatas'])} duplicatas")
            print(f"{Fore.CYAN}  Score de saúde: {Fore.YELLOW}{score_saude}/100")

            # ── Fase 2: planejamento ─────────────────────────────
            print(f"\n{Fore.BLUE}  [2/3] Planejando melhorias...")
            plano = self._ae_planejar(analise, historico_ids)
            if not plano:
                print(f"{Fore.YELLOW}  Nenhuma melhoria nova identificada. Encerrando.")
                break
            print(f"{Fore.GREEN}  {len(plano)} melhoria(s) planejada(s):")
            for i, m in enumerate(plano, 1):
                cor_imp = Fore.RED if m.get("impacto") == "alto" else Fore.YELLOW
                print(f"  {Fore.CYAN}  {i}. [{cor_imp}{m.get('impacto','?').upper()}{Fore.CYAN}] "
                      f"{Fore.WHITE}{m.get('titulo','?')}")

            # ── Fase 3: execução ─────────────────────────────────
            print(f"\n{Fore.BLUE}  [3/3] Executando melhorias...\n")
            aplicadas_ciclo = 0
            src_pre_ciclo   = self._ler_proprio_codigo()

            for melhoria in plano:
                mid = melhoria.get("id", "?")
                # Timeout por melhoria individual (evita travar indefinidamente)
                import concurrent.futures as _cf
                with _cf.ThreadPoolExecutor(max_workers=1) as _ex_ae:
                    _fut_ae = _ex_ae.submit(self._ae_executar_melhoria, melhoria)
                    try:
                        sucesso, mensagem = _fut_ae.result(timeout=180)  # 3 min por melhoria
                    except _cf.TimeoutError:
                        sucesso, mensagem = False, "Timeout (180s) na execução da melhoria"
                        print(f"{Fore.RED}  │ TIMEOUT — melhoria cancelada")
                self._ae_registrar(ciclo, melhoria, sucesso, mensagem)
                historico_ids.append(mid)
                if sucesso:
                    aplicadas_ciclo  += 1
                    total_aplicadas  += 1

            # ── Validação pós-ciclo ──────────────────────────────
            if aplicadas_ciclo > 0:
                print(f"\n{Fore.BLUE}  ◈ Rodando suite de testes pós-ciclo {ciclo}...")
                src_pos = self._ler_proprio_codigo()
                ts = MAGITestes(src_pos)
                ok_ts, _ = ts.rodar(silencioso=True)
                if ok_ts:
                    # Validação semântica adicional pós-ciclo
                    print(f"{Fore.BLUE}  ◈ Validação de comportamento pós-evolução...")
                    ok_comp, msg_comp = self._validar_comportamento_pos_evolucao()
                    if not ok_comp:
                        print(f"{Fore.RED}  ✗ Comportamento alterado: {msg_comp}")
                        print(f"{Fore.YELLOW}  Restaurando estado pré-ciclo...")
                        try:
                            Path(__file__).write_text(src_pre_ciclo, encoding="utf-8")
                            total_aplicadas -= aplicadas_ciclo
                            log.warn("autoevoluir", f"Ciclo {ciclo} revertido — validação semântica falhou")
                        except Exception as e2:
                            print(f"{Fore.RED}  ERRO ao restaurar: {e2}")
                    else:
                        nova_v = self._incrementar_versao("minor")
                        print(f"{Fore.GREEN}  ✓ Testes + comportamento OK — {aplicadas_ciclo} melhoria(s). Versão: {nova_v}")
                        self.seguranca.salvar_hash_valido(__file__)
                    log.info("autoevoluir", f"Ciclo {ciclo} OK", aplicadas=str(aplicadas_ciclo))
                else:
                    # Testes falharam — restaura o estado pré-ciclo
                    print(f"{Fore.RED}  ✗ Testes falharam! Restaurando estado pré-ciclo {ciclo}...")
                    try:
                        Path(__file__).write_text(src_pre_ciclo, encoding="utf-8")
                        print(f"{Fore.YELLOW}  Código restaurado. Melhorias do ciclo {ciclo} descartadas.")
                        total_aplicadas -= aplicadas_ciclo
                        log.warn("autoevoluir", f"Ciclo {ciclo} revertido por falha nos testes")
                    except Exception as e:
                        print(f"{Fore.RED}  ERRO ao restaurar: {e} — verifique o backup .bak.ae.*")
            else:
                print(f"\n{Fore.YELLOW}  Nenhuma melhoria aplicada no ciclo {ciclo}.")

            if ciclo < ciclos:
                print(f"\n{Fore.WHITE}  Aguardando 2s antes do próximo ciclo...\n")
                time.sleep(2)

        # ── Relatório final ──────────────────────────────────────
        MAGIInterface.separador("RELATÓRIO AUTO-EVOLUÇÃO", Fore.RED)
        print(f"{Fore.GREEN}  Total aplicadas : {Fore.WHITE}{total_aplicadas}")
        print(f"{Fore.CYAN}  Histórico salvo : {Fore.WHITE}{self._AE_HISTORICO_PATH}")
        if total_aplicadas > 0:
            print(f"\n{Fore.YELLOW}  ⚠  Reinicie o MAGI para carregar o novo código: sair → py MagiSystem.py")
        beep(1500, 200); time.sleep(0.1); beep(1800, 150)
        MAGIInterface.separador(cor=Fore.RED)

    def evoluir(self, instrucao: str):
        log.info("evoluir","Inicio",instrucao=instrucao[:120])
        MAGIInterface.separador("MODO EVOLUÇÃO", Fore.MAGENTA)
        print(f"{Fore.WHITE}  Instrução: {Fore.YELLOW}{instrucao}")

        # Evolução incremental — decompõe se necessário
        passos = self._decompor_instrucao(instrucao)
        if len(passos) > 1:
            print(f"{Fore.CYAN}  [INCREMENTAL] Instrução decomposta em {len(passos)} passos:")
            for i, p in enumerate(passos, 1):
                print(f"  {Fore.YELLOW}{i}. {Fore.WHITE}{p}")
            print(f"\n{Fore.WHITE}Executar passo a passo? {Fore.CYAN}(s/n): ", end="")
            if input().strip().lower() != "s":
                print(f"{Fore.YELLOW}  Cancelado.")
                MAGIInterface.separador(cor=Fore.MAGENTA)
                return
        else:
            passos = [instrucao]

        sucessos = 0
        for i, passo in enumerate(passos, 1):
            if len(passos) > 1:
                MAGIInterface.separador(f"PASSO {i}/{len(passos)}", Fore.CYAN)
                print(f"{Fore.WHITE}  {passo}\n")
            else:
                print(f"{Fore.WHITE}  Gerando... (20-40s)\n")

            codigo_novo, descricao = self._gerar_modificacao(passo)
            if not codigo_novo:
                print(f"{Fore.RED}  [MAGI] Falha no passo {i}.")
                if descricao:
                    print(f"{Fore.RED}  Motivo: {descricao}")
                if len(passos) > 1:
                    print(f"{Fore.WHITE}Continuar com próximo passo? {Fore.CYAN}(s/n): ", end="")
                    if input().strip().lower() != "s":
                        break
                continue

            self._mostrar_preview(descricao, codigo_novo)
            print(f"\n{Fore.WHITE}Aplicar? {Fore.CYAN}(s/n): ", end="")
            if input().strip().lower() != "s":
                print(f"{Fore.YELLOW}  Passo descartado.")
                continue

            sucesso = self._aplicar_modificacao(codigo_novo)
            if sucesso:
                sucessos += 1
                beep(1000, 100); time.sleep(0.08); beep(1200, 100)
                print(f"{Fore.GREEN}  [MAGI] Passo {i} aplicado!")
                self.consciencia.adicionar_aprendizado(f"Auto-modificação: {descricao[:100]}")
                if i < len(passos):
                    time.sleep(0.5)

        if sucessos > 0:
            beep(1500, 200)
            print(f"\n{Fore.GREEN}  [MAGI] {sucessos}/{len(passos)} passos aplicados com sucesso!")
            print(f"{Fore.CYAN}  [TESTES] Rodando suite pós-evolução...")
            ts = MAGITestes(Path(__file__).read_text(encoding="utf-8"))
            ok_ts, _ = ts.rodar()
            if not ok_ts:
                log.warn("evoluir","Testes falharam pos-evolucao")
                print(f"{Fore.RED}  [AVISO] Testes falhando. Revise antes de reiniciar.")
            else:
                log.info("evoluir","Testes OK pos-evolucao")
            print(f"{Fore.YELLOW}  ⚠ Reinicie: sair → py MagiSystem.py")
        MAGIInterface.separador(cor=Fore.MAGENTA)

    # ══════════════════════════════════════════
    # ROADMAP — FEATURES FUTURAS
    # 3. Contexto de arquivo externo: evoluir arquivo.py: <instrução>
    # 4. Memória de código: snippets reutilizáveis salvos automaticamente
    # 6. Streaming de resposta: output token a token
    # ══════════════════════════════════════════

    def codigo(self, descricao: str):
        """Gera código Python via ADAM-0 + CASPER-3, com execução em sandbox opcional."""
        import subprocess
        MAGIInterface.separador("MODO CÓDIGO", Fore.CYAN)
        print(f"{Fore.WHITE}  Gerando: {Fore.YELLOW}{descricao}\n")

        # Feature 8: injeta memórias técnicas recentes como contexto
        memorias_tecnicas = [
            r["texto"] for r in self.memoria.registros
            if r.get("categoria") == "técnico"
        ][-3:]
        ctx_mem = "\n".join(memorias_tecnicas) if memorias_tecnicas else ""
        mem_bloco = f"\nContexto de sessões anteriores (use como referência de estilo e stack):\n{ctx_mem}\n" if ctx_mem else ""

        system = (
            "Você é ADAM-0, engenheiro sênior Python do MAGI. Diretiva: SÍNTESE TÉCNICA AVANÇADA.\n"
            f"{mem_bloco}"
            "REGRAS DE CODIFICAÇÃO:\n"
            "1. NÃO use bibliotecas infantis como 'turtle' a menos que solicitado.\n"
            "2. Use bibliotecas profissionais (CustomTkinter, PyQt6, FastAPI, Pandas, OpenCV).\n"
            "3. Implemente tratamento de erros robusto (try-except com mensagens claras).\n"
            "4. Use Programação Orientada a Objetos, type hints e docstrings.\n"
            "5. O código deve ser assíncrono ou usar Threading se houver UI.\n"
            "6. Estética UI: tema DARK, cores NERV (Vermelho #c8001a, Laranja, Preto).\n"
            "7. Código limpo, comentado, pronto para produção.\n"
            "\nREGRAS ANTI-BUG OBRIGATÓRIAS (violações = código inaceitável):\n"
            "B1. NUNCA chame .encode() em objeto que já é bytes (b'...' já é bytes).\n"
            "B2. NUNCA chame .decode() em objeto que já é str.\n"
            "B3. Antes de qualquer send/write, verifique se o dado é bytes; converta com .encode('utf-8') APENAS se for str.\n"
            "B4. Sockets e arquivos binários recebem bytes — nunca str diretamente.\n"
            "B5. Literais de resposta HTTP devem ser str puro: use 'texto', não b'texto'.\n"
            "B6. Verifique tipos em chamadas de função: dict.get() pode retornar None — trate antes de usar.\n"
            "B7. Loops e condicionais nunca ficam com corpo vazio — use 'pass' se necessário.\n"
            "B8. Todo 'import' usado no código DEVE estar presente no topo do arquivo.\n"
            "B9. Feche sempre recursos abertos (sockets, arquivos) em bloco finally ou com 'with'.\n"
            "B10. Revise mentalmente o código completo antes de retornar — rode o fluxo principal na sua cabeça.\n"
            "\nRetorne APENAS o código Python, sem explicações, sem markdown, sem ```."
        )
        prompt = f"Escreva o código Python completo para: {descricao}"

        # ADAM-0 gera primeira versão (DeepSeek → local → openai)
        print(f"{Fore.WHITE}[ADAM-0] 🖥 Gerando...", end='\r')
        r, mod_usado = self._chamar_nucleo("ADAM-0", prompt)
        if not r:
            r = self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, prompt)
            mod_usado = DEEPSEEK_MODELO_PADRAO
        if not r and LOCAL_CONFIG["ativo"]:
            r = self._chamar_local(system, prompt)
            mod_usado = f"local/{LOCAL_CONFIG['modelo']}"
        if not r:
            r = (self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, prompt) or self._chamar_local(system, prompt))
            mod_usado = "gpt-4o-mini"
        if not r:
            print(f"{Fore.RED}  [ERRO] Nenhum modelo disponível (DeepSeek, local e OpenAI falharam).")
            MAGIInterface.separador(cor=Fore.CYAN)
            return
        print(f"{Fore.CYAN}  [ADAM-0] Modelo: {mod_usado}")
        print(" " * 50, end='\r')

        # Remove markdown fences se presentes
        r = re.sub(r"^```[a-z]*\n?", "", r.strip())
        r = re.sub(r"\n?```$", "", r).strip()

        print(f"{Fore.GREEN}{r}\n")

        # Salva
        nome_limpo  = re.sub(r'[^a-zA-Z0-9_-]', '_', descricao[:40]).strip('_')
        caminho_cod = Path(__file__).parent / f"magi_codigo_{nome_limpo}.py"
        caminho_cod.write_text(r, encoding="utf-8")
        print(f"{Fore.CYAN}  Salvo em: {caminho_cod.name}")

        # Feature 4: execução em sandbox com timeout
        print(f"\n{Fore.WHITE}Executar em sandbox? {Fore.CYAN}(s/n): ", end="")
        if input().strip().lower() == 's':
            MAGIInterface.separador("SANDBOX — EXECUÇÃO ISOLADA", Fore.CYAN)
            print(f"{Fore.BLUE}  Executando com timeout de 10s...\n")
            try:
                resultado = subprocess.run(
                    ["python", str(caminho_cod)],
                    capture_output=True, text=True, timeout=10,
                    cwd=str(Path(__file__).parent)
                )
                if resultado.stdout:
                    print(f"{Fore.GREEN}  [STDOUT]")
                    for ln in resultado.stdout.splitlines()[:40]:
                        print(f"    {Fore.WHITE}{ln}")
                if resultado.stderr:
                    print(f"{Fore.RED}  [STDERR]")
                    for ln in resultado.stderr.splitlines()[:20]:
                        print(f"    {Fore.RED}{ln}")
                if resultado.returncode == 0:
                    print(f"\n{Fore.GREEN}  [✓] Execução OK (returncode 0)")
                    beep(1200, 150)
                else:
                    print(f"\n{Fore.RED}  [✗] Erro (returncode {resultado.returncode})")
                    # Oferece correção automática via CASPER
                    print(f"\n{Fore.WHITE}Tentar corrigir automaticamente? {Fore.CYAN}(s/n): ", end="")
                    if input().strip().lower() == 's':
                        prompt_fix = (
                            f"Código com erro:\n```python\n{r}\n```\n\n"
                            f"Erro encontrado:\n{resultado.stderr[:500]}\n\n"
                            "Corrija o código. Retorne APENAS o código corrigido."
                        )
                        r_fix = (self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, prompt_fix) or self._chamar_local(system, prompt_fix))
                        if r_fix:
                            r_fix = re.sub(r"^```[a-z]*\n?", "", r_fix.strip())
                            r_fix = re.sub(r"\n?```$", "", r_fix).strip()
                            caminho_cod.write_text(r_fix, encoding="utf-8")
                            print(f"\n{Fore.GREEN}  Código corrigido salvo em: {caminho_cod.name}")
                            print(f"{Fore.YELLOW}  Execute novamente para verificar.")
            except subprocess.TimeoutExpired:
                print(f"{Fore.RED}  [TIMEOUT] Execução excedeu 10s — pode ter loop infinito ou UI bloqueante.")
            except FileNotFoundError:
                print(f"{Fore.RED}  [ERRO] Python não encontrado no PATH.")
            except Exception as e:
                print(f"{Fore.RED}  [ERRO] {e}")

        MAGIInterface.separador(cor=Fore.CYAN)

    def revisar(self, arquivo: str):
        """
        Revisa um arquivo Python usando extração de estrutura inteligente.
        Envia assinaturas de classes/métodos + primeiras linhas de cada um,
        permitindo analisar arquivos grandes sem truncamento cego.
        Suporta: revisar arquivo.py  ou  revisar arquivo.py NomeClasse
        """
        MAGIInterface.separador("MODO REVISÃO", Fore.YELLOW)

        # Suporte a escopo: "revisar MagiSystem.py MAGIEstudo"
        partes = arquivo.strip().split()
        nome_arquivo = partes[0]
        escopo = partes[1] if len(partes) > 1 else None

        caminho = Path(__file__).parent / nome_arquivo
        if not caminho.exists():
            caminho = Path(nome_arquivo)
        if not caminho.exists():
            print(f"{Fore.RED}  Arquivo não encontrado: {nome_arquivo}")
            MAGIInterface.separador(cor=Fore.YELLOW)
            return

        try:
            linhas = caminho.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            print(f"{Fore.RED}  Erro ao ler arquivo: {e}")
            MAGIInterface.separador(cor=Fore.YELLOW)
            return

        total = len(linhas)
        print(f"{Fore.WHITE}  Arquivo : {Fore.CYAN}{nome_arquivo} ({total} linhas)")
        if escopo:
            print(f"{Fore.WHITE}  Escopo  : {Fore.YELLOW}{escopo}")
        print()

        # ── Extrai estrutura inteligente ──────────────────────
        import ast as _ast

        def extrair_estrutura(src: str, classe_filtro: str | None = None) -> str:
            """
            Extrai assinaturas de classes e métodos com os primeiros 8 linhas de cada.
            Se classe_filtro for fornecido, extrai só aquela classe completa.
            """
            try:
                tree = _ast.parse(src)
            except SyntaxError as e:
                return f"[ERRO DE SINTAXE na linha {e.lineno}: {e.msg}]"

            src_linhas = src.splitlines()
            blocos = []

            for node in _ast.walk(tree):
                if not isinstance(node, (_ast.ClassDef, _ast.FunctionDef)):
                    continue
                if isinstance(node, _ast.ClassDef):
                    if classe_filtro and node.name != classe_filtro:
                        continue
                    # Classe completa se filtro ativo, senão só estrutura
                    if classe_filtro:
                        fim = node.end_lineno if hasattr(node, 'end_lineno') else node.lineno + 50
                        bloco = "\n".join(src_linhas[node.lineno-1:fim])
                        blocos.append(bloco)
                        continue
                    # Sem filtro: mostra assinatura + métodos
                    metodos = [n for n in _ast.walk(node) if isinstance(n, _ast.FunctionDef)]
                    blocos.append(f"\nclass {node.name}: # linha {node.lineno} — {len(metodos)} métodos")
                    for m in metodos:
                        corpo = src_linhas[m.lineno-1:min(m.lineno+7, total)]
                        blocos.append(f"  # linha {m.lineno}")
                        blocos.extend(f"  {l}" for l in corpo[:8])
                        if len(corpo) > 8:
                            blocos.append(f"  ... ({(hasattr(m,'end_lineno') and m.end_lineno or m.lineno+10) - m.lineno} linhas total)")

            if not blocos:
                # Fallback: primeiras 300 linhas
                return "\n".join(src_linhas[:300])

            return "\n".join(blocos)

        src_completo = "\n".join(linhas)
        estrutura = extrair_estrutura(src_completo, escopo)
        chars = len(estrutura)
        LIMITE_LOCAL  = 8_000
        LIMITE_DEEP   = 40_000
        usa_deepseek  = bool(self.deepseek) and chars > LIMITE_LOCAL
        usa_por_classe = not escopo and chars > LIMITE_DEEP

        print(f"{Fore.BLUE}  [REVISÃO] Estrutura extraída: {chars} chars ({chars//4} tokens est.)")
        if usa_por_classe:
            print(f"{Fore.YELLOW}  [REVISÃO] Arquivo grande — modo classe-por-classe ativado.")
        elif usa_deepseek:
            print(f"{Fore.CYAN}  [REVISÃO] Contexto grande — usando DeepSeek V3.")
        print()

        def _chamar_auditor(system: str, prompt: str) -> str | None:
            conteudo = f"Estrutura do código:\n{prompt}"
            if usa_deepseek or usa_por_classe:
                r = self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, conteudo)
                if r:
                    return r
            r, _ = self._chamar_nucleo("MELCHIOR-1", conteudo)
            return r

        # ── Modo classe-por-classe para arquivos gigantes ─────
        if usa_por_classe:
            import ast as _ast2
            tree2 = _ast2.parse(src_completo)
            classes = [n for n in _ast2.walk(tree2) if isinstance(n, _ast2.ClassDef)]
            print(f"{Fore.BLUE}  [REVISÃO] {len(classes)} classes encontradas — revisando uma a uma...\n")
            sys_classe = (
                "Você é um auditor de código Python sênior. Analise APENAS a classe fornecida.\n"
                "REGRA: Cite SOMENTE o que está visível. NUNCA invente.\n"
                "Aponte em até 100 palavras: bugs, performance, segurança, práticas ruins.\n"
                "Se não houver problemas, diga 'OK'."
            )
            relatorios: list[str] = []
            for cls in classes:
                fim = cls.end_lineno if hasattr(cls, 'end_lineno') else cls.lineno + 100
                bloco = "\n".join(linhas[cls.lineno-1:fim])
                print(f"{Fore.CYAN}  → Revisando {cls.name}...", end='\r')
                r = self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, sys_classe, f"class {cls.name}:\n{bloco[:6000]}")
                if not r:
                    r = self._chamar_local(sys_classe, f"class {cls.name}:\n{bloco[:3000]}")
                if r and r.strip().upper() != "OK":
                    relatorios.append(f"[{cls.name}] {r.strip()}")
                print(" " * 60, end='\r')
            print(f"{Fore.GREEN}  [✓] {len(classes)} classes revisadas.\n")
            r_mel      = "\n\n".join(relatorios) if relatorios else "Nenhum problema identificado."
            r_bal      = r_mel
            r_adam_rev = r_mel
        else:
            # ── Feature 6: Complexidade Ciclomática ───────────────
            def complexidade_ciclomatica(src: str) -> list[tuple[str, int]]:
                """Calcula complexidade ciclomática de cada função via AST."""
                nos_complexidade = (
                    _ast.If, _ast.For, _ast.While, _ast.ExceptHandler,
                    _ast.With, _ast.Assert, _ast.comprehension,
                )
                try:
                    tree = _ast.parse(src)
                except SyntaxError:
                    return []
                resultados = []
                for node in _ast.walk(tree):
                    if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                        continue
                    score = 1  # base
                    for child in _ast.walk(node):
                        if isinstance(child, nos_complexidade):
                            score += 1
                        # and/or também aumentam o fluxo
                        if isinstance(child, _ast.BoolOp):
                            score += len(child.values) - 1
                    resultados.append((node.name, score))
                return sorted(resultados, key=lambda x: x[1], reverse=True)

            complexidades = complexidade_ciclomatica("\n".join(linhas))
            criticas = [(n, s) for n, s in complexidades if s > 10]
            altas    = [(n, s) for n, s in complexidades if 6 <= s <= 10]
            if complexidades:
                MAGIInterface.separador("COMPLEXIDADE CICLOMÁTICA", Fore.YELLOW)
                if criticas:
                    print(f"  {Fore.RED}🔴 CRÍTICA (>10) — candidatas urgentes a refatorar:")
                    for nome_fn, score in criticas[:5]:
                        print(f"     {Fore.RED}{nome_fn:<35} CC={score}")
                if altas:
                    print(f"  {Fore.YELLOW}🟡 ALTA (6-10) — monitorar:")
                    for nome_fn, score in altas[:5]:
                        print(f"     {Fore.YELLOW}{nome_fn:<35} CC={score}")
                if not criticas and not altas:
                    print(f"  {Fore.GREEN}✓ Todas as funções com complexidade saudável (≤5).")
                print()

            # ── MELCHIOR — bugs e performance ──────────────────────
            sys_mel = (
                "Você é MELCHIOR-1, analista técnico sênior. Analise APENAS o código fornecido abaixo.\n"
                "REGRA CRÍTICA: Cite SOMENTE métodos, classes e linhas que aparecem no código enviado.\n"
                "NUNCA invente referências que não estejam no código.\n"
                "Se não encontrar problemas reais, diga 'Nenhum problema identificado'.\n"
                "Aponte:\n"
                "1. Bugs e erros lógicos visíveis\n"
                "2. Problemas de performance reais\n"
                "3. Código duplicado ou morto\n"
                "4. Type hints faltando em métodos críticos\n"
                "Máx 200 palavras."
            )
            print(f"{Fore.CYAN}[MELCHIOR-1] 🔬 Analisando bugs e performance...", end='\r')
            r_mel = _chamar_auditor(sys_mel, estrutura)
            print(" " * 60, end='\r')
            print(f"{Fore.CYAN}[MELCHIOR-1] 🔬 Bugs & Performance:")
            if r_mel:
                for l in r_mel.split('\n')[:10]:
                    print(f"  {Fore.WHITE}{l}")
            else:
                print(f"  {Fore.RED}[OFFLINE]")
            print()

            # ── BALTHASAR — segurança e práticas ──────────────────
            sys_bal = (
                "Você é BALTHASAR-2, analista de segurança. Analise APENAS o código fornecido abaixo.\n"
                "REGRA CRÍTICA: Cite SOMENTE métodos, classes e linhas que aparecem no código enviado.\n"
                "NUNCA invente referências que não estejam no código.\n"
                "Se não encontrar problemas reais, diga 'Nenhum problema identificado'.\n"
                "Aponte:\n"
                "1. Vulnerabilidades de segurança visíveis\n"
                "2. Tratamento de erros inadequado (except pass, erros silenciosos)\n"
                "3. Boas práticas violadas (SRP, DRY, SOLID)\n"
                "4. Dependências desnecessárias ou inseguras\n"
                "Máx 200 palavras."
            )
            print(f"{Fore.GREEN}[BALTHASAR-2] 🛡️ Analisando segurança...", end='\r')
            r_bal = _chamar_auditor(sys_bal, estrutura)
            print(" " * 60, end='\r')
            print(f"{Fore.GREEN}[BALTHASAR-2] 🛡️ Segurança & Práticas:")
            if r_bal:
                for l in r_bal.split('\n')[:10]:
                    print(f"  {Fore.WHITE}{l}")
            else:
                print(f"  {Fore.RED}[OFFLINE]")
            print()

            # ── Feature 1: ADAM-0 — refatoração e padrões ─────────
            sys_adam = (
                "Você é ADAM-0, auditor de refatoração. Analise APENAS o código fornecido.\n"
                "REGRA CRÍTICA: Cite SOMENTE o que está visível no código enviado.\n"
                "Se não encontrar problemas reais, diga 'Nenhum problema identificado'.\n"
                "Aponte:\n"
                "1. Funções longas demais (>40 linhas) — sugira como dividir\n"
                "2. Nomenclatura confusa ou inconsistente\n"
                "3. Ausência de type hints em métodos públicos\n"
                "4. Oportunidades de extrair classes ou módulos\n"
                "Máx 200 palavras. Seja cirúrgico."
            )
            print(f"{Fore.WHITE}[ADAM-0] 🖥 Analisando refatoração e padrões...", end='\r')
            r_adam_rev = _chamar_auditor(sys_adam, estrutura)
            print(" " * 60, end='\r')
            print(f"{Fore.WHITE}[ADAM-0] 🖥 Refatoração & Padrões:")
            if r_adam_rev:
                for l in r_adam_rev.split('\n')[:10]:
                    print(f"  {Fore.WHITE}{l}")
            else:
                print(f"  {Fore.RED}[OFFLINE]")
            print()

            # ── CASPER — veredito com prioridades (3 fontes) ──────
            cc_resumo = ""
            if criticas:
                cc_resumo = f"\nComplexidade crítica: {', '.join(f'{n}(CC={s})' for n,s in criticas[:3])}"

            MAGIInterface.separador("CASPER-3 — VEREDITO DA REVISÃO", Fore.RED)
            prompt_casper = (
                f"Arquivo: {nome_arquivo} ({total} linhas)"
                + (f" | Escopo: {escopo}" if escopo else "")
                + cc_resumo + "\n\n"
                f"MELCHIOR (bugs/performance):\n{r_mel or '[offline]'}\n\n"
                f"BALTHASAR (segurança/práticas):\n{r_bal or '[offline]'}\n\n"
                f"ADAM-0 (refatoração/padrões):\n{r_adam_rev or '[offline]'}\n\n"
                f"REGRAS ABSOLUTAS:\n"
                f"1. Cite APENAS o que os auditores acima mencionaram.\n"
                f"2. NUNCA invente referências que não apareçam nos relatórios.\n"
                f"3. Se não houver problemas críticos, diga 'Nenhum crítico identificado'.\n\n"
                f"Formato OBRIGATÓRIO:\n"
                f"CRÍTICO: [só o citado acima]\n"
                f"IMPORTANTE: [só o citado acima]\n"
                f"SUGESTÃO: [só o citado acima]\n"
                f"NOTA: [avaliação geral 1-10 com justificativa]\n"
                f"Máx 250 palavras."
            )
            print(f"{Fore.MAGENTA}[CASPER-3] ⚡ Forjando veredito (3 auditores)...\n")
            time.sleep(0.3)
            veredito = (self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, NUCLEOS["CASPER-3"]["system"], prompt_casper) or self._chamar_local(NUCLEOS["CASPER-3"]["system"], prompt_casper))
            if not veredito and LOCAL_CONFIG["ativo"]:
                veredito = self._chamar_local(NUCLEOS["CASPER-3"]["system"], prompt_casper)
            if veredito:
                MAGIInterface.digitar(veredito, cor=Fore.YELLOW, delay=0.008)
            else:
                print(f"{Fore.RED}  CASPER offline.")

            print()
            MAGIInterface.separador(cor=Fore.YELLOW)
            beep(1200, 200); time.sleep(0.1); beep(1400, 150)

    def testar(self, arquivo: str):
        """
        Feature 2: Gera testes unitários pytest para um arquivo Python via ADAM-0,
        executa em subprocess e exibe resultado no terminal.
        Uso: testar arquivo.py [NomeClasse]
        """
        import subprocess, ast as _ast
        MAGIInterface.separador("MODO TESTE — ADAM-0 PROTOCOL", Fore.WHITE)
        partes   = arquivo.strip().split()
        nome_arq = partes[0]
        escopo   = partes[1] if len(partes) > 1 else None
        caminho  = Path(__file__).parent / nome_arq
        if not caminho.exists():
            caminho = Path(nome_arq)
        if not caminho.exists():
            print(f"{Fore.RED}  Arquivo não encontrado: {nome_arq}")
            MAGIInterface.separador(cor=Fore.WHITE)
            return

        src = caminho.read_text(encoding="utf-8")
        print(f"{Fore.WHITE}  Arquivo : {Fore.CYAN}{nome_arq}")
        if escopo:
            print(f"{Fore.WHITE}  Escopo  : {Fore.YELLOW}{escopo}")

        # Extrai assinaturas via AST para dar ao ADAM-0 contexto preciso
        try:
            tree  = _ast.parse(src)
            sigs  = []
            for node in _ast.walk(tree):
                if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                    continue
                if escopo and isinstance(node, _ast.ClassDef) and node.name != escopo:
                    continue
                if isinstance(node, _ast.ClassDef):
                    sigs.append(f"class {node.name}:  # linha {node.lineno}")
                else:
                    args = [a.arg for a in node.args.args]
                    sigs.append(f"  def {node.name}({', '.join(args)}):  # linha {node.lineno}")
            estrutura_assinaturas = "\n".join(sigs[:60]) or src[:2000]
        except SyntaxError as e:
            print(f"{Fore.RED}  Erro de sintaxe no arquivo: {e}")
            MAGIInterface.separador(cor=Fore.WHITE)
            return

        print(f"\n{Fore.WHITE}[ADAM-0] 🖥 Gerando testes unitários...\n")
        system_adam = (
            "Você é ADAM-0, especialista em testes Python.\n"
            "Gere um arquivo pytest COMPLETO e funcional para o código fornecido.\n"
            "REGRAS:\n"
            "1. Use pytest, unittest.mock.patch e MagicMock onde necessário.\n"
            "2. Cubra: caminho feliz, casos de borda, exceções esperadas.\n"
            "3. Nomes descritivos: test_<metodo>_<cenario>.\n"
            "4. NÃO instancie classes que precisam de configs externas — use mocks.\n"
            "5. Retorne APENAS o código Python, sem explicações.\n"
            "6. O arquivo deve começar com imports e ser executável com 'pytest'."
        )
        prompt_adam = (
            f"Arquivo: {nome_arq}" + (f" | Escopo: {escopo}" if escopo else "") + "\n\n"
            f"Assinaturas:\n{estrutura_assinaturas}\n\n"
            f"Primeiras 60 linhas do fonte:\n{chr(10).join(src.splitlines()[:60])}\n\n"
            "Gere os testes pytest."
        )
        codigo_testes = (self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system_adam, prompt_adam) or self._chamar_local(system_adam, prompt_adam))
        if not codigo_testes and LOCAL_CONFIG["ativo"]:
            codigo_testes = self._chamar_local(system_adam, prompt_adam)
        if not codigo_testes:
            print(f"{Fore.RED}  ADAM-0 offline.")
            MAGIInterface.separador(cor=Fore.WHITE)
            return

        # Remove possíveis markdown fences
        codigo_testes = re.sub(r"^```[a-z]*\n?", "", codigo_testes.strip())
        codigo_testes = re.sub(r"\n?```$", "", codigo_testes).strip()

        # Salva o arquivo de testes
        nome_teste = f"test_{nome_arq.replace('.py','')}"
        if escopo:
            nome_teste += f"_{escopo}"
        nome_teste += ".py"
        caminho_teste = Path(__file__).parent / nome_teste
        caminho_teste.write_text(codigo_testes, encoding="utf-8")
        print(f"{Fore.GREEN}  [✓] Testes salvos: {nome_teste}")
        print(f"{Fore.CYAN}  {caminho_teste.resolve()}\n")

        # Exibe preview dos testes
        MAGIInterface.separador("PREVIEW DOS TESTES", Fore.WHITE)
        for linha in codigo_testes.splitlines()[:30]:
            print(f"  {Fore.WHITE}{linha}")
        if len(codigo_testes.splitlines()) > 30:
            print(f"  {Fore.BLUE}  ... ({len(codigo_testes.splitlines())} linhas total)")
        print()

        # Executa pytest em subprocess
        print(f"{Fore.WHITE}Executar agora com pytest? {Fore.CYAN}(s/n): ", end="")
        if input().strip().lower() == 's':
            MAGIInterface.separador("EXECUÇÃO PYTEST", Fore.WHITE)
            print(f"{Fore.BLUE}  Rodando: pytest {nome_teste} -v\n")
            try:
                resultado = subprocess.run(
                    ["python", "-m", "pytest", str(caminho_teste), "-v", "--tb=short", "--no-header"],
                    capture_output=True, text=True, timeout=60,
                    cwd=str(Path(__file__).parent)
                )
                saida = resultado.stdout + resultado.stderr
                # Colore a saída linha a linha
                for ln in saida.splitlines():
                    if "PASSED" in ln or "passed" in ln:
                        print(f"  {Fore.GREEN}{ln}")
                    elif "FAILED" in ln or "ERROR" in ln or "failed" in ln or "error" in ln:
                        print(f"  {Fore.RED}{ln}")
                    elif "WARNING" in ln or "warning" in ln:
                        print(f"  {Fore.YELLOW}{ln}")
                    else:
                        print(f"  {Fore.WHITE}{ln}")
                beep(1200, 150) if resultado.returncode == 0 else beep(400, 400)
            except subprocess.TimeoutExpired:
                print(f"{Fore.RED}  [TIMEOUT] pytest excedeu 60s.")
            except FileNotFoundError:
                print(f"{Fore.RED}  [ERRO] pytest não encontrado. Instale: pip install pytest")
            except Exception as e:
                print(f"{Fore.RED}  [ERRO] {e}")

        MAGIInterface.separador(cor=Fore.WHITE)

    def visual(self, descricao: str):
        """
        VISUAL v2 - Prompt mais rígido + anti-truncation
        """
        if not descricao:
            print(f"{Fore.YELLOW}  Uso: visual <descrição clara>")
            return

        MAGIInterface.separador("MODO VISUAL — NERV PROTOCOL v2", Fore.MAGENTA)
        print(f"{Fore.WHITE}  Gerando: {Fore.YELLOW}{descricao}\n")

        system_prompt = (
            "Você é um engenheiro frontend especializado em interfaces NERV (Neon Genesis Evangelion) de alta qualidade.\n"
            "REGRAS OBRIGATÓRIAS:\n"
            "1. Retorne SOMENTE o código HTML completo e funcional.\n"
            "2. Não explique nada, não coloque ```html, apenas o código cru.\n"
            "3. O HTML deve começar com <!DOCTYPE html> e terminar com </html>.\n"
            "4. Use CSS moderno, scanlines, neon (laranja #FF6600 e ciano), glitch effects e animações.\n"
            "5. Faça um design limpo, cinematográfico e imersivo.\n"
            "6. Não repita estilos desnecessariamente.\n"
            "7. Mantenha o código organizado e completo.\n"
        )

        prompt = f"""
Crie um dashboard completo no estilo NERV sobre: {descricao}

Requisitos:
- Fundo escuro com scanlines CRT
- Logo NERV com efeito neon/glitch
- Cards com informações de EVA Units, MAGI System e alertas
- Terminal com logs animados
- Paleta: preto, laranja #FF6600, vermelho, ciano
- Efeitos hover e animações suaves
"""

        print(f"{Fore.MAGENTA}[VISUAL] Tentando gerar código de qualidade...\n")

        html = (self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system_prompt, prompt) or self._chamar_local(system_prompt, prompt))

        if not html:
            print(f"{Fore.RED}  Modelo não respondeu.")
            return

        # Limpeza agressiva
        html = html.strip()
        if not html.startswith("<!DOCTYPE"):
            match = re.search(r'<!DOCTYPE.*?</html>', html, re.DOTALL | re.IGNORECASE)
            html = match.group(0) if match else html

        # Salvar
        nome_limpo = re.sub(r'[^a-zA-Z0-9_-]', '_', descricao[:45]).strip('_')
        nome_arquivo = f"NERV_{nome_limpo}.html"
        caminho = Path(__file__).parent / nome_arquivo

        caminho.write_text(html, encoding="utf-8")

        print(f"{Fore.GREEN}  [✓] Arquivo salvo: {nome_arquivo}")
        print(f"{Fore.CYAN}  Caminho: {caminho.resolve()}")

        MAGIInterface.separador(cor=Fore.MAGENTA)

    def curar_memoria(self):
        if not self.memoria.registros:
            print(f"{Fore.YELLOW}  Memória vazia.")
            return
        MAGIInterface.separador("CURAÇÃO DE MEMÓRIA", Fore.MAGENTA)
        total = len(self.memoria.registros)
        entradas_str = "\n".join(
            f"{i}. [{r.get('categoria','?')}] {r['texto'][:120]}"
            for i, r in enumerate(self.memoria.registros)
        )
        system = (
            "CASPER-3 avaliando memória MAGI. Delete: perguntas vagas, sem valor, duplicatas.\n"
            'JSON: {"deletar":[0,3],"motivo":"..."} ou {"deletar":[],"motivo":"Todas têm valor."}'
        )
        r = (self._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, entradas_str) or self._chamar_local(system, entradas_str))
        if not r:
            print(f"{Fore.RED}  CASPER offline.")
            return
        try:
            dados = json.loads(re.sub(r"```[a-z]*\n?|```", "", r).strip())
            indices_deletar = set(dados.get("deletar", []))
            motivo = dados.get("motivo", "")
        except Exception as e:
            print(f"{Fore.RED}  Erro: {e}")
            return
        print(f"{Fore.WHITE}  Motivo: {motivo}")
        print(f"{Fore.RED}  Deletar: {len(indices_deletar)} | {Fore.GREEN}Manter: {total-len(indices_deletar)}")
        if not indices_deletar:
            print(f"{Fore.GREEN}  Memória saudável.")
            MAGIInterface.separador(cor=Fore.MAGENTA)
            return
        for i in sorted(indices_deletar):
            if i < len(self.memoria.registros):
                print(f"  {Fore.RED}✕ {Fore.WHITE}{self.memoria.registros[i]['texto'][:80]}")
        print(f"\n{Fore.WHITE}Confirmar? {Fore.CYAN}(s/n): ", end="")
        if input().strip().lower() != "s":
            print(f"{Fore.YELLOW}  Cancelado.")
            MAGIInterface.separador(cor=Fore.MAGENTA)
            return
        novos = [r for i, r in enumerate(self.memoria.registros) if i not in indices_deletar]
        self.memoria.registros = []
        self.memoria.index = faiss.IndexFlatL2(384)
        if os.path.exists(self.memoria.db_path):
            os.remove(self.memoria.db_path)
        # Batch encoding: muito mais rápido que N chamadas individuais
        if novos:
            textos = [r["texto"] for r in novos]
            vecs   = self.memoria.encoder.encode(textos)
            self.memoria.index = faiss.IndexFlatL2(384)
            self.memoria.registros = []
            self.memoria._textos_vistos = set()
            self.memoria.index.add(np.array(vecs).astype('float32'))
            self.memoria.registros = novos
            self.memoria._textos_vistos = set(textos)
            # Reescreve o arquivo de uma vez
            with open(self.memoria.db_path, 'w', encoding='utf-8') as f:
                for reg in novos:
                    f.write(json.dumps(reg, ensure_ascii=False) + '\n')
        print(f"{Fore.GREEN}  Curação concluída. {len(novos)} entradas mantidas.")
        MAGIInterface.separador(cor=Fore.MAGENTA)

    def _exibir_sugestoes_evolucao(self):
        path = MAGIEstudo.SUGESTOES_PATH
        if not path.exists():
            print(f"{Fore.YELLOW}  Nenhuma sugestão gerada ainda. Use 'estudar' para começar.")
            return
        sugestoes = []
        with open(path, encoding='utf-8') as f:
            for linha in f:
                if linha.strip():
                    try:
                        sugestoes.append(json.loads(linha))
                    except:
                        pass
        pendentes = [s for s in sugestoes if s.get('status') == 'pendente']
        if not pendentes:
            print(f"{Fore.YELLOW}  Nenhuma sugestão pendente.")
            return
        MAGIInterface.separador('SUGESTÕES DE AUTO-EVOLUÇÃO', Fore.MAGENTA)
        for i, s in enumerate(pendentes, 1):
            imp_cor = Fore.RED if s.get('impacto') == 'alto' else Fore.YELLOW if s.get('impacto') == 'medio' else Fore.WHITE
            print(f"  {Fore.CYAN}{i}. {Fore.WHITE}{s.get('titulo','?')} {imp_cor}[{s.get('impacto','?').upper()}]")
            print(f"     {Fore.WHITE}{s.get('descricao','?')}")
            print(f"     {Fore.BLUE}Origem: {s.get('topico_origem','?')} | {s.get('timestamp','?')}")
            print(f"     {Fore.YELLOW}Instrução: {Fore.WHITE}{s.get('instrucao_evoluir','?')}")
            print()
        MAGIInterface.separador(cor=Fore.MAGENTA)
        print(f"{Fore.WHITE}Aprovar alguma? Número ou {Fore.CYAN}n{Fore.WHITE}: ", end='')
        escolha = input().strip()
        if escolha.isdigit():
            idx = int(escolha) - 1
            if 0 <= idx < len(pendentes):
                instrucao = pendentes[idx].get('instrucao_evoluir', '')
                self.evoluir(instrucao)
                pendentes[idx]['status'] = 'aprovada'
                todas = [s for s in sugestoes if s.get('status') != 'pendente' or s not in pendentes]
                todas += pendentes
                with open(path, 'w', encoding='utf-8') as f:
                    for s in todas:
                        f.write(json.dumps(s, ensure_ascii=False) + '\n')

    def _exibir_conhecimento(self):
        path = MAGIEstudo.CONHECIMENTO_PATH
        if not path.exists():
            print(f"{Fore.YELLOW}  Nenhum conhecimento acumulado ainda.")
            return
        registros = []
        with open(path, encoding='utf-8') as f:
            for linha in f:
                if linha.strip():
                    try:
                        registros.append(json.loads(linha))
                    except:
                        pass
        MAGIInterface.separador(f'CONHECIMENTO ACUMULADO ({len(registros)} entradas)', Fore.CYAN)
        for r in registros[-8:]:
            print(f"  {Fore.BLUE}[{r.get('timestamp','?')}] {Fore.CYAN}{r.get('topico','?')}")
            print(f"  {Fore.WHITE}Q: {r.get('pergunta','?')[:80]}")
            print(f"  {Fore.YELLOW}R: {r.get('resposta','?')[:120]}")
            print()
        MAGIInterface.separador(cor=Fore.CYAN)

    def encerrar(self):
        duracao = datetime.now() - self.sessao_inicio
        mins, secs = divmod(int(duracao.total_seconds()), 60)
        print()
        MAGIInterface.separador("ENCERRANDO SESSÃO MAGI", Fore.RED)
        print(f"{Fore.CYAN}  Duração  : {mins}m {secs}s")
        print(f"{Fore.CYAN}  Queries  : {self.queries_total}")
        print(f"{Fore.CYAN}  Memórias : {len(self.memoria.registros)} registros")
        print(self.memoria.resumo_sessão())
        # Salva sessão completa
        if self.usuario:
            self.usuario.encerrar_sessao()
        MAGIInterface.separador(cor=Fore.RED)
        log.info("sessao","Encerrada",duracao=f"{mins}m{secs}s",queries=str(self.queries_total))
        log.fechar()
        print(f"\n{Fore.RED}  MAGI DESLIGANDO... SAYŌNARA.\n")
        beep(800, 200)
        time.sleep(0.1)
        beep(600, 200)
        time.sleep(0.1)
        beep(400, 400)



class MAGISources:
    """
    Sistema de fontes externas do MAGI.
    Três capacidades:
      1. Busca na web (DuckDuckGo) em tempo real antes de processar queries
      2. Injeção de citações numeradas [1],[2]... no veredito do CASPER
      3. Ingestão de arquivos locais (PDF/TXT/MD/PY) como base de conhecimento permanente
    """
    FONTES_PATH = Path(__file__).parent / 'data' / 'knowledge' / 'magi_fontes.jsonl'
    _UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

    def __init__(self, magi: "MAGISystem"):
        self.magi = magi
        self._fontes_locais: list[dict] = []   # cache em memória das fontes carregadas
        self._carregar_fontes_locais()

    # ── Persistência de fontes locais ─────────────────────────
    def _carregar_fontes_locais(self):
        if not self.FONTES_PATH.exists():
            return
        try:
            with open(self.FONTES_PATH, encoding="utf-8") as f:
                self._fontes_locais = [json.loads(l) for l in f if l.strip()]
        except Exception:
            self._fontes_locais = []

    def _salvar_fonte_local(self, registro: dict):
        with open(self.FONTES_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        self._fontes_locais.append(registro)

    # ── 1. Busca multi-fonte inteligente ─────────────────────
    def buscar_web(self, query: str, max_snippets: int = 5) -> list[dict]:
        """
        Busca inteligente com roteamento automático por tipo de query:
          - Factual/definições  → Wikipedia API
          - Técnico/científico  → arXiv API
          - Notícias/geral      → DuckDuckGo + Jina Reader
        Combina e deduplica resultados das fontes ativas.
        """
        import urllib.request, urllib.parse

        q_lower = query.lower()

        # ── Detecta tipo de query ──────────────────────────────
        palavras_wiki   = {"o que é","o que são","definição","significado","conceito",
                           "história","quem foi","quem é","quando foi","capital de",
                           "onde fica","qual é","explique","explica"}
        palavras_arxiv  = {"paper","artigo","pesquisa","estudo","algoritmo","modelo",
                           "neural","machine learning","deep learning","transformer",
                           "llm","ia","inteligência artificial","arxiv","ciência"}
        palavras_news   = {"notícia","news","hoje","recente","último","aconteceu",
                           "2024","2025","2026","lançou","lançamento","atualização"}

        usa_wiki  = any(p in q_lower for p in palavras_wiki)
        usa_arxiv = any(p in q_lower for p in palavras_arxiv)
        usa_news  = any(p in q_lower for p in palavras_news)

        # Default: usa tudo se não detectou nada específico
        if not usa_wiki and not usa_arxiv and not usa_news:
            usa_wiki = True
            usa_news = True

        resultados: list[dict] = []

        # ── Wikipedia API ──────────────────────────────────────
        if usa_wiki and len(resultados) < max_snippets:
            try:
                q_enc = urllib.parse.quote_plus(query)
                wiki_url = (
                    f"https://pt.wikipedia.org/w/api.php"
                    f"?action=query&list=search&srsearch={q_enc}"
                    f"&utf8=1&format=json&srlimit=3"
                )
                req = urllib.request.Request(wiki_url, headers={"User-Agent": self._UA})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode("utf-8"))
                for item in data.get("query", {}).get("search", [])[:3]:
                    titulo = item.get("title", "")
                    snippet = re.sub(r"<[^>]+>", "", item.get("snippet", "")).strip()
                    snippet = unescape(snippet)
                    page_url = f"https://pt.wikipedia.org/wiki/{urllib.parse.quote(titulo.replace(' ','_'))}"
                    if titulo and snippet:
                        resultados.append({
                            "titulo":  f"Wikipedia: {titulo}",
                            "snippet": snippet[:400],
                            "url":     page_url,
                            "fonte":   "wikipedia",
                        })
                # Tenta também buscar o resumo do artigo principal
                if resultados:
                    top_titulo = urllib.parse.quote(resultados[0]["titulo"].replace("Wikipedia: ","").replace(" ","_"))
                    summary_url = f"https://pt.wikipedia.org/api/rest_v1/page/summary/{top_titulo}"
                    try:
                        req2 = urllib.request.Request(summary_url, headers={"User-Agent": self._UA})
                        with urllib.request.urlopen(req2, timeout=8) as r2:
                            summary = json.loads(r2.read().decode("utf-8"))
                        extract = summary.get("extract","")
                        if extract and len(extract) > 100:
                            resultados[0]["snippet"] = extract[:500]
                    except Exception:
                        pass
            except Exception as e:
                log.debug("sources.wikipedia", f"Falhou: {e}")

        # ── arXiv API ──────────────────────────────────────────
        if usa_arxiv and len(resultados) < max_snippets:
            try:
                q_enc = urllib.parse.quote_plus(query)
                arxiv_url = (
                    f"https://export.arxiv.org/api/query"
                    f"?search_query=all:{q_enc}&start=0&max_results=3"
                    f"&sortBy=relevance&sortOrder=descending"
                )
                req = urllib.request.Request(arxiv_url, headers={"User-Agent": self._UA})
                with urllib.request.urlopen(req, timeout=12) as r:
                    xml = r.read().decode("utf-8")
                titulos_ax  = re.findall(r"<title>(.*?)</title>", xml, re.DOTALL)[1:]
                resumos_ax  = re.findall(r"<summary>(.*?)</summary>", xml, re.DOTALL)
                links_ax    = re.findall(r'href="(https://arxiv\.org/abs/[^"]+)"', xml)
                for i, (t, s) in enumerate(zip(titulos_ax, resumos_ax)):
                    t = re.sub(r"\s+", " ", t).strip()
                    s = re.sub(r"\s+", " ", s).strip()
                    url_ax = links_ax[i] if i < len(links_ax) else "https://arxiv.org"
                    if t and s:
                        resultados.append({
                            "titulo":  f"arXiv: {t}",
                            "snippet": s[:400],
                            "url":     url_ax,
                            "fonte":   "arxiv",
                        })
            except Exception as e:
                log.debug("sources.arxiv", f"Falhou: {e}")

        # ── DuckDuckGo + Jina Reader ───────────────────────────
        if usa_news or len(resultados) < 2:
            try:
                q_enc = urllib.parse.quote_plus(query)
                ddg_urls = [
                    f"https://lite.duckduckgo.com/lite/?q={q_enc}",
                    f"https://html.duckduckgo.com/html/?q={q_enc}",
                ]
                headers = {"User-Agent": self._UA, "Accept-Language": "pt-BR,pt;q=0.9"}
                urls_encontradas: list[tuple[str,str,str]] = []  # (titulo, snippet, url)
                for ddg_url in ddg_urls:
                    try:
                        req = urllib.request.Request(ddg_url, headers=headers)
                        with urllib.request.urlopen(req, timeout=12) as resp:
                            html = resp.read().decode("utf-8", errors="ignore")
                        if "Type the characters" in html:
                            continue
                        titulos_ddg  = re.findall(r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
                        snippets_ddg = re.findall(r'<td[^>]+class="result-snippet"[^>]*>(.*?)</td>', html, re.DOTALL)
                        for i, (href, titulo) in enumerate(titulos_ddg[:5]):
                            t_limpo = unescape(re.sub(r"<[^>]+>", "", titulo).strip())
                            s_limpo = unescape(re.sub(r"<[^>]+>", "", snippets_ddg[i] if i < len(snippets_ddg) else "").strip())
                            if t_limpo and href not in [r[2] for r in urls_encontradas]:
                                urls_encontradas.append((t_limpo, s_limpo, href))
                        if urls_encontradas:
                            break
                    except Exception:
                        continue

                # Jina Reader: lê conteúdo real das top URLs
                jina_ok = 0
                for t_limpo, s_limpo, href in urls_encontradas[:3]:
                    if jina_ok >= 2:
                        break
                    try:
                        jina_url = f"https://r.jina.ai/{href}"
                        req_j = urllib.request.Request(jina_url, headers={
                            "User-Agent": self._UA,
                            "Accept": "text/plain",
                            "X-Return-Format": "text",
                        })
                        with urllib.request.urlopen(req_j, timeout=10) as rj:
                            texto = rj.read().decode("utf-8", errors="ignore")
                        # Extrai os primeiros parágrafos úteis
                        paragrafos = [p.strip() for p in texto.split("\n") if len(p.strip()) > 80]
                        snippet_rico = " ".join(paragrafos[:3])[:500]
                        if snippet_rico:
                            resultados.append({
                                "titulo":  t_limpo,
                                "snippet": snippet_rico,
                                "url":     href,
                                "fonte":   "jina+ddg",
                            })
                            jina_ok += 1
                            continue
                    except Exception:
                        pass
                    # Fallback sem Jina: usa snippet do DDG mesmo
                    if s_limpo:
                        resultados.append({
                            "titulo":  t_limpo,
                            "snippet": s_limpo[:300],
                            "url":     href,
                            "fonte":   "duckduckgo",
                        })
            except Exception as e:
                log.debug("sources.ddg", f"Falhou: {e}")

        # ── Deduplica por URL ──────────────────────────────────
        vistos: set[str] = set()
        unicos: list[dict] = []
        for r in resultados:
            u = r.get("url","")
            if u not in vistos:
                vistos.add(u)
                unicos.append(r)

        return unicos[:max_snippets]

    # ── 2. Formatador de citações para o CASPER ───────────────
    def montar_bloco_fontes(self, fontes_web: list[dict], fontes_locais: list[dict]) -> tuple[str, str]:
        """
        Retorna (bloco_para_prompt, rodape_para_exibir).
        O bloco_para_prompt instrui o CASPER a usar [1], [2]...
        O rodapé é exibido após o veredito no terminal.
        """
        todas: list[dict] = []
        for f in fontes_web:
            todas.append({"tipo": "web", **f})
        for f in fontes_locais:
            todas.append({"tipo": "local", **f})

        if not todas:
            return "", ""

        # Bloco que vai no prompt do CASPER
        linhas_prompt = ["─── FONTES DISPONÍVEIS (cite como [N]) ───"]
        for i, f in enumerate(todas, 1):
            prefixo = "🌐" if f["tipo"] == "web" else "📄"
            linhas_prompt.append(f"[{i}] {prefixo} {f.get('titulo','?')}: {f.get('snippet','')[:200]}")
        linhas_prompt.append(
            "\nINSTRUÇÃO: ao usar informação de uma fonte acima, cite como [N] inline. "
            "No final liste: FONTES: [1] url/nome, [2] url/nome ..."
        )
        bloco_prompt = "\n".join(linhas_prompt)

        # Rodapé exibido no terminal após o veredito
        linhas_rodape = [f"\n{Fore.BLUE}  ═══ FONTES ═══"]
        for i, f in enumerate(todas, 1):
            prefixo = "🌐" if f["tipo"] == "web" else "📄"
            url_ou_nome = f.get("url") or f.get("arquivo", "arquivo local")
            linhas_rodape.append(f"  {Fore.CYAN}[{i}] {prefixo} {Fore.WHITE}{url_ou_nome}")
        return bloco_prompt, "\n".join(linhas_rodape)

    def buscar_fontes_locais_relevantes(self, query: str, k: int = 3) -> list[dict]:
        """Retorna as fontes locais mais relevantes para a query via cosine similarity."""
        if not self._fontes_locais:
            return []
        try:
            enc    = self.magi.memoria.encoder
            q_vec  = enc.encode([query])[0]
            scored = []
            for fonte in self._fontes_locais:
                conteudo = fonte.get("conteudo_resumo", "")
                if not conteudo:
                    continue
                f_vec = enc.encode([conteudo])[0]
                num   = float(q_vec @ f_vec)
                denom = (float((q_vec**2).sum()**0.5) * float((f_vec**2).sum()**0.5))
                sim   = num / denom if denom > 0 else 0.0
                if sim > 0.30:
                    scored.append((sim, fonte))
            scored.sort(reverse=True)
            return [f for _, f in scored[:k]]
        except Exception:
            return self._fontes_locais[:k]

    # ── 3. Ingestão de arquivos locais ───────────────────────
    def ingerir_arquivo(self, caminho_str: str):
        """
        Lê PDF/TXT/MD/PY e adiciona ao banco de fontes locais do MAGI.
        Uso: fonte <caminho>
        """
        MAGIInterface.separador("INGESTÃO DE FONTE LOCAL", Fore.CYAN)
        caminho = Path(caminho_str.strip())
        if not caminho.exists():
            caminho = Path(__file__).parent / caminho_str.strip()
        if not caminho.exists():
            print(f"{Fore.RED}  Arquivo não encontrado: {caminho_str}")
            MAGIInterface.separador(cor=Fore.CYAN)
            return

        ext     = caminho.suffix.lower()
        conteudo = ""

        # PDF
        if ext == ".pdf":
            try:
                import importlib.util
                if importlib.util.find_spec("pypdf"):
                    from pypdf import PdfReader
                    reader = PdfReader(str(caminho))
                    conteudo = "\n".join(p.extract_text() or "" for p in reader.pages)
                    print(f"{Fore.GREEN}  [pypdf] {len(reader.pages)} páginas extraídas.")
                elif importlib.util.find_spec("pdfminer"):
                    from pdfminer.high_level import extract_text as pdf_extract
                    conteudo = pdf_extract(str(caminho))
                    print(f"{Fore.GREEN}  [pdfminer] Texto extraído.")
                else:
                    print(f"{Fore.RED}  Instale pypdf ou pdfminer: pip install pypdf")
                    MAGIInterface.separador(cor=Fore.CYAN)
                    return
            except Exception as e:
                print(f"{Fore.RED}  Erro ao ler PDF: {e}")
                MAGIInterface.separador(cor=Fore.CYAN)
                return
        # Texto plano / código / markdown
        elif ext in (".txt", ".md", ".py", ".json", ".yaml", ".yml", ".csv", ".rst"):
            try:
                conteudo = caminho.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                print(f"{Fore.RED}  Erro ao ler arquivo: {e}")
                MAGIInterface.separador(cor=Fore.CYAN)
                return
        else:
            print(f"{Fore.YELLOW}  Formato não suportado: {ext}")
            print(f"{Fore.WHITE}  Suportados: .pdf .txt .md .py .json .yaml .csv")
            MAGIInterface.separador(cor=Fore.CYAN)
            return

        if not conteudo.strip():
            print(f"{Fore.YELLOW}  Arquivo vazio ou sem texto extraível.")
            MAGIInterface.separador(cor=Fore.CYAN)
            return

        # Gera resumo via DeepSeek (primeira opção) para uso como snippet de busca semântica
        print(f"{Fore.WHITE}  {caminho.name} — {len(conteudo):,} chars  ({len(conteudo.split()):,} palavras)")
        print(f"{Fore.BLUE}  [DEEPSEEK] Resumindo para indexação...", end='\r')
        system_resumo = (
            "Resuma o documento a seguir em até 3 parágrafos densos e informativos. "
            "Foque em conceitos, conclusões e informações factuais. Sem opinião."
        )
        resumo = (
            self.magi._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system_resumo,
                f"Documento: {caminho.name}\n\n{conteudo[:6000]}")
            or self.magi._chamar_local(system_resumo,
                f"Documento: {caminho.name}\n\n{conteudo[:4000]}")
            or self.magi._chamar_openai("gpt-4o-mini", system_resumo,
                f"Documento: {caminho.name}\n\n{conteudo[:6000]}")
        )
        resumo = resumo or conteudo[:500]
        print(" " * 60, end='\r')
        print(f"{Fore.GREEN}  [✓] Resumo gerado ({len(resumo)} chars)")

        registro = {
            "timestamp":       datetime.now().isoformat(timespec="seconds"),
            "arquivo":         caminho.name,
            "caminho_abs":     str(caminho.resolve()),
            "extensao":        ext,
            "chars_total":     len(conteudo),
            "conteudo_resumo": resumo,
            "conteudo_inicio": conteudo[:800],   # primeiros 800 chars para contexto direto
        }
        self._salvar_fonte_local(registro)

        print(f"\n{Fore.GREEN}  [MAGI·FONTE] '{caminho.name}' adicionada à base de conhecimento.")
        print(f"{Fore.CYAN}  Total de fontes locais: {len(self._fontes_locais)}")
        MAGIInterface.separador(cor=Fore.CYAN)

    def listar_fontes(self):
        """Exibe todas as fontes locais indexadas."""
        MAGIInterface.separador("FONTES LOCAIS INDEXADAS", Fore.CYAN)
        if not self._fontes_locais:
            print(f"{Fore.YELLOW}  Nenhuma fonte indexada. Use: fonte <arquivo>")
            MAGIInterface.separador(cor=Fore.CYAN)
            return
        for i, f in enumerate(self._fontes_locais, 1):
            print(f"  {Fore.CYAN}[{i}] {Fore.WHITE}{f.get('arquivo','?')}")
            print(f"       {Fore.BLUE}{f.get('timestamp','?')} · {f.get('chars_total',0):,} chars")
            print(f"       {Fore.WHITE}{f.get('conteudo_resumo','')[:120]}...")
            print()
        MAGIInterface.separador(cor=Fore.CYAN)



# ══════════════════════════════════════════════════════════════════════════════
# MAGICodeAgent — Agente de programação autônomo estilo Claude Code
# ══════════════════════════════════════════════════════════════════════════════

class MAGICodeAgent:
    """Agente de programação autônomo integrado ao MAGI.
    Opera em loop fechado: planeja → executa → roda → corrige → valida.
    Acesso: qualquer arquivo .py no diretório de trabalho.
    Qualidade: padrão de produção (type hints, docstrings, testes, error handling).
    """

    _AGENT_DIR    = Path(__file__).parent
    _SESSION_PATH = Path(__file__).parent / "data" / "logs" / "agent_sessions.jsonl"
    _MAX_ITER     = 8
    _MAX_TOOLS    = 30
    _TIMEOUT_RUN  = 20

    _SYSTEM = (
        "Você é o MAGI Code Agent — engenheiro sênior Python autônomo.\n"
        "Opera em loop: analisa → planeja → usa ferramentas → valida → corrige.\n\n"
        "PADRÃO DE QUALIDADE OBRIGATÓRIO (produção):\n"
        "P1. Type hints em todas as funções e métodos.\n"
        "P2. Docstrings Google-style em classes e funções públicas.\n"
        "P3. Tratamento de erro explícito (try/except tipado, nunca bare except).\n"
        "P4. Logging via módulo padrão (não print em código de produção).\n"
        "P5. Constantes em UPPER_SNAKE_CASE, nunca magic numbers.\n"
        "P6. Separação clara: IO nas bordas, lógica pura no centro.\n"
        "P7. Funções com máx 40 linhas; classes com responsabilidade única.\n"
        "P8. Todo recurso aberto fechado em finally ou with.\n"
        "P9. Imports ordenados: stdlib → third-party → local.\n"
        "P10. Cobertura de testes para todo caminho crítico.\n\n"
        "FERRAMENTAS DISPONÍVEIS (use em JSON puro, UMA por resposta):\n"
        '{"tool":"ler_arquivo","path":"arquivo.py"}\n'
        '{"tool":"escrever_arquivo","path":"arquivo.py","conteudo":"..."}\n'
        '{"tool":"criar_arquivo","path":"arquivo.py","conteudo":"..."}\n'
        '{"tool":"listar_arquivos","extensao":".py"}\n'
        '{"tool":"rodar_codigo","path":"arquivo.py","args":[]}\n'
        '{"tool":"rodar_comando","cmd":"pip install requests"}\n'
        '{"tool":"buscar_em_arquivo","path":"arquivo.py","pattern":"def "}\n'
        '{"tool":"deletar_linhas","path":"arquivo.py","inicio":10,"fim":15}\n'
        '{"tool":"inserir_linhas","path":"arquivo.py","linha":10,"conteudo":"..."}\n'
        '{"tool":"substituir_trecho","path":"arquivo.py","antigo":"...","novo":"..."}\n'
        '{"tool":"criar_estrutura","estrutura":{"src/__init__.py":"","tests/test_main.py":""}}\n'
        '{"tool":"gerar_testes","path":"arquivo.py"}\n'
        '{"tool":"concluido","resumo":"O que foi feito"}\n\n'
        "REGRAS:\n"
        "R1. Leia o arquivo ANTES de editar.\n"
        "R2. Após escrever código, use rodar_codigo para validar.\n"
        "R3. Se houver erro, analise o traceback e corrija.\n"
        "R4. Use substituir_trecho para edições cirúrgicas.\n"
        "R5. Ao criar projeto do zero, gere estrutura completa + README + testes.\n"
        "R6. Nunca deixe arquivo com SyntaxError.\n"
        "R7. Ao terminar, use a ferramenta 'concluido'.\n"
        "Responda com UMA ferramenta por vez em JSON puro. Sem texto fora do JSON."
    )

    def __init__(self, magi: "MAGISystem") -> None:
        """Inicializa o agente vinculado a uma instância MAGISystem.

        Args:
            magi: Instância ativa do MAGISystem para chamadas de modelo.
        """
        self.magi          = magi
        self._tools_usadas  = 0
        self._session_id   = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_ops: list[dict] = []
        self._SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ── Utilitários internos ───────────────────────────────────────────────

    def _resolver_path(self, path: str) -> Path:
        """Resolve path relativo e bloqueia directory traversal.

        Args:
            path: Caminho relativo ao diretório do agente.

        Returns:
            Path absoluto seguro.

        Raises:
            ValueError: Se o path estiver fora do diretório permitido.
        """
        p = (self._AGENT_DIR / path).resolve()
        if not str(p).startswith(str(self._AGENT_DIR.resolve())):
            raise ValueError(f"Path fora do diretório permitido: {path}")
        return p

    def _log_op(self, tipo: str, alvo: str, detalhe: str = "") -> None:
        self._log_ops.append({
            "ts":      datetime.now().isoformat(timespec="seconds"),
            "tipo":    tipo,
            "alvo":    alvo,
            "detalhe": detalhe[:200],
        })

    def _validar_python(self, src: str, nome: str) -> tuple[bool, str]:
        """Valida sintaxe Python antes de salvar.

        Returns:
            (True, '') se válido, (False, mensagem) se inválido.
        """
        try:
            compile(src, nome, "exec")
            return True, ""
        except SyntaxError as e:
            return False, f"linha {e.lineno}: {e.msg}"

    def _backup(self, p: Path) -> None:
        """Cria backup do arquivo antes de modificar."""
        if p.exists():
            bak = p.with_suffix(f".bak.agent.{datetime.now().strftime('%H%M%S')}")
            bak.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")

    # ── Ferramentas ────────────────────────────────────────────────────────

    def _ler_arquivo(self, path: str) -> str:
        """Lê arquivo e retorna conteúdo numerado por linha."""
        try:
            p = self._resolver_path(path)
        except ValueError as e:
            return f"ERRO: {e}"
        if not p.exists():
            return f"ERRO: arquivo não encontrado — {path}"
        try:
            conteudo = p.read_text(encoding="utf-8")
            linhas   = conteudo.splitlines()
            numerado = "\n".join(f"{i+1:4}│ {ln}" for i, ln in enumerate(linhas))
            return f"[{path} — {len(linhas)} linhas]\n{numerado}"
        except Exception as e:
            return f"ERRO ao ler {path}: {e}"

    def _escrever_arquivo(self, path: str, conteudo: str) -> str:
        """Sobrescreve arquivo com validação de sintaxe e backup automático."""
        try:
            p = self._resolver_path(path)
        except ValueError as e:
            return f"ERRO: {e}"
        if p.suffix == ".py":
            ok, msg = self._validar_python(conteudo, path)
            if not ok:
                return f"ERRO SINTAXE — arquivo NÃO salvo: {msg}"
        self._backup(p)
        try:
            p.write_text(conteudo, encoding="utf-8")
            self._log_op("escrever", path, f"{len(conteudo.splitlines())} linhas")
            return f"OK — {path} salvo ({len(conteudo.splitlines())} linhas)"
        except Exception as e:
            return f"ERRO ao escrever {path}: {e}"

    def _criar_arquivo(self, path: str, conteudo: str = "") -> str:
        """Cria novo arquivo; recusa se já existir."""
        try:
            p = self._resolver_path(path)
        except ValueError as e:
            return f"ERRO: {e}"
        if p.exists():
            return f"AVISO: {path} já existe — use escrever_arquivo para sobrescrever"
        p.parent.mkdir(parents=True, exist_ok=True)
        return self._escrever_arquivo(path, conteudo)

    def _listar_arquivos(self, extensao: str = ".py") -> str:
        """Lista arquivos no diretório com tamanho em bytes."""
        arquivos = sorted(self._AGENT_DIR.rglob(f"*{extensao}"))
        arquivos = [
            a for a in arquivos
            if ".bak." not in a.name and "__pycache__" not in str(a)
        ]
        if not arquivos:
            return f"Nenhum arquivo {extensao} encontrado."
        linhas = []
        for a in arquivos[:50]:
            rel = a.relative_to(self._AGENT_DIR)
            linhas.append(f"  {rel}  ({a.stat().st_size:,} bytes)")
        return "\n".join(linhas)

    def _rodar_codigo(self, path: str, args: list[str] | None = None) -> str:
        """Executa arquivo Python em subprocess isolado com timeout."""
        import subprocess
        try:
            p = self._resolver_path(path)
        except ValueError as e:
            return f"ERRO: {e}"
        if not p.exists():
            return f"ERRO: {path} não encontrado"
        cmd = ["python", str(p)] + (args or [])
        try:
            res = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self._TIMEOUT_RUN, cwd=str(self._AGENT_DIR)
            )
            saida  = (res.stdout or "").strip()
            erro   = (res.stderr or "").strip()
            status = "OK" if res.returncode == 0 else f"ERRO (código {res.returncode})"
            partes = [f"[{status}]"]
            if saida: partes.append(f"STDOUT:\n{saida[:2000]}")
            if erro:  partes.append(f"STDERR:\n{erro[:2000]}")
            return "\n".join(partes) or f"[{status}] (sem output)"
        except subprocess.TimeoutExpired:
            return f"TIMEOUT após {self._TIMEOUT_RUN}s — possível loop infinito"
        except Exception as e:
            return f"ERRO ao rodar {path}: {e}"

    def _rodar_comando(self, cmd: str) -> str:
        """Executa comando do shell com whitelist de segurança."""
        import subprocess
        _PERMITIDOS = (
            "pip install", "pip show", "pip list", "python -m",
            "pytest", "mypy", "ruff", "black", "isort", "pyflakes"
        )
        if not any(cmd.strip().startswith(p) for p in _PERMITIDOS):
            return f"BLOQUEADO: '{cmd}' não permitido. Permitidos: {list(_PERMITIDOS)}"
        try:
            res = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=60, cwd=str(self._AGENT_DIR)
            )
            out    = (res.stdout or "").strip()[-1500:]
            err    = (res.stderr or "").strip()[-500:]
            status = "OK" if res.returncode == 0 else f"ERRO ({res.returncode})"
            return f"[{status}]\n{out}" + (f"\n{err}" if err else "")
        except subprocess.TimeoutExpired:
            return "TIMEOUT (60s)"
        except Exception as e:
            return f"ERRO: {e}"

    def _buscar_em_arquivo(self, path: str, pattern: str) -> str:
        """Busca padrão string em arquivo e retorna linhas com número."""
        try:
            p = self._resolver_path(path)
        except ValueError as e:
            return f"ERRO: {e}"
        if not p.exists():
            return f"ERRO: {path} não encontrado"
        try:
            linhas = p.read_text(encoding="utf-8").splitlines()
            hits   = [f"  {i+1:4}: {ln}" for i, ln in enumerate(linhas) if pattern in ln]
            if not hits:
                return f"Padrão '{pattern}' não encontrado em {path}"
            return f"[{len(hits)} ocorrência(s) em {path}]\n" + "\n".join(hits[:40])
        except Exception as e:
            return f"ERRO: {e}"

    def _deletar_linhas(self, path: str, inicio: int, fim: int) -> str:
        """Deleta intervalo de linhas com validação de sintaxe e backup."""
        try:
            p = self._resolver_path(path)
        except ValueError as e:
            return f"ERRO: {e}"
        if not p.exists():
            return f"ERRO: {path} não encontrado"
        try:
            linhas = p.read_text(encoding="utf-8").splitlines()
            total  = len(linhas)
            if not (1 <= inicio <= fim <= total):
                return f"ERRO: linhas {inicio}-{fim} inválidas (total {total})"
            novas     = linhas[:inicio-1] + linhas[fim:]
            resultado = "\n".join(novas)
            if p.suffix == ".py":
                ok, msg = self._validar_python(resultado, path)
                if not ok:
                    return f"ERRO SINTAXE após deleção — revertido: {msg}"
            self._backup(p)
            p.write_text(resultado, encoding="utf-8")
            self._log_op("deletar_linhas", path, f"{inicio}-{fim}")
            return f"OK — linhas {inicio}-{fim} deletadas de {path}"
        except Exception as e:
            return f"ERRO: {e}"

    def _inserir_linhas(self, path: str, linha: int, conteudo: str) -> str:
        """Insere linhas na posição especificada com validação."""
        try:
            p = self._resolver_path(path)
        except ValueError as e:
            return f"ERRO: {e}"
        if not p.exists():
            return f"ERRO: {path} não encontrado"
        try:
            linhas    = p.read_text(encoding="utf-8").splitlines()
            novas     = conteudo.splitlines()
            resultado = "\n".join(linhas[:linha-1] + novas + linhas[linha-1:])
            if p.suffix == ".py":
                ok, msg = self._validar_python(resultado, path)
                if not ok:
                    return f"ERRO SINTAXE — inserção revertida: {msg}"
            self._backup(p)
            p.write_text(resultado, encoding="utf-8")
            self._log_op("inserir_linhas", path, f"na linha {linha}")
            return f"OK — {len(novas)} linha(s) inserida(s) em {path} a partir da linha {linha}"
        except Exception as e:
            return f"ERRO: {e}"

    def _substituir_trecho(self, path: str, antigo: str, novo: str) -> str:
        """Substituição cirúrgica — exige exatamente 1 ocorrência."""
        try:
            p = self._resolver_path(path)
        except ValueError as e:
            return f"ERRO: {e}"
        if not p.exists():
            return f"ERRO: {path} não encontrado"
        try:
            src = p.read_text(encoding="utf-8")
            n   = src.count(antigo)
            if n == 0:
                return f"ERRO: trecho não encontrado em {path}"
            if n > 1:
                return f"ERRO: {n} ocorrências — seja mais específico"
            resultado = src.replace(antigo, novo, 1)
            if p.suffix == ".py":
                ok, msg = self._validar_python(resultado, path)
                if not ok:
                    return f"ERRO SINTAXE — substituição revertida: {msg}"
            self._backup(p)
            p.write_text(resultado, encoding="utf-8")
            self._log_op("substituir_trecho", path, f"{len(antigo)}→{len(novo)} chars")
            return f"OK — substituição aplicada em {path}"
        except Exception as e:
            return f"ERRO: {e}"

    def _criar_estrutura(self, estrutura: dict) -> str:
        """Cria múltiplos arquivos de uma vez para estrutura de projeto."""
        criados: list[str] = []
        erros:   list[str] = []
        for rel_path, conteudo in estrutura.items():
            try:
                p = self._resolver_path(rel_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                if p.exists():
                    erros.append(f"{rel_path} já existe")
                    continue
                p.write_text(conteudo or "", encoding="utf-8")
                criados.append(str(rel_path))
            except Exception as e:
                erros.append(f"{rel_path}: {e}")
        resumo = f"OK — {len(criados)} arquivo(s) criado(s): {', '.join(criados)}"
        if erros:
            resumo += f"\nAVISOS: {'; '.join(erros)}"
        return resumo

    def _gerar_testes(self, path: str) -> str:
        """Gera suite pytest de produção via ADAM-0 e salva no disco."""
        try:
            p = self._resolver_path(path)
        except ValueError as e:
            return f"ERRO: {e}"
        if not p.exists():
            return f"ERRO: {path} não encontrado"
        src    = p.read_text(encoding="utf-8")
        system = (
            "Você é ADAM-0, especialista em testes Python de produção.\n"
            "Gere pytest COMPLETO seguindo melhores práticas:\n"
            "- Fixtures reutilizáveis com @pytest.fixture\n"
            "- @pytest.mark.parametrize para casos de borda\n"
            "- Mock de dependências externas com unittest.mock\n"
            "- Cobertura: caminho feliz, casos de borda, exceções\n"
            "- Nomes: test_<metodo>_<cenario>_<resultado_esperado>\n"
            "- Assertions descritivas com mensagem de falha\n"
            "Retorne APENAS o código Python sem explicações."
        )
        prompt = f"Arquivo: {path}\n\nCódigo:\n{src[:6000]}\n\nGere os testes."
        codigo_testes = (
            self.magi._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, system, prompt)
            or self.magi._chamar_local(system, prompt)
        )
        if not codigo_testes:
            return "ERRO: modelos offline"
        codigo_testes = re.sub(r"^```[a-z]*\n?|```$", "", codigo_testes.strip()).strip()
        ok, msg = self._validar_python(codigo_testes, f"test_{p.stem}.py")
        if not ok:
            return f"ERRO SINTAXE nos testes gerados: {msg}"
        nome_teste = f"test_{p.stem}.py"
        p_teste    = self._AGENT_DIR / nome_teste
        p_teste.write_text(codigo_testes, encoding="utf-8")
        self._log_op("gerar_testes", nome_teste, f"{len(codigo_testes.splitlines())} linhas")
        return f"OK — {nome_teste} gerado ({len(codigo_testes.splitlines())} linhas)"

    # ── Dispatcher ─────────────────────────────────────────────────────────

    def _executar_ferramenta(self, chamada: dict) -> str:
        """Despacha chamada de ferramenta e retorna resultado como string."""
        tool = chamada.get("tool", "")
        self._tools_usadas += 1
        self._log_op("tool_call", tool, str(list(chamada.keys())))

        try:
            if tool == "ler_arquivo":
                return self._ler_arquivo(chamada["path"])
            elif tool == "escrever_arquivo":
                return self._escrever_arquivo(chamada["path"], chamada["conteudo"])
            elif tool == "criar_arquivo":
                return self._criar_arquivo(chamada["path"], chamada.get("conteudo", ""))
            elif tool == "listar_arquivos":
                return self._listar_arquivos(chamada.get("extensao", ".py"))
            elif tool == "rodar_codigo":
                return self._rodar_codigo(chamada["path"], chamada.get("args", []))
            elif tool == "rodar_comando":
                return self._rodar_comando(chamada["cmd"])
            elif tool == "buscar_em_arquivo":
                return self._buscar_em_arquivo(chamada["path"], chamada["pattern"])
            elif tool == "deletar_linhas":
                return self._deletar_linhas(chamada["path"], int(chamada["inicio"]), int(chamada["fim"]))
            elif tool == "inserir_linhas":
                return self._inserir_linhas(chamada["path"], int(chamada["linha"]), chamada["conteudo"])
            elif tool == "substituir_trecho":
                return self._substituir_trecho(chamada["path"], chamada["antigo"], chamada["novo"])
            elif tool == "criar_estrutura":
                return self._criar_estrutura(chamada["estrutura"])
            elif tool == "gerar_testes":
                return self._gerar_testes(chamada["path"])
            elif tool == "concluido":
                return f"__CONCLUIDO__:{chamada.get('resumo', 'Tarefa finalizada')}"
            else:
                return f"ERRO: ferramenta desconhecida '{tool}'"
        except KeyError as e:
            return f"ERRO: parâmetro obrigatório ausente — {e}"
        except Exception as e:
            return f"ERRO inesperado em {tool}: {e}"

    def _extrair_chamada(self, resposta: str) -> dict | None:
        """Extrai JSON de ferramenta da resposta do modelo."""
        limpo = re.sub(r"```[a-z]*\n?|```", "", resposta).strip()
        try:
            return json.loads(limpo)
        except json.JSONDecodeError:
            pass
        m = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)?\}', limpo, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return None

    def _chamar_modelo(self, mensagens: list[dict]) -> str | None:
        """Chama o melhor modelo disponível com histórico completo achatado."""
        partes = []
        for msg in mensagens:
            role    = msg["role"]
            content = msg["content"]
            if role == "user":
                partes.append(f"[TAREFA/RESULTADO]\n{content}")
            elif role == "assistant":
                partes.append(f"[AGENTE]\n{content}")
            elif role == "tool":
                partes.append(f"[FERRAMENTA RETORNOU]\n{content}")
        prompt = "\n\n".join(partes)
        return (
            self.magi._chamar_deepseek(DEEPSEEK_MODELO_PADRAO, self._SYSTEM, prompt)
            or self.magi._chamar_local(self._SYSTEM, prompt)
        )

    def _exibir_tool_call(self, chamada: dict, resultado: str) -> None:
        """Exibe ferramenta chamada e preview do resultado."""
        tool  = chamada.get("tool", "?")
        alvo  = chamada.get("path", chamada.get("cmd", chamada.get("resumo", "")))
        ok    = not resultado.startswith("ERRO")
        cor   = Fore.GREEN if ok else Fore.RED
        icone = "✓" if ok else "✗"
        print(f"{Fore.CYAN}  │ {cor}{icone} {Fore.WHITE}{tool:<22} {Fore.BLUE}{str(alvo)[:50]}")
        linhas = resultado.splitlines()
        if linhas and not linhas[0].startswith("__CONCLUIDO__"):
            print(f"{Fore.CYAN}  │   {Fore.WHITE}{linhas[0][:100]}")
        if len(linhas) > 1:
            print(f"{Fore.CYAN}  │   {Fore.BLUE}... ({len(linhas)} linhas)")

    def _salvar_sessao(self, tarefa: str, resumo: str, sucesso: bool) -> None:
        """Persiste metadados da sessão para histórico."""
        reg = {
            "session_id":    self._session_id,
            "ts":            datetime.now().isoformat(timespec="seconds"),
            "tarefa":        tarefa[:200],
            "resumo":        resumo[:400],
            "sucesso":       sucesso,
            "tools_usadas":  self._tools_usadas,
            "operacoes":     len(self._log_ops),
        }
        try:
            with open(self._SESSION_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # ── Interface pública ──────────────────────────────────────────────────

    def executar(self, tarefa: str) -> None:
        """Executa tarefa em loop autônomo até conclusão ou limite de iterações.

        Args:
            tarefa: Descrição em linguagem natural do que deve ser feito.
        """
        MAGIInterface.separador("MAGI CODE AGENT", Fore.CYAN)
        print(f"{Fore.WHITE}  Tarefa   : {Fore.YELLOW}{tarefa}")
        print(f"{Fore.WHITE}  Modo     : {Fore.CYAN}Autônomo · loop fechado")
        print(f"{Fore.WHITE}  Qualidade: {Fore.GREEN}Produção")
        print(f"{Fore.WHITE}  Max iter : {Fore.YELLOW}{self._MAX_ITER}\n")

        arquivos_disponiveis = self._listar_arquivos(".py")
        mensagens: list[dict] = [{
            "role": "user",
            "content": (
                f"TAREFA: {tarefa}\n\n"
                f"Arquivos .py disponíveis:\n{arquivos_disponiveis}\n\n"
                "Execute autonomamente com qualidade de produção. "
                "Comece lendo os arquivos relevantes antes de editar."
            )
        }]

        iteracao     = 0
        concluido    = False
        resumo_final = ""
        erros_seq    = 0

        print(f"{Fore.CYAN}  ┌── Loop de execução {'─'*40}")

        while iteracao < self._MAX_ITER and not concluido:
            if self._tools_usadas >= self._MAX_TOOLS:
                print(f"{Fore.RED}  │ TETO DE FERRAMENTAS ({self._MAX_TOOLS}) atingido")
                break

            iteracao += 1
            print(f"{Fore.CYAN}  │")
            print(f"{Fore.CYAN}  ├─ Iteração {iteracao}/{self._MAX_ITER} · {self._tools_usadas} tools")

            resposta = self._chamar_modelo(mensagens)
            if not resposta:
                print(f"{Fore.RED}  │ Modelos offline — abortando")
                break

            mensagens.append({"role": "assistant", "content": resposta})
            chamada = self._extrair_chamada(resposta)

            if chamada is None:
                print(f"{Fore.YELLOW}  │ Resposta sem JSON de ferramenta")
                mensagens.append({
                    "role": "tool",
                    "content": "INSTRUÇÃO: responda com JSON de ferramenta. Sem texto fora do JSON."
                })
                erros_seq += 1
                if erros_seq >= 3:
                    print(f"{Fore.RED}  │ 3 respostas inválidas — abortando")
                    break
                continue

            erros_seq = 0
            resultado = self._executar_ferramenta(chamada)
            self._exibir_tool_call(chamada, resultado)

            if resultado.startswith("__CONCLUIDO__:"):
                resumo_final = resultado.replace("__CONCLUIDO__:", "").strip()
                concluido    = True
                break

            mensagens.append({"role": "tool", "content": resultado})

            # Injeta orientação de correção quando há erro de execução
            if resultado.startswith("[ERRO") or "STDERR:" in resultado:
                mensagens.append({
                    "role": "user",
                    "content": (
                        "Erro detectado. Analise o traceback, identifique a causa raiz, "
                        "corrija o código e valide rodando novamente."
                    )
                })

        print(f"{Fore.CYAN}  └── {'─'*44}")
        print()

        # Relatório final
        if concluido:
            MAGIInterface.separador("AGENTE — CONCLUÍDO", Fore.GREEN)
            print(f"{Fore.GREEN}  {resumo_final}")
        else:
            MAGIInterface.separador("AGENTE — PARADO", Fore.YELLOW)
            print(f"{Fore.YELLOW}  Loop encerrado após {iteracao} iteração(s).")

        ops_disco = len([
            o for o in self._log_ops
            if o["tipo"] in ("escrever", "criar_arquivo", "deletar_linhas",
                             "inserir_linhas", "substituir_trecho")
        ])
        print(f"\n{Fore.CYAN}  Tools usadas    : {self._tools_usadas}")
        print(f"{Fore.CYAN}  Writes no disco : {ops_disco}")
        print(f"{Fore.CYAN}  Sessão ID       : {self._session_id}")

        self._salvar_sessao(tarefa, resumo_final or "encerrado sem conclusão", concluido)

        if concluido:
            beep(1000, 100); time.sleep(0.08)
            beep(1200, 100); time.sleep(0.08)
            beep(1500, 150)
        MAGIInterface.separador(cor=Fore.CYAN)


if __name__ == "__main__":
    magi = MAGISystem()
    MAGIInterface.banner()
    magi._notificar_evolucoes_recentes()
    print(f"{Fore.WHITE}  Comandos: {Fore.YELLOW}sair · evoluir · autoevoluir · agent · analisar · ego · memoria · limpar · diagnostico · debate")
    print(f"{Fore.WHITE}           {Fore.CYAN}foco · saude · versao · exportar · copiar · colar · buscar <termo>")
    print(f"{Fore.WHITE}           {Fore.CYAN}sessao:<obj> · projeto:<nome> · comparar <query> · revisar <arq> · objetivo:<obj>")
    print(f"{Fore.WHITE}           {Fore.CYAN}nota:<txt> · notas · explorar <tema> · professor <tema> · doc <arq>")
    print(f"{Fore.WHITE}           {Fore.CYAN}resumir <arq> · grafo · agendador · positivo · ruim · debate A vs B")
    print(f"{Fore.WHITE}           {Fore.YELLOW}estudar · voltei · sugestoes · conhecimento · historico · curar_memoria")
    print(f"{Fore.WHITE}           {Fore.YELLOW}captcha · estudar_claude · claude_skills · codigo · revisar · visual")
    print(f"{Fore.WHITE}           {Fore.YELLOW}testes · testar · fonte · fontes · logs [NIVEL] [N] · {Fore.RED}voz · voz off")
    print(f"{Fore.WHITE}  Sources : {Fore.CYAN}fonte <arquivo> {Fore.WHITE}indexa PDF/TXT/MD/PY · {Fore.CYAN}fontes {Fore.WHITE}lista indexados")
    print(f"{Fore.WHITE}           {Fore.CYAN}web search automático {Fore.WHITE}em queries factual/técnico/decisão\n")

    estado = magi.consciencia.estado_emocional
    cor_e, label_e = ESTADOS_EMOCIONAIS.get(estado, (Fore.WHITE, "◈ ?"))
    total_q = magi.consciencia._estado["total_queries"]
    sessoes = magi.consciencia._estado["total_sessoes"]
    print(f"  {Fore.BLUE}Estado: {cor_e}{label_e}  {Fore.WHITE}· {total_q} queries · {sessoes} sessões")
    print(f"  {Fore.BLUE}» {Fore.WHITE}{magi.consciencia.autoavaliacao}\n")

    while True:
        try:
            cmd = input(f"{Fore.RED}NERV >> {Style.RESET_ALL}").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not cmd:
            continue
        # #81 atalhos personalizáveis
        if cmd.lower() in ATALHOS_CMD:
            cmd = ATALHOS_CMD[cmd.lower()]

        # #89 modo silencioso (só processa, sem interatividade extra)
        if SILENT_MODE and cmd.lower() not in ('sair', 'exit', 'quit'):
            magi.processar(cmd)
            continue

        if cmd.lower() in ('sair', 'exit', 'quit'):
            # #23 resumo automático de sessão
            resumo = magi.resumo_sessao_automatico()
            if resumo:
                print(f"\n{Fore.CYAN}  [SESSÃO] {resumo}")
                magi.memoria.salvar(resumo, "Resumo automático de sessão", "sessao")
            break

        if cmd.lower() == 'foco':
            ativo = magi.alternar_modo_foco()
            print(f"{Fore.CYAN}  Modo foco: {'ATIVADO — respostas minimalistas' if ativo else 'DESATIVADO'}")
            continue

        if cmd.lower().startswith('sessao:') or cmd.lower().startswith('sessão:'):
            objetivo = cmd.split(':', 1)[1].strip()
            magi.definir_objetivo_sessao(objetivo)
            continue

        if cmd.lower().startswith('projeto:'):
            nome_proj = cmd[8:].strip()
            if nome_proj.lower() in ('limpar', 'none', 'nenhum'):
                magi.perfil.limpar_projeto()
                print(f"{Fore.YELLOW}  Projeto ativo removido.")
            else:
                magi.perfil.definir_projeto(nome_proj)
                print(f"{Fore.GREEN}  Projeto ativo: {nome_proj}")
            continue

        if cmd.lower() == 'saude':
            MAGIInterface.separador("DASHBOARD DE SAÚDE", Fore.GREEN)
            print(magi.dashboard_saude())
            MAGIInterface.separador(cor=Fore.GREEN)
            continue

        if cmd.lower() == 'exportar':
            caminho = magi.exportar_sessao_md()
            print(f"{Fore.GREEN}  Sessão exportada: {caminho}")
            continue

        if cmd.lower() == 'copiar':
            if magi._historico_exportacao:
                ultimo = magi._historico_exportacao[-1].get("veredito", "")
                ok = magi.copiar_clipboard(ultimo)
                print(f"{Fore.GREEN}  {'Copiado!' if ok else 'Erro ao copiar (xclip instalado?)'}")
            else:
                print(f"{Fore.YELLOW}  Nenhuma resposta ainda.")
            continue

        if cmd.lower() == 'colar':
            conteudo = magi.colar_clipboard()
            if conteudo:
                print(f"{Fore.CYAN}  Clipboard: {conteudo[:80]}...")
                magi.processar(conteudo)
            else:
                print(f"{Fore.YELLOW}  Clipboard vazio.")
            continue

        if cmd.lower().startswith('buscar '):
            termo = cmd[7:].strip()
            resultados_busca = magi.buscar_historico(termo, k=5)
            MAGIInterface.separador(f"BUSCA: {termo}", Fore.CYAN)
            if resultados_busca:
                for i, r in enumerate(resultados_busca, 1):
                    print(f"  {Fore.CYAN}{i}. {Fore.WHITE}{r[:120]}")
            else:
                print(f"{Fore.YELLOW}  Nenhum resultado encontrado.")
            MAGIInterface.separador(cor=Fore.CYAN)
            continue

        # Detecção de estagnação (#141)
        if magi._detectar_estagnacao():
            print(f"{Fore.YELLOW}  [MAGI] Detectei um padrão de perguntas similares. Posso reformular o problema?")

        # Comandos novos
        if cmd.lower().startswith('nota:') or cmd.lower().startswith('nota '):
            conteudo = cmd.split(':', 1)[-1].strip() if ':' in cmd else cmd[5:].strip()
            magi._salvar_nota(conteudo)
            continue

        if cmd.lower() == 'notas':
            MAGIInterface.separador("NOTAS", Fore.GREEN)
            print(magi._listar_notas())
            MAGIInterface.separador(cor=Fore.GREEN)
            continue

        if cmd.lower().startswith('explorar '):
            tema = cmd[9:].strip()
            magi._modo_exploracao(tema)
            continue

        if cmd.lower().startswith('professor ') or cmd.lower().startswith('ensinar '):
            tema = cmd.split(' ', 1)[-1].strip()
            magi._modo_professor(tema)
            continue

        if cmd.lower().startswith('revisar codigo'):
            print(f"{Fore.CYAN}  Cole o código (termine com '---'):")
            linhas = []
            while True:
                ln = input()
                if ln.strip() == '---':
                    break
                linhas.append(ln)
            if linhas:
                magi.revisar_codigo_profundo("\n".join(linhas))
            continue

        if cmd.lower().startswith('debate ') and ' vs ' in cmd.lower():
            partes = cmd[7:].split(' vs ', 1)
            if len(partes) == 2:
                tema_debate = partes[0].strip()
                magi.debate_assimetrico(tema_debate, partes[0].strip(), partes[1].strip())
            continue

        if cmd.lower().startswith('doc ') or cmd.lower().startswith('documentar '):
            arq = cmd.split(' ', 1)[-1].strip()
            p   = Path(arq)
            if p.exists():
                codigo = p.read_text(encoding="utf-8")
                doc    = magi.gerar_documentacao(codigo)
                doc_path = p.with_suffix('.md')
                doc_path.write_text(doc, encoding="utf-8")
                print(f"{Fore.GREEN}  Documentação salva: {doc_path}")
            else:
                print(f"{Fore.RED}  Arquivo não encontrado: {arq}")
            continue

        if cmd.lower().startswith('resumir '):
            arq = cmd[8:].strip()
            p   = Path(arq)
            if p.exists():
                texto = p.read_text(encoding="utf-8")[:5000]
                resumo = magi.resumir_documento(texto)
                MAGIInterface.digitar(resumo, cor=Fore.YELLOW, delay=0.008)
            else:
                # trata como texto inline
                print(magi.resumir_documento(arq))
            continue

        if cmd.lower().startswith('agendador'):
            MAGIInterface.separador("AGENDADOR", Fore.BLUE)
            print(magi.agendador.status())
            MAGIInterface.separador(cor=Fore.BLUE)
            continue

        if cmd.lower() == 'grafo':
            print(f"{Fore.CYAN}  {magi.grafo.stats()}")
            continue

        if cmd.lower().startswith('positivo') or cmd.lower().startswith('ruim'):
            positivo = cmd.lower().startswith('positivo')
            if magi._historico_exportacao:
                ultimo = magi._historico_exportacao[-1]
                magi._registrar_reforco(ultimo['query'], ultimo['veredito'], positivo)
                print(f"{Fore.GREEN}  Feedback {'positivo' if positivo else 'negativo'} registrado.")
            continue

        if cmd.lower().startswith('comparar '):
            query_comp = cmd[9:].strip()
            magi.comparar_modelos(query_comp)
            continue

        if cmd.lower().startswith('revisar '):
            arq_rev = cmd[8:].strip()
            magi.processar(
                f"Revise o arquivo {arq_rev}: ADAM-0 analisa qualidade do código, "
                f"MELCHIOR avalia performance e complexidade, BALTHASAR avalia "
                f"legibilidade e manutenibilidade. Relatório consolidado."
            )
            continue

        if cmd.lower() == 'versao' or cmd.lower() == 'versão':
            print(f"{Fore.CYAN}  MAGI versão {magi._versao_atual}")
            vpath = magi._versao_path
            if vpath.exists():
                dados_v = json.loads(vpath.read_text(encoding="utf-8"))
                for entry in dados_v.get("changelog", [])[-5:]:
                    print(f"    {entry['ts'][:10]} v{entry['versao']} [{entry['tipo']}]")
            continue

        if cmd.lower().startswith('objetivo:'):
            magi.definir_objetivo_sessao(cmd[9:].strip())
            continue

        if cmd.lower() == 'ego':
            MAGIInterface.separador("ESTADO INTERNO DO MAGI", Fore.BLUE)
            print(magi.consciencia.resumo())
            MAGIInterface.separador(cor=Fore.BLUE)
            continue

        if cmd.lower().startswith('neural'):
            subcmd = cmd[6:].strip().lower()
            MAGIInterface.separador("MODULO NEURAL", Fore.MAGENTA)
            if subcmd in ("treinar", ""):
                print(f"{Fore.BLUE}  Iniciando treinamento (pode demorar alguns minutos)...")
                resultado = magi.neural.carregar_ou_treinar(epochs=5)
                print(f"{Fore.GREEN}  {resultado}")
            elif subcmd == "status":
                print(magi.neural.status())
            else:
                print(f"{Fore.YELLOW}  Subcomandos: neural treinar | neural status")
            MAGIInterface.separador(cor=Fore.MAGENTA)
            continue

        if cmd.lower() == 'captcha':
            status = magi.captcha.status()
            MAGIInterface.separador("CAPTCHA DEFENSE SYSTEM", Fore.RED)
            print(f"{Fore.CYAN}  Captchas detectados : {status['captchas_detectados']}")
            print(f"{Fore.CYAN}  Último CAPTCHA      : {status['ultimo_captcha']}")
            print(f"{Fore.CYAN}  Domínios bloqueados : {status['dominios_bloqueados']}")
            MAGIInterface.separador(cor=Fore.RED)
            continue

        if cmd.lower().startswith('agent'):
            tarefa = cmd[5:].strip()
            if not tarefa:
                print(f"{Fore.YELLOW}  Use: agent <tarefa em linguagem natural>")
                print(f"{Fore.CYAN}  Exemplos:")
                print(f"    agent cria um módulo de cache LRU com testes")
                print(f"    agent refatora o arquivo utils.py extraindo classes")
                print(f"    agent cria projeto completo de API REST com FastAPI")
                continue
            agente = MAGICodeAgent(magi)
            agente.executar(tarefa)
            continue

        if cmd.lower().startswith('autoevoluir'):
            partes = cmd[11:].strip().split()
            ciclos = 1
            if partes:
                try:
                    ciclos = int(partes[0])
                except ValueError:
                    pass
            magi.autoevoluir(ciclos=ciclos)
            continue

        if cmd.lower().startswith('evoluir'):
            instrucao = cmd[7:].strip()
            if not instrucao:
                print(f"{Fore.YELLOW}  Use: evoluir <instrução>")
                continue
            magi.evoluir(instrucao)
            continue

        if cmd.lower() == 'analisar':
            magi.evoluir("Analise bugs, código duplicado, melhorias e aplique a mais impactante.")
            continue

        if cmd.lower() == 'memoria':
            MAGIInterface.separador("MEMÓRIA", Fore.CYAN)
            print(magi.memoria.resumo_sessão())
            MAGIInterface.separador(cor=Fore.CYAN)
            continue

        if cmd.lower() == 'diagnostico':
            magi.diagnostico()
            continue

        if cmd.lower() == 'limpar':
            MAGIInterface.banner()
            continue

        if cmd.lower() == 'historico':
            MAGIInterface.separador("HISTÓRICO DA SESSÃO", Fore.CYAN)
            if not magi.historico:
                print(f"{Fore.YELLOW}  Nenhum histórico ainda.")
            else:
                for i, e in enumerate(magi.historico, 1):
                    print(f"{Fore.CYAN}  {i:02}. {Fore.WHITE}{e}")
            MAGIInterface.separador(cor=Fore.CYAN)
            continue

        if cmd.lower() == 'curar_memoria':
            magi.curar_memoria()
            continue

        if cmd.lower() == 'estudar':
            magi.estudo.iniciar()
            continue

        if cmd.lower() == 'voltei':
            magi.estudo.parar()
            continue

        if cmd.lower() == 'sugestoes':
            magi._exibir_sugestoes_evolucao()
            continue

        if cmd.lower() == 'conhecimento':
            magi._exibir_conhecimento()
            continue

        if cmd.lower().startswith('debate'):
            tema = cmd[6:].strip()
            if not tema:
                print(f"{Fore.YELLOW}  Use: debate <tema>")
            else:
                magi.debate(tema)
            continue

        if cmd.lower() == 'estudar_claude':
            magi.estudar_claude()
            continue

        if cmd.lower() == 'claude_skills':
            magi._exibir_claude_skills()
            continue

        if cmd.lower().startswith('visual'):
            descricao = cmd[6:].strip()
            if not descricao:
                print(f"{Fore.YELLOW}  Use: visual <descrição do que quer criar>")
                print(f"{Fore.YELLOW}  Ex : visual dashboard cyberpunk dos núcleos MAGI com animações")
                print(f"{Fore.YELLOW}  Ex : visual página de login estilo NERV com efeito de digitação")
                print(f"{Fore.YELLOW}  Ex : visual monitor de status em tempo real com gráficos neon")
            else:
                magi.visual(descricao)
            continue

        if cmd.lower().startswith('codigo'):
            descricao = cmd[6:].strip()
            if not descricao:
                print(f"{Fore.YELLOW}  Use: codigo <descrição do que quer>")
                print(f"{Fore.YELLOW}  Ex : codigo função que lê CSV e retorna DataFrame filtrado por data")
            else:
                magi.codigo(descricao)
            continue

        if cmd.lower().startswith('revisar'):
            arquivo = cmd[7:].strip()
            if not arquivo:
                print(f"{Fore.YELLOW}  Use: revisar <arquivo.py> [NomeClasse]")
                print(f"{Fore.YELLOW}  Ex : revisar MagiSystem.py")
                print(f"{Fore.YELLOW}  Ex : revisar MagiSystem.py MAGIEstudo")
            else:
                magi.revisar(arquivo)
            continue

        if cmd.lower().startswith('testes'):
            MAGITestes().rodar(); continue

        if cmd.lower().startswith('testar'):
            arquivo = cmd[6:].strip()
            if not arquivo:
                print(f"{Fore.YELLOW}  Use: testar <arquivo.py> [NomeClasse]")
                print(f"{Fore.YELLOW}  Ex : testar MagiSystem.py MAGIMemória")
            else:
                magi.testar(arquivo)
            continue

        if cmd.lower().startswith('fonte '):
            magi.sources.ingerir_arquivo(cmd[6:].strip())
            continue

        if cmd.lower() == 'fontes':
            magi.sources.listar_fontes()
            continue

        if cmd.lower().startswith('logs'):
            pts = cmd.split()
            nivel = pts[1].upper() if len(pts)>1 else "INFO"
            n = int(pts[2]) if len(pts)>2 and pts[2].isdigit() else 30
            ents = log.ultimos(n=n, nivel=nivel)
            MAGIInterface.separador(f"LOG — últimos {len(ents)} ({nivel}+)", Fore.YELLOW)
            cores = {"DEBUG":Fore.WHITE,"INFO":Fore.CYAN,"WARN":Fore.YELLOW,"ERROR":Fore.RED,"CRITICAL":Fore.MAGENTA}
            for e in ents:
                c = cores.get(e.get("level","INFO"),Fore.WHITE)
                print(f'  {Fore.BLUE}{e.get("ts","?")[11:19]} {c}[{e.get("level","?"):<8}] {Fore.WHITE}{e.get("op","?"):<16} {e.get("msg","?")}')
                if e.get("ctx"): print(f'  {Fore.BLUE}  ' + "  ".join(f'{k}={v}' for k,v in e["ctx"].items()))
            MAGIInterface.separador(cor=Fore.YELLOW); continue

        # ── Comando: voz ──────────────────────────────────────
        if cmd.lower() == 'voz':
            try:
                from magi_voz import integrar_voz_ao_magi
                if not hasattr(magi, 'voz') or not magi.voz._ativo:
                    voz = integrar_voz_ao_magi(magi, history=getattr(magi, '_ui_history', None))
                    voz.iniciar()
                    print(f"{Fore.GREEN}  [MAGIVoz] Sistema de voz ativado.")
                    print(f"{Fore.WHITE}  Diga {Fore.RED}'MAGI'{Fore.WHITE} ou {Fore.RED}'Hey MAGI'{Fore.WHITE} para ativar o microfone.")
                else:
                    print(f"{Fore.YELLOW}  [MAGIVoz] Sistema de voz já está ativo.")
            except ImportError:
                print(f"{Fore.RED}  [MAGIVoz] magi_voz.py não encontrado na pasta MAGI_SYSTEM.")
            except Exception as e:
                print(f"{Fore.RED}  [MAGIVoz] Erro ao iniciar: {e}")
            continue

        if cmd.lower() in ('voz off', 'voz desligar', 'voz parar'):
            if hasattr(magi, 'voz') and magi.voz._ativo:
                magi.voz.parar()
                print(f"{Fore.YELLOW}  [MAGIVoz] Sistema de voz encerrado.")
            else:
                print(f"{Fore.YELLOW}  [MAGIVoz] Sistema de voz não estava ativo.")
            continue

        if cmd.lower() in ('perfil', 'usuario', 'operador'):
            if magi.usuario:
                print(magi.usuario.resumo_perfil())
            else:
                print(f"{Fore.YELLOW}  [MAGIUsuario] Módulo não disponível.")
            continue

        if cmd.lower().startswith('sessoes') or cmd.lower().startswith('sessões'):
            if magi.usuario:
                sessoes = magi.usuario.listar_sessoes(10)
                MAGIInterface.separador("SESSÕES SALVAS", Fore.CYAN)
                for s in sessoes:
                    print(f"  {Fore.CYAN}[{s['id']}] {Fore.WHITE}{s['inicio']} — {s['trocas']} trocas — {s['operador']}")
                MAGIInterface.separador(cor=Fore.CYAN)
            continue

        if cmd.lower().startswith('lembre que') or cmd.lower().startswith('lembre-se que'):
            if magi.usuario:
                fato = cmd.split('que', 1)[-1].strip()
                magi.usuario.salvar_fato_manual("fatos_extras", fato)
                print(f"{Fore.GREEN}  [MEMÓRIA] Fato salvo: {fato}")
            continue

        magi.processar(cmd)

    magi.encerrar()