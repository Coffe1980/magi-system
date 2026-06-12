"""
main.py — Ponto de entrada do MAGI SYSTEM
"""
import os
import sys
import runpy
import threading
from pathlib import Path

# ── Garante diretório base correto ────────────────────────────
if getattr(sys, 'frozen', False):
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).parent

os.chdir(_BASE)
sys.path.insert(0, str(_BASE))

def _carregar_magi():
    try:
        ns = runpy.run_path(str(_BASE / "MagiSystem.py"), run_name="__magi__")
        magi = ns.get("magi") or ns.get("MAGISystem", None)
        if callable(magi):
            magi = magi()
        return magi
    except Exception as e:
        print(f"[MAGI] Erro ao carregar sistema: {e}")
        import traceback; traceback.print_exc()
        return None

def main():
    # Tenta importar PySide6 mostrando erro real
    ui_disponivel = False
    try:
        import PySide6
        import PySide6.QtWidgets
        import PySide6.QtCore
        import PySide6.QtGui
        from magi_ui import iniciar_ui
        ui_disponivel = True
        print(f"[MAGI] PySide6 {PySide6.__version__} OK")
    except Exception as e:
        print(f"[MAGI] PySide6 ERRO: {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()

    print("[MAGI] Inicializando sistema...")
    magi = _carregar_magi()

    if ui_disponivel and magi:
        app, win = iniciar_ui(magi)
        try:
            from magi_voz import integrar_voz_ao_magi
            voz = integrar_voz_ao_magi(magi)
            voz.iniciar()
            win._event_log.add("OK", "Sistema de voz ativo — diga 'MAGI'")
        except Exception as e:
            win._event_log.add("WARN", f"Voz não iniciada: {e}")
        sys.exit(app.exec())
    elif ui_disponivel and not magi:
        from magi_ui import iniciar_ui
        app, win = iniciar_ui(magi=None)
        sys.exit(app.exec())
    else:
        runpy.run_path(str(_BASE / "MagiSystem.py"), run_name="__main__")

if __name__ == "__main__":
    main()