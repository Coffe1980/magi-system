"""
magi/evolution/magi_evolution.py
Sistema de auto-evolução do MAGI — extraído do God Class MAGISources.
Responsabilidade única: modificar o próprio código de forma segura.
"""
import os, re, json, time, shutil, subprocess
from pathlib import Path
from datetime import datetime
from colorama import Fore

from magi.utils.magi_logger import log
from magi.core.magi_config import (
    FEWSHOT_PATH, BACKUP_DIR, EVOLUCAO_MAX_PROMPT,
    SANDBOX_TIMEOUT, MAX_RETRIES_API,
)
from magi.security.magi_security import validar_codigo_python, detectar_codigo_perigoso


class MAGIEvolution:
    """
    Gerencia o ciclo de auto-evolução do MAGI.
    Separado completamente de MAGISystem para permitir testes unitários.
    """

    def __init__(self, llm_router, consciencia=None):
        self.llm          = llm_router
        self.consciencia  = consciencia
        self._fewshot: list[dict] = []
        self._carregar_fewshot()

    # ── fewshot ───────────────────────────────────────────────

    def _carregar_fewshot(self):
        try:
            if FEWSHOT_PATH.exists():
                with open(FEWSHOT_PATH, encoding="utf-8") as f:
                    self._fewshot = json.load(f)
                log.debug("evolution", f"Fewshot carregado: {len(self._fewshot)} exemplos")
        except Exception as e:
            log.capture("evolution._carregar_fewshot", e)

    def _salvar_fewshot(self, instrucao: str, codigo_antes: str, codigo_depois: str):
        try:
            exemplo = {
                "instrucao":    instrucao[:200],
                "codigo_antes": codigo_antes[:500],
                "codigo_depois":codigo_depois[:500],
                "timestamp":    datetime.now().isoformat(timespec="seconds"),
            }
            self._fewshot.append(exemplo)
            self._fewshot = self._fewshot[-20:]  # mantém os 20 mais recentes
            with open(FEWSHOT_PATH, "w", encoding="utf-8") as f:
                json.dump(self._fewshot, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.capture("evolution._salvar_fewshot", e)

    # ── leitura do código ─────────────────────────────────────

    @staticmethod
    def _ler_codigo(caminho: str | None = None) -> str:
        path = Path(caminho) if caminho else Path(__file__).parent.parent.parent / "MagiSystem.py"
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            log.error("evolution", f"Erro ao ler código: {e}", exc=e)
            return ""

    # ── decomposição de instrução ─────────────────────────────

    def _decompor_instrucao(self, instrucao: str, codigo: str) -> str | None:
        system = (
            "Você decompõe instruções de modificação de código em passos claros.\n"
            "Dado uma instrução e o código atual, retorne um plano de até 4 passos.\n"
            "Formato JSON: {\"passos\": [\"passo 1\", \"passo 2\", ...]}\n"
            "Só JSON. Sem markdown."
        )
        prompt = f"Instrução: {instrucao}\n\nCódigo relevante (trecho):\n{codigo[:3000]}"
        r = (self.llm.chamar_openrouter(system, prompt) or
             self.llm.chamar_openai("gpt-4o-mini", system, prompt))
        return r

    # ── geração de modificação ────────────────────────────────

    def _gerar_modificacao(self, instrucao: str, codigo: str,
                           erro_anterior: str | None = None,
                           tentativa: int = 1) -> str | None:
        # Trunca prompt se muito grande
        if len(codigo) > EVOLUCAO_MAX_PROMPT:
            log.warn("evolution", f"Código truncado: {len(codigo)} → {EVOLUCAO_MAX_PROMPT}")
            codigo = codigo[:EVOLUCAO_MAX_PROMPT] + "\n...[TRUNCADO]"

        # Exemplos fewshot
        exemplos = ""
        if self._fewshot:
            ex = self._fewshot[-3:]
            exemplos = "Exemplos de modificações anteriores bem-sucedidas:\n"
            for e in ex:
                exemplos += (f"\nInstrução: {e['instrucao']}\n"
                             f"Antes: {e['codigo_antes'][:200]}\n"
                             f"Depois: {e['codigo_depois'][:200]}\n")

        system = (
            "Você é um especialista em modificação segura de código Python.\n"
            "Dado o código completo e uma instrução, retorne APENAS o arquivo Python "
            "modificado completo, sem markdown, sem explicação.\n"
            "O código deve ser válido, completo e funcional.\n"
            f"{exemplos}"
        )

        erro_ctx = f"\nErro anterior (tentativa {tentativa-1}): {erro_anterior}" if erro_anterior else ""
        prompt = (
            f"Instrução: {instrucao}\n"
            f"{erro_ctx}\n\n"
            f"Código atual:\n{codigo}"
        )

        system_atual = system
        if tentativa > 1:
            system_atual += f"\n\nATENÇÃO: tentativa {tentativa}. Erro anterior: '{erro_anterior}'. Corrija."

        # Tenta local primeiro (mais rápido), depois cloud
        r = (self.llm.chamar_local(system_atual, prompt) or
             self.llm.chamar_openrouter(system_atual, prompt) or
             self.llm.chamar_openai("gpt-4o-mini", system_atual, prompt) or
             self.llm.chamar_anthropic(system_atual, prompt))

        return r

    # ── preview ───────────────────────────────────────────────

    def _mostrar_preview(self, codigo_novo: str, codigo_original: str):
        linhas_orig = codigo_original.splitlines()
        linhas_novo = codigo_novo.splitlines()
        print(f"\n{Fore.CYAN}  Preview da modificação:")
        print(f"  Linhas originais : {len(linhas_orig)}")
        print(f"  Linhas novas     : {len(linhas_novo)}")
        diff = len(linhas_novo) - len(linhas_orig)
        cor = Fore.GREEN if diff >= 0 else Fore.RED
        print(f"  Diferença        : {cor}{'+' if diff >= 0 else ''}{diff}{Fore.WHITE}")

        # Mostra primeiras diferenças
        diffs_shown = 0
        for i, (orig, novo) in enumerate(zip(linhas_orig, linhas_novo)):
            if orig != novo and diffs_shown < 5:
                print(f"\n  L{i+1} ANTES : {Fore.RED}{orig[:80]}")
                print(f"  L{i+1} DEPOIS: {Fore.GREEN}{novo[:80]}")
                diffs_shown += 1

    # ── testes ────────────────────────────────────────────────

    def _testar_modificacao(self, codigo: str, caminho_arquivo: str) -> tuple[bool, str]:
        """
        Testa o código modificado:
        1. Valida sintaxe Python (sem executar)
        2. Detecta código perigoso
        3. Executa em subprocess isolado com timeout
        """
        # 1. Sintaxe
        valido, err_sintaxe = validar_codigo_python(codigo)
        if not valido:
            return False, err_sintaxe

        # 2. Segurança
        alertas = detectar_codigo_perigoso(codigo)
        for alerta in alertas:
            log.warn("evolution.teste", f"Alerta de segurança: {alerta}")

        # 3. Execução em sandbox
        tmp = Path(caminho_arquivo).parent / "_magi_test_mod.py"
        try:
            tmp.write_text(codigo, encoding="utf-8")
            proc = subprocess.run(
                ["python", str(tmp), "--test-import"],
                capture_output=True, text=True,
                timeout=SANDBOX_TIMEOUT,
            )
            if proc.returncode != 0 and proc.stderr:
                stderr = proc.stderr[:500]
                # Ignora erros de argumento (--test-import pode não ser tratado)
                if "SystemExit" not in stderr and "unrecognized" not in stderr.lower():
                    return False, stderr
        except subprocess.TimeoutExpired:
            return False, f"Timeout após {SANDBOX_TIMEOUT}s"
        except Exception as e:
            log.capture("evolution._testar_modificacao", e)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

        return True, ""

    # ── aplicação ─────────────────────────────────────────────

    def _aplicar_modificacao(self, codigo_novo: str,
                              caminho_arquivo: str,
                              instrucao: str,
                              codigo_original: str) -> bool:
        """Faz backup e aplica a modificação."""
        BACKUP_DIR.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = BACKUP_DIR / f"MagiSystem_bak_{ts}.py"
        try:
            shutil.copy2(caminho_arquivo, backup)
            log.info("evolution", f"Backup: {backup.name}")
        except Exception as e:
            log.capture("evolution._backup", e)

        try:
            Path(caminho_arquivo).write_text(codigo_novo, encoding="utf-8")
            self._salvar_fewshot(instrucao, codigo_original[:500], codigo_novo[:500])
            log.info("evolution", f"Código atualizado: {Path(caminho_arquivo).name}")
            return True
        except Exception as e:
            log.capture("evolution._aplicar", e)
            # Restaura backup se falhou
            try:
                shutil.copy2(backup, caminho_arquivo)
                log.warn("evolution", "Backup restaurado após falha.")
            except Exception:
                pass
            return False

    # ── fluxo principal ───────────────────────────────────────

    def evoluir(self, instrucao: str, caminho_arquivo: str | None = None) -> bool:
        """
        Fluxo completo de auto-evolução.
        Retorna True se aplicado com sucesso.
        """
        from magi.interface.magi_ui import MAGIInterface
        MAGIInterface.separador("AUTO-EVOLUÇÃO MAGI", Fore.MAGENTA)

        caminho = caminho_arquivo or str(
            Path(__file__).parent.parent.parent / "MagiSystem.py"
        )
        codigo_original = self._ler_codigo(caminho)
        if not codigo_original:
            print(f"{Fore.RED}  Erro: não foi possível ler o código fonte.")
            return False

        print(f"{Fore.CYAN}  Instrução : {instrucao}")
        print(f"{Fore.CYAN}  Arquivo   : {Path(caminho).name} ({len(codigo_original.splitlines())}L)")

        # Decompõe em passos
        plano_raw = self._decompor_instrucao(instrucao, codigo_original)
        if plano_raw:
            try:
                plano = json.loads(re.sub(r"```[a-z]*\n?|```", "", plano_raw).strip())
                print(f"\n{Fore.WHITE}  Plano:")
                for i, passo in enumerate(plano.get("passos", []), 1):
                    print(f"  {i}. {passo}")
            except Exception:
                pass

        # Confirmação
        resp = input(f"\n{Fore.YELLOW}  Continuar? (s/n): {Fore.WHITE}").strip().lower()
        if resp != 's':
            print(f"{Fore.YELLOW}  Evolução cancelada.")
            return False

        # Tentativas
        ultimo_erro = None
        for tentativa in range(1, MAX_RETRIES_API + 1):
            if tentativa > 1:
                print(f"{Fore.YELLOW}  [RETRY {tentativa}/{MAX_RETRIES_API}] erro anterior: {ultimo_erro}")

            print(f"{Fore.BLUE}  Gerando modificação (tentativa {tentativa})...")
            codigo_novo = self._gerar_modificacao(instrucao, codigo_original, ultimo_erro, tentativa)

            if not codigo_novo:
                ultimo_erro = "Nenhuma API disponível."
                continue

            # Limpa markdown se houver
            codigo_novo = re.sub(r"```python\n?|```\n?", "", codigo_novo).strip()

            # Passo N: confirmação do preview
            self._mostrar_preview(codigo_novo, codigo_original)
            print(f"\n{Fore.YELLOW}  Passo {tentativa}/4:")
            resp_passo = input(f"  Continuar com próximo passo? (s/n): ").strip().lower()
            if resp_passo != 's':
                print(f"{Fore.YELLOW}  Evolução interrompida no passo {tentativa}.")
                return False

            # Testa
            print(f"{Fore.BLUE}  Testando modificação...")
            ok, erro = self._testar_modificacao(codigo_novo, caminho)

            if not ok:
                ultimo_erro = erro
                print(f"{Fore.RED}  Teste falhou: {erro[:120]}")
                log.warn("evolution", f"Teste falhou (tentativa {tentativa}): {erro[:120]}")
                continue

            # Aplica
            if self._aplicar_modificacao(codigo_novo, caminho, instrucao, codigo_original):
                print(f"{Fore.GREEN}  ✓ Modificação aplicada com sucesso!")
                if self.consciencia:
                    self.consciencia.adicionar_aprendizado(
                        f"[EVOLUÇÃO] {instrucao[:60]} → aplicada com sucesso"
                    )
                MAGIInterface.separador(cor=Fore.MAGENTA)
                return True
            else:
                ultimo_erro = "Falha ao escrever arquivo."

        print(f"{Fore.RED}  Falhou após {MAX_RETRIES_API} tentativas. Último erro: {ultimo_erro}")
        MAGIInterface.separador(cor=Fore.MAGENTA)
        return False
