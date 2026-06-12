import os
import sys
import time
import requests 
from dotenv import load_dotenv
from openai import OpenAI
import google.generativeai as genai
from colorama import Fore, Style, init

# 1. INICIALIZAÇÃO E CARREGAMENTO DE CHAVES
init(autoreset=True)

pasta_projeto = os.path.dirname(os.path.abspath(__file__))
# Tenta carregar o arquivo, testando variações de nome comuns no Windows
for nome_env in ['Projeto2.env', 'Projeto2.env.txt']:
    caminho = os.path.join(pasta_projeto, nome_env)
    if os.path.exists(caminho):
        load_dotenv(caminho)
        print(f"{Fore.GREEN}INFO: Arquivo de configuração '{nome_env}' carregado.")
        break
else:
    print(f"{Fore.RED}AVISO: Arquivo .env não encontrado. Verifique se ele está na pasta: {pasta_projeto}")

# --- DEFINIÇÃO DOS NÚCLEOS ---

class Melchior:
    def __init__(self):
        self.api_key = os.getenv("MISTRAL_API_KEY")
        self.url = "https://api.mistral.ai/v1/chat/completions"

    def pensar(self, prompt):
        if not self.api_key: return "Chave Mistral ausente."
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            data = {
                "model": "mistral-tiny",
                "messages": [{"role": "user", "content": f"Aja como MELCHIOR (Lógica): {prompt}"}]
            }
            response = requests.post(self.url, json=data, headers=headers, timeout=10)
            return response.json()['choices'][0]['message']['content']
        except Exception as e:
            return f"Erro Melchior: {str(e)}"

class Balthasar:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None

    def pensar(self, prompt):
        if not self.model: return "Chave Google ausente."
        try:
            resp = self.model.generate_content(f"Aja como BALTHASAR (Ética): {prompt}")
            return resp.text
        except Exception as e:
            return f"Erro Balthasar: {str(e)}"

class Casper:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key) if api_key else None

    def pensar(self, prompt):
        if not self.client: return "Chave OpenAI ausente."
        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=[{"role": "user", "content": prompt}]
            )
            return resp.choices[0].message.content
        except Exception as e: 
            return f"Erro Casper: {str(e)}"

class MagiSystem:
    def __init__(self):
        self.melchior = Melchior()
        self.balthasar = Balthasar()
        self.casper = Casper()

# --- INTERFACE ---

def digitacao_lenta(texto, cor=Fore.WHITE):
    for char in texto:
        sys.stdout.write(cor + char)
        sys.stdout.flush()
        time.sleep(0.005)
    print()

def efeito_carregamento(nome, cor):
    sys.stdout.write(cor + f"[{nome}] PROCESSANDO...")
    for _ in range(15):
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(0.04)
    print(" [OK]")

# --- LOOP PRINCIPAL ---

if __name__ == "__main__":
    magi = MagiSystem()
    
    print(f"\n{Fore.RED}{Style.BRIGHT}=========================================")
    print(f"{Fore.RED}   SISTEMA DE SUPORTE À DECISÃO MAGI     ")
    print(f"{Fore.RED}        NERV - MATRIZ DE CONSENSO        ")
    print(f"{Fore.RED}=========================================")

    while True:
        user_input = input(f"\n{Fore.YELLOW}>> ")
        
        if user_input.lower() in ['sair', 'exit']:
            break

        print(f"\n{Fore.CYAN}[ANALISANDO PRIORIDADES...]")
        
        efeito_carregamento("MELCHIOR", Fore.BLUE)
        r1 = magi.melchior.pensar(user_input)
        
        efeito_carregamento("BALTHASAR", Fore.GREEN)
        r2 = magi.balthasar.pensar(user_input)

        print(f"{Fore.RED}[CASPER] GERANDO VEREDITO FINAL...")
        prompt_final = f"Decida: Melchior diz '{r1}'. Balthasar diz '{r2}'. Pergunta: {user_input}. Dê um veredito curto."
        resultado = magi.casper.pensar(prompt_final)
        
        print(f"\n{Fore.WHITE}{Style.BRIGHT}================ VEREDITO ================")
        digitacao_lenta(resultado, Fore.YELLOW)
        print(f"{Fore.WHITE}{Style.BRIGHT}==========================================")