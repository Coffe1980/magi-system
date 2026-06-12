"""
magi/utils/magi_logger.py
Logger centralizado — substitui todos os bare except/pass.
"""
import os, sys, json, time, traceback
from pathlib import Path
from datetime import datetime
from enum import IntEnum


class Level(IntEnum):
    DEBUG = 0
    INFO  = 1
    WARN  = 2
    ERROR = 3


LEVEL_COLORS = {
    Level.DEBUG: "\033[90m",
    Level.INFO:  "\033[36m",
    Level.WARN:  "\033[33m",
    Level.ERROR: "\033[31m",
}
RESET = "\033[0m"


class MAGILogger:
    """
    Logger estruturado e thread-safe para o MAGI.
    - Grava em arquivo JSONL
    - Exibe no console com cores
    - Nunca silencia erros sem registrar
    """

    def __init__(self, log_path: str | None = None, min_level: Level = Level.INFO,
                 console: bool = True, max_lines: int = 5000):
        self.log_path  = Path(log_path or "log_nerv.jsonl")
        self.min_level = min_level
        self.console   = console
        self.max_lines = max_lines
        self._count    = 0
        self._session  = datetime.now().isoformat(timespec="seconds")

    # ── interface principal ───────────────────────────────────

    def debug(self, modulo: str, msg: str, **kw):
        self._log(Level.DEBUG, modulo, msg, **kw)

    def info(self, modulo: str, msg: str, **kw):
        self._log(Level.INFO, modulo, msg, **kw)

    def warn(self, modulo: str, msg: str, **kw):
        self._log(Level.WARN, modulo, msg, **kw)

    def error(self, modulo: str, msg: str, exc: BaseException | None = None, **kw):
        if exc:
            kw["traceback"] = traceback.format_exc()
        self._log(Level.ERROR, modulo, msg, **kw)

    def capture(self, modulo: str, exc: BaseException, contexto: str = ""):
        """
        Substitui os bare 'except: pass'.
        Registra o erro com traceback completo sem silenciar.
        """
        self.error(modulo, f"{contexto}: {type(exc).__name__}: {exc}", exc=exc)

    # ── interno ───────────────────────────────────────────────

    def _log(self, level: Level, modulo: str, msg: str, **kw):
        if level < self.min_level:
            return
        ts  = datetime.now().isoformat(timespec="milliseconds")
        rec = {"ts": ts, "lvl": level.name, "mod": modulo, "msg": msg, **kw}

        # Console
        if self.console:
            col = LEVEL_COLORS.get(level, "")
            tag = f"[{level.name:5}]"
            print(f"{col}{tag} {modulo}: {msg}{RESET}", flush=True)

        # Arquivo
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            self._count += 1
            if self._count % 500 == 0:
                self._rotate()
        except OSError:
            pass  # única situação onde silenciar é aceitável (disco cheio)

    def _rotate(self):
        """Mantém o arquivo de log com no máximo max_lines linhas."""
        try:
            lines = self.log_path.read_text(encoding="utf-8").splitlines()
            if len(lines) > self.max_lines:
                self.log_path.write_text(
                    "\n".join(lines[-self.max_lines:]) + "\n", encoding="utf-8")
        except Exception:
            pass

    def tail(self, n: int = 50, level: str = "INFO") -> list[str]:
        """Retorna as últimas n linhas do log filtradas por nível."""
        try:
            lines = self.log_path.read_text(encoding="utf-8").splitlines()
            filtered = [l for l in lines if f'"lvl": "{level}"' in l or level == "DEBUG"]
            return filtered[-n:]
        except Exception:
            return []

    def tail_plain(self, n: int = 80, level: str = "INFO") -> list[str]:
        """Retorna linhas formatadas legíveis (para exibição no terminal/dashboard)."""
        out = []
        for raw in self.tail(n * 3, "DEBUG"):
            try:
                rec = json.loads(raw)
                lvl = rec.get("lvl", "INFO")
                if Level[lvl] < Level[level]:
                    continue
                out.append(f"[{rec['ts'][11:19]}] [{lvl:5}] {rec['mod']}: {rec['msg']}")
            except Exception:
                out.append(raw[:120])
            if len(out) >= n:
                break
        return out


# Instância global — importada por todos os módulos
log = MAGILogger()
