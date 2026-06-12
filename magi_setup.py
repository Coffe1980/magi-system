"""
magi_setup.py — Cria a estrutura de pastas do MAGI e migra arquivos existentes
Execute uma vez: py magi_setup.py
"""
import os
import shutil
from pathlib import Path

BASE = Path(__file__).parent

# ── Estrutura de pastas ───────────────────────────────────────
PASTAS = [
    BASE / "data" / "memory",
    BASE / "data" / "logs",
    BASE / "data" / "knowledge",
    BASE / "skills",
]

for p in PASTAS:
    p.mkdir(parents=True, exist_ok=True)
    print(f"  ✓ {p.relative_to(BASE)}")

# ── Migração de arquivos existentes ──────────────────────────
MIGRACOES = {
    # (arquivo antigo) → (novo destino)
    "magi_memoria.jsonl":           "data/memory/magi_memoria.jsonl",
    "magi_memoria.json":            "data/memory/magi_memoria.jsonl",
    "magi_ego.json":                "data/memory/magi_ego.json",
    "magi_valence_cache.json":      "data/memory/magi_valence_cache.json",
    "magi_episodios.jsonl":         "data/memory/magi_episodios.jsonl",
    "magi_log.jsonl":               "data/logs/magi_log.jsonl",
    "magi_log.json":                "data/logs/magi_log.jsonl",
    "magi_testes.jsonl":            "data/logs/magi_testes.jsonl",
    "magi_conhecimento.jsonl":      "data/knowledge/magi_conhecimento.jsonl",
    "magi_conhecimento.json":       "data/knowledge/magi_conhecimento.jsonl",
    "magi_sugestoes_evolucao.jsonl":"data/knowledge/magi_sugestoes_evolucao.jsonl",
    "magi_sugestoes_evolucao.json": "data/knowledge/magi_sugestoes_evolucao.jsonl",
    "magi_evolucao_skills.jsonl":   "data/knowledge/magi_evolucao_skills.jsonl",
    "magi_evolucao_skills.json":    "data/knowledge/magi_evolucao_skills.jsonl",
    "magi_claude_skills.jsonl":     "data/knowledge/magi_claude_skills.jsonl",
    "magi_fontes.jsonl":            "data/knowledge/magi_fontes.jsonl",
}

print("\n  Migrando arquivos...")
migrados = 0
for origem_nome, destino_rel in MIGRACOES.items():
    origem  = BASE / origem_nome
    destino = BASE / destino_rel
    if origem.exists() and not destino.exists():
        shutil.copy2(origem, destino)
        print(f"  → {origem_nome} → {destino_rel}")
        migrados += 1
    elif origem.exists() and destino.exists():
        print(f"  ~ {origem_nome} já migrado (mantido)")
    else:
        # Cria vazio se não existir
        if not destino.exists():
            destino.write_text("{}" if destino.suffix == ".json" else "")

print(f"\n  {migrados} arquivo(s) migrado(s).")
print("\n  Estrutura final:")
for pasta in PASTAS:
    arquivos = list(pasta.glob("*"))
    print(f"  📁 {pasta.relative_to(BASE)}/ ({len(arquivos)} arquivo(s))")
    for a in arquivos:
        print(f"     · {a.name}")

print("\n  ✅ Setup concluído! Rode: py -3.11 main.py")
