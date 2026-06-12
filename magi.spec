# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

BASE = Path(".").resolve()

a = Analysis(
    ["main.py"],
    pathex=[str(BASE)],
    binaries=[],
    datas=[
        ("Projeto2.env",        "."),
        ("magi_voz.py",         "."),
        ("magi_ui.py",          "."),
        ("magi_usuario.py",     "."),
        ("MagiSystem.py",       "."),
        ("MagiServer.py",       "."),
        ("magidataset.py",      "."),
        ("magi_ego.json",       "."),
        ("data",                "data"),
        ("skills",              "skills"),
    ],
    hiddenimports=[
        # PySide6 completo
        "PySide6",
        "PySide6.QtWidgets",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtOpenGL",
        "PySide6.QtNetwork",
        "PySide6.QtPrintSupport",
        "shiboken6",
        # Voz
        "speech_recognition", "pyaudio", "edge_tts",
        "pygame", "pygame.mixer",
        # IA
        "google.genai", "openai", "faiss", "numpy",
        "sentence_transformers",
        "scipy", "scipy.spatial", "scipy.special",
        "scipy.sparse", "scipy.linalg",
        "sklearn", "sklearn.utils",
        "sklearn.utils._chunking",
        "sklearn.utils._param_validation",
        # Misc
        "colorama", "dotenv", "mss", "asyncio",
        "threading", "queue", "pathlib", "collections",
        "math", "time", "json", "re",
    ],
    hookspath=[],
    runtime_hooks=["hook_magi.py"],  # <-- nosso hook forçado
    excludes=["tkinter", "matplotlib", "pytest", "jupyter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="MAGI",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=False,
    name="MAGI",
)
