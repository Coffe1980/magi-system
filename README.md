# MAGI SYSTEM

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Em%20desenvolvimento-yellow)
![Open Source](https://img.shields.io/badge/Open%20Source-Sim-brightgreen)

> Sistema de IA multi-agente inspirado no supercomputador MAGI da série **Neon Genesis Evangelion**.  
> Três núcleos de IA — MELCHIOR-1, BALTHASAR-2 e CASPER-3 — trabalham em paralelo para analisar, raciocinar e sintetizar respostas.

---

## Núcleos

| Núcleo | Papel | Modelo |
|---|---|---|
| 🔬 MELCHIOR-1 | Análise lógica e técnica | DeepSeek or OpenAI |
| 🛡️ BALTHASAR-2 | Avaliação ética e humana | DeepSeek or OpenAI |
| ⚡ CASPER-3 | Síntese e veredito final | DeepSeek via OpenRouter |
| 🖥️ ADAM-0 | Engenharia e código | DeepSeek R1 via OpenRouter |

---

## Funcionalidades

- **Multi-agente**: três núcleos de IA deliberando em paralelo
- **Memória semântica**: FAISS + sentence-transformers para RAG
- **Estudo autônomo**: aprende sozinho pesquisando na web e no arxiv
- **Interface local**: UI desktop com PySide6 (tema NERV)
- **Voz**: reconhecimento e síntese de fala
- **Auto-evolução**: sugere e aplica melhorias ao próprio código

---

## Requisitos

- Python 3.11+
- Pelo menos uma chave de API (Google ou OpenRouter — ambas têm tier gratuito)

---

## Instalação

```bash
# 1. Clone o repositório
git clone https://github.com/Coffe1980/magi-system.git
cd magi-system

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Configure as chaves de API
cp .env.example .env
# Edite o .env com suas chaves

# 4. Execute
python main.py
```

---

## Configuração

Copie `.env.example` para `.env` e preencha as chaves:

```env
OPENROUTER_API_KEY=sua_chave_aqui
GOOGLE_API_KEY=sua_chave_aqui
```

Você pode obter chaves gratuitas em:
- [OpenRouter](https://openrouter.ai) — acesso a DeepSeek, Mistral, LLaMA e outros
- [Google AI Studio](https://aistudio.google.com) — Gemini

---

## Estrutura do projeto

```
magi-system/
├── main.py                  # Ponto de entrada
├── MagiSystem.py            # Core do sistema e todos os núcleos
├── MagiServer.py            # Servidor FastAPI (opcional)
├── magi_ui.py               # Interface PySide6
├── magi_voz.py              # Sistema de voz
├── magi_usuario.py          # Perfil e histórico do usuário
├── magidataset.py           # Coleta de dados e feeds
├── magi/                    # Módulos internos
│   ├── ai/                  # LLM backends
│   ├── core/                # Config e boot
│   ├── security/            # Segurança e auditoria
│   ├── evolution/           # Auto-evolução
│   ├── interface/           # UI modular
│   └── utils/               # Logger e utilitários
├── skills/                  # Skills carregadas sob demanda
│   ├── skill_estudo.py      # Estudo autônomo
│   ├── skill_rag.py         # RAG e busca semântica
│   └── ...
├── data/                    # Dados gerados em runtime (não versionado)
│   ├── memory/
│   ├── logs/
│   └── knowledge/
├── .env.example             # Modelo de configuração
├── requirements.txt
└── LICENSE
```

---

## Aviso legal

Este projeto é open source, sem fins lucrativos, distribuído sob a licença MIT.  
"MAGI", "NERV", "Neon Genesis Evangelion" e os personagens relacionados são propriedade de **Hideaki Anno / Gainax / Khara**.  
Este projeto é uma obra de fã (*fan project*) sem qualquer afiliação ou endosso oficial.

---

## Licença

MIT — veja [LICENSE](LICENSE) para detalhes.
