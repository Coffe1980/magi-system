"""
magi_boot.py
Inicialização resiliente do MAGI.
Execute: py magi_boot.py
"""
import os, sys
from pathlib import Path
from colorama import Fore, init as colorama_init


def _fix_encoding():
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _check_dependencies():
    required = [
        ("colorama",              "colorama"),
        ("dotenv",                "python-dotenv"),
        ("google.genai",          "google-genai"),
        ("openai",                "openai"),
        ("sentence_transformers", "sentence-transformers"),
        ("faiss",                 "faiss-cpu"),
    ]
    missing = []
    for mod, pkg in required:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"{Fore.RED}  Dependências faltando: {', '.join(missing)}")
        print(f"{Fore.YELLOW}  Execute: pip install {' '.join(missing)}")


def _ensure_dirs(base: Path):
    for pasta in ("MAGI_BACKUPS",):
        try:
            (base / pasta).mkdir(exist_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    _fix_encoding()
    colorama_init(autoreset=True)

    boot_dir = Path(__file__).parent.resolve()

    _check_dependencies()
    _ensure_dirs(boot_dir)

    # Garante que Python acha o MagiSystem.py
    if str(boot_dir) not in sys.path:
        sys.path.insert(0, str(boot_dir))

    magi_path = boot_dir / "MagiSystem.py"
    if not magi_path.exists():
        print(f"{Fore.RED}  [ERRO] MagiSystem.py não encontrado em {boot_dir}")
        sys.exit(1)

    # Roda MagiSystem.py como __main__ — ativa o loop principal completo
    import runpy
    runpy.run_path(str(magi_path), run_name="__main__")