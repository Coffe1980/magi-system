import os
from dotenv import load_dotenv
from openai import OpenAI
from colorama import Fore, init

init(autoreset=True)
load_dotenv("Projeto2.env")

key = os.getenv("GROQ_API_KEY", "")
if not key:
    print(f"{Fore.RED}GROQ_API_KEY não encontrada no Projeto2.env")
    exit(1)

client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key)

modelos = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]

for m in modelos:
    try:
        r = client.chat.completions.create(
            model=m,
            messages=[{"role": "user", "content": "Qual a data de hoje? Responda em uma linha."}],
            max_tokens=50,
        )
        print(f"{Fore.GREEN}[OK] {m}: {r.choices[0].message.content.strip()}")
    except Exception as e:
        print(f"{Fore.RED}[FALHOU] {m}: {e}")