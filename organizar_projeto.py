"""
organizar_projeto.py
Execute UMA VEZ na pasta MAGI_SYSTEM para organizar tudo.
Cria a estrutura de pastas e move os arquivos.
NÃO apaga nada — só move.
"""

import os, shutil
from pathlib import Path

BASE = Path(__file__).parent

# ── Estrutura de destino ───────────────────────────────────────
PASTAS = [
    "magi/core",
    "magi/ai",
    "magi/evolution",
    "magi/security",
    "magi/interface",
    "magi/utils",
    "skills",
    "tests",
    "backups",
    "data",
]

# ── Mapeamento: arquivo → pasta destino ───────────────────────
MAPA = {
    # Core
    "magi_boot.py":        "magi/core",
    "magi_config.py":      "magi/core",

    # AI
    "magi_llm.py":         "magi/ai",

    # Evolution
    "magi_evolution.py":   "magi/evolution",
    "magi_evolucao_skills.jsonl": "magi/evolution",

    # Security
    "magi_security.py":    "magi/security",

    # Interface / UI
    "magi_ui.py":          "magi/interface",
    "NERV_dashboard_da_NERV.HTML": "magi/interface",
    "Visual_system.py":    "magi/interface",

    # Utils / Logger
    "magi_logger.py":      "magi/utils",

    # Skills
    "skill_estudo.py":     "skills",
    "skill_neural.py":     "skills",
    "skill_visual.py":     "skills",
    "Skill rag.PY":        "skills",   # nome com espaço
    "skill_rag.py":        "skills",
    "skill_agentes.py":    "skills",

    # Tests
    "test_core.py":        "tests",
    "Test_deepseek.py":    "tests",
    "test_groq.py":        "tests",
    "magi_testes.jsonl":   "tests",

    # Backups
    "MagiSystem copy.py":  "backups",
    "MagiSystem.bak.20260514_013529.py": "backups",

    # Data (arquivos de estado/memória)
    "magi_conhecimento.jsonl":       "data",
    "magi_conhecimento.txt":         "data",
    "magi_memoria.jsonl":            "data",
    "magi_episodios.jsonl":          "data",
    "magi_ego.json":                 "data",
    "magi_log.jsonl":                "data",
    "magi_valence_cache.json":       "data",
    "magi_sugestoes_evolucao.jsonl": "data",
    "magi_claude_skills.jsonl":      "data",
    "dados_aprendizado.json":        "data",
    "magi_fala.mp3":                 "data",
}

# Arquivos que FICAM na raiz (núcleo do sistema)
FICAM_NA_RAIZ = {
    "MagiSystem.py",
    "MagiServer.py",
    "magidataset.py",
    "Projeto2.env",
    "requirements.txt",
    "main.py",
    "organizar_projeto.py",
    "__init__.py",
}


def main():
    print("=" * 55)
    print("  MAGI — ORGANIZADOR DE PROJETO")
    print("=" * 55)

    # 1. Cria pastas
    for pasta in PASTAS:
        dest = BASE / pasta
        dest.mkdir(parents=True, exist_ok=True)
        # Cria __init__.py nos módulos Python
        if pasta.startswith("magi") or pasta in ("skills", "tests"):
            init = dest / "__init__.py"
            if not init.exists():
                init.write_text("")
    print(f"  ✓ Pastas criadas.\n")

    # 2. Move arquivos
    movidos, ja_la, nao_encontrado = [], [], []

    for arquivo, destino in MAPA.items():
        src = BASE / arquivo
        dst_dir = BASE / destino

        if not src.exists():
            nao_encontrado.append(arquivo)
            continue

        dst = dst_dir / src.name
        if dst.exists():
            ja_la.append(arquivo)
            continue

        try:
            shutil.move(str(src), str(dst))
            movidos.append(f"  {arquivo} → {destino}/")
        except Exception as e:
            print(f"  ✗ Erro ao mover {arquivo}: {e}")

    # 3. Move pasta MAGI_BACKUPS se existir
    magi_bk = BASE / "MAGI_BACKUPS"
    if magi_bk.exists() and magi_bk.is_dir():
        dest_bk = BASE / "backups" / "MAGI_BACKUPS"
        if not dest_bk.exists():
            shutil.move(str(magi_bk), str(dest_bk))
            movidos.append("  MAGI_BACKUPS/ → backups/")

    # 4. Relatório
    print(f"  ✓ Movidos ({len(movidos)}):")
    for m in movidos:
        print(m)

    if nao_encontrado:
        print(f"\n  ⚠ Não encontrados ({len(nao_encontrado)}) — provavelmente já removidos:")
        for f in nao_encontrado:
            print(f"    {f}")

    if ja_la:
        print(f"\n  ℹ Já estavam no destino ({len(ja_la)}):")
        for f in ja_la:
            print(f"    {f}")

    print("\n" + "=" * 55)
    print("  Estrutura final:")
    print("=" * 55)

    for item in sorted(BASE.iterdir()):
        if item.name.startswith("__") or item.name == ".git":
            continue
        if item.is_dir():
            sub = list(item.rglob("*.py")) + list(item.rglob("*.json*"))
            print(f"  📁 {item.name}/  ({len(sub)} arquivos)")
        elif item.suffix in (".py", ".env", ".txt", ".HTML", ".html"):
            print(f"  📄 {item.name}")

    print("\n  ✅ Concluído! Execute: python MagiSystem.py")
    print("=" * 55)


if __name__ == "__main__":
    main()
