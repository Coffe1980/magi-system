"""
magi/core/magi_config.py
Toda configuração centralizada — carregada UMA vez no boot.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega .env do diretório raiz do projeto
_PROJECT_ROOT = Path(__file__).parent.parent.parent
for _env in [_PROJECT_ROOT / "Projeto2.env", _PROJECT_ROOT / ".env"]:
    if _env.exists():
        load_dotenv(_env)
        break

# ── APIs ─────────────────────────────────────────────────────
GOOGLE_API_KEY     = os.getenv("GOOGLE_API_KEY", "")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")

# ── Modelo local (LM Studio / Ollama) ────────────────────────
LOCAL_CONFIG = {
    "ativo":  os.getenv("LOCAL_ATIVO", "true").lower() == "true",
    "url":    os.getenv("LOCAL_URL",   "http://127.0.0.1:1234/v1"),
    "modelo": os.getenv("LOCAL_MODELO", "qwen3-14b"),
}

# ── OpenRouter ───────────────────────────────────────────────
OPENROUTER_CONFIG = {
    "url":    "https://openrouter.ai/api/v1",
    "modelo": os.getenv("OPENROUTER_MODELO", "deepseek/deepseek-chat-v3-0324:free"),
    # Fallback chain (provedores diferentes para evitar rate limit compartilhado)
    "fallbacks": [
        "deepseek/deepseek-r1-0528:free",
        "mistralai/mistral-small-3.1-24b-instruct:free",
        "qwen/qwen3-235b-a22b:free",
        "nvidia/llama-3.1-nemotron-ultra-253b-v1:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ],
}

# ── Núcleos MAGI ─────────────────────────────────────────────
from colorama import Fore

NUCLEOS: dict[str, dict] = {
    "MELCHIOR-1": {
        "cor":       Fore.CYAN,
        "subtitulo": "A CIENTISTA",
        "emoji":     "🔬",
        "model":     "gemini-2.0-flash",
        "backend":   "google",
        "fallback":  "gemini-1.5-flash",
        "fallback_openai_model":  "gpt-4o-mini",
        "fallback_openai_system": (
            "Você é MELCHIOR-1, núcleo lógico do MAGI. "
            "Analise racionalmente. Máx 300 palavras."
        ),
        "system": (
            "Você é MELCHIOR-1, o núcleo lógico-científico do MAGI.\n"
            "Analise com precisão técnica e lógica rigorosa.\n"
            "Máximo 300 palavras. Sem devaneios filosóficos."
        ),
    },
    "BALTHASAR-2": {
        "cor":       Fore.GREEN,
        "subtitulo": "A MÃE",
        "emoji":     "🛡️",
        "model":     "gemini-2.0-flash-lite",
        "backend":   "google",
        "fallback":  "gemini-1.5-flash",
        "fallback_openai_model":  "gpt-4o-mini",
        "fallback_openai_system": (
            "Você é BALTHASAR-2, núcleo ético do MAGI. "
            "Avalie impacto humano. Máx 300 palavras."
        ),
        "system": (
            "Você é BALTHASAR-2, o núcleo ético-protetor do MAGI.\n"
            "Avalie impacto humano, riscos e implicações éticas.\n"
            "Máximo 300 palavras."
        ),
    },
    "CASPER-3": {
        "cor":       Fore.MAGENTA,
        "subtitulo": "A MULHER",
        "emoji":     "⚡",
        "model":     "deepseek/deepseek-chat-v3-0324:free",
        "backend":   "openrouter",
        "fallback_openai_model":  "gpt-4o-mini",
        "fallback_openai_system": (
            "Você é CASPER-3, núcleo de síntese do MAGI. "
            "Sintetize e dê veredito final. Máx 400 palavras."
        ),
        "system": (
            "Você é CASPER-3, o núcleo de síntese do MAGI.\n"
            "Sua função: sintetizar as análises de MELCHIOR e BALTHASAR e dar a palavra final.\n"
            "Seja direta, concreta, útil. Máximo 400 palavras."
        ),
    },
    "ADAM-0": {
        "cor":       Fore.WHITE,
        "subtitulo": "O CÓDIGO",
        "emoji":     "🖥",
        "model":     "deepseek/deepseek-r1-0528:free",
        "backend":   "openrouter",
        "fallback_openai_model":  "gpt-4o-mini",
        "fallback_openai_system": (
            "Você é ADAM-0, núcleo de código do MAGI. "
            "Código completo e funcional apenas."
        ),
        "system": (
            "Você é ADAM-0, núcleo de engenharia do MAGI.\n"
            "Responda APENAS com código: completo, tipado, comentado, pronto para produção.\n"
            "Zero introdução. Zero filosofia. Zero markdown extra."
        ),
    },
}

# ── Caminhos de dados ─────────────────────────────────────────
DATA_DIR = _PROJECT_ROOT
MEMORIA_PATH    = DATA_DIR / "magi_memoria.jsonl"
CONHECIMENTO_PATH = DATA_DIR / "magi_conhecimento.jsonl"
SUGESTOES_PATH  = DATA_DIR / "magi_sugestoes_evolucao.jsonl"
FEWSHOT_PATH    = DATA_DIR / "magi_claude_skills.json"
EGO_PATH        = DATA_DIR / "magi_ego.json"
LOG_PATH        = DATA_DIR / "log_nerv.jsonl"
BACKUP_DIR      = DATA_DIR / "MAGI_BACKUPS"

# ── Runtime ───────────────────────────────────────────────────
CACHE_MAX_MIN     = 30    # validade do cache semântico em minutos
EVOLUCAO_MAX_PROMPT = 60_000  # chars máx no prompt de evolução
SANDBOX_TIMEOUT   = 15   # segundos para execução em sandbox
MAX_RETRIES_API   = 3    # tentativas por API
OPENROUTER_TIMEOUT = 45  # segundos

def resumo() -> dict:
    """Retorna resumo da config para diagnóstico."""
    return {
        "google_key":        bool(GOOGLE_API_KEY),
        "openai_key":        bool(OPENAI_API_KEY),
        "openrouter_key":    bool(OPENROUTER_API_KEY),
        "anthropic_key":     bool(ANTHROPIC_API_KEY),
        "local_ativo":       LOCAL_CONFIG["ativo"],
        "local_modelo":      LOCAL_CONFIG["modelo"],
        "openrouter_modelo": OPENROUTER_CONFIG["modelo"],
    }
