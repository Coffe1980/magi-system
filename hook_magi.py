"""
Runtime hook do MAGI — força paths e imports críticos antes do main.py
"""
import os
import sys
from pathlib import Path

# ── Garante diretório base correto ────────────────────────────
if getattr(sys, 'frozen', False):
    BASE = Path(sys.executable).parent
    os.chdir(BASE)
    # Adiciona _internal ao path (onde o PyInstaller coloca os módulos)
    internal = BASE / "_internal"
    if internal.exists() and str(internal) not in sys.path:
        sys.path.insert(0, str(internal))
    if str(BASE) not in sys.path:
        sys.path.insert(0, str(BASE))

# ── Força PySide6 ─────────────────────────────────────────────
try:
    import PySide6
    import PySide6.QtCore
    import PySide6.QtGui
    import PySide6.QtWidgets
except Exception as e:
    print(f"[HOOK] PySide6 não carregou: {e}")

# ── Força shiboken6 ───────────────────────────────────────────
try:
    import shiboken6
except Exception:
    pass

# ── Força scipy/sklearn ───────────────────────────────────────
try:
    import scipy
    import scipy.spatial
    import sklearn
except Exception:
    pass
