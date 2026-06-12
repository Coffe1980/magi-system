"""
╔══════════════════════════════════════════════════════════════╗
║  MAGI SKILL — ESTUDO AUTÔNOMO                                ║
║  Carregado sob demanda pelos comandos:                       ║
║    estudar · voltei · conhecimento · captcha                 ║
╚══════════════════════════════════════════════════════════════╝
"""

import os, time, re, json, threading, urllib.request, urllib.parse, random
from html import unescape
from datetime import datetime
from pathlib import Path
from colorama import Fore

# ════════════════════════════════════════════════
# CAPTCHA DEFENSE SYSTEM
# ════════════════════════════════════════════════

class MAGICaptcha:
    CAPTCHA_PATTERNS = [
        "captcha", "recaptcha", "hcaptcha",
        "verify you are human", "i am not a robot",
        "cloudflare", "access denied", "attention required", "security check"
    ]
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 OPR/108.0.0.0",
    ]

    ACCEPT_LANGUAGES = [
        "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
        "pt-BR,pt;q=0.8,en;q=0.6",
        "en-GB,en;q=0.9,pt;q=0.8",
    ]


    def __init__(self):
        self.detectados = 0
        self.bloqueios = {}
        self.ultimo_captcha = None
        self._cache: dict[str, tuple[list[str], str]] = {}

    def detectar(self, html: str) -> bool:
        if not html:
            return False
        html_lower = html.lower()
        for pattern in self.CAPTCHA_PATTERNS:
            if pattern in html_lower:
                self.detectados += 1
                self.ultimo_captcha = datetime.now().isoformat(timespec="seconds")
                return True
        return False

    def delay_humano(self):
        time.sleep(random.uniform(1.5, 4.0))

    def gerar_headers(self):
        ua = random.choice(self.USER_AGENTS)
        lang = random.choice(self.ACCEPT_LANGUAGES)
        headers = {
            "User-Agent": ua,
            "Accept-Language": lang,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        if "Chrome" in ua or "Edg" in ua or "OPR" in ua:
            headers["Sec-CH-UA-Mobile"] = "?0"
            headers["Sec-CH-UA-Platform"] = random.choice(['"Windows"', '"macOS"', '"Linux"'])
        return headers

    def cache_get(self, query: str, max_age_min: int = 60) -> list[str] | None:
        if query not in self._cache:
            return None
        frases, ts = self._cache[query]
        try:
            idade = (datetime.now() - datetime.fromisoformat(ts)).total_seconds() / 60
            if idade <= max_age_min:
                return frases
        except Exception:
            pass
        del self._cache[query]
        return None

    def cache_set(self, query: str, frases: list[str]):
        self._cache[query] = (frases, datetime.now().isoformat(timespec="seconds"))

    def registrar_bloqueio(self, dominio: str):
        self.bloqueios[dominio] = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "tentativas": self.bloqueios.get(dominio, {}).get("tentativas", 0) + 1
        }

    def status(self):
        return {
            "captchas_detectados": self.detectados,
            "ultimo_captcha": self.ultimo_captcha,
            "dominios_bloqueados": len(self.bloqueios)
        }


# ══════════════════════════════════════════════════════════════
# MODO ESTUDO AUTÔNOMO
# ══════════════════════════════════════════════════════════════

class MAGIEstudo:
    CICLO_ON_MIN  = 45
    CICLO_OFF_MIN = 15
    CONHECIMENTO_PATH = Path(__file__).parent.parent / "data" / "knowledge" / "magi_conhecimento.jsonl"
    SUGESTOES_PATH    = Path(__file__).parent.parent / "data" / "knowledge" / "magi_sugestoes_evolucao.jsonl"

    TOPICOS_BASE = [
        # === SEGURANÇA CIBERNÉTICA (via arxiv.org) ===
        "arxiv: cybersecurity vulnerabilities exploitation techniques 2025",
        "arxiv: malware detection deep learning neural network",
        "arxiv: network intrusion detection system anomaly",
        "arxiv: zero trust architecture security model",
        "arxiv: cryptographic protocols formal verification",
        "arxiv: ransomware analysis defense mechanisms",
        "arxiv: adversarial attacks machine learning security",
        "arxiv: threat intelligence cyber attack attribution",
        "arxiv: vulnerability assessment penetration testing automated",
        "arxiv: side channel attacks hardware security",

        # === RACIOCÍNIO AVANÇADO (Opus Style) ===
        "técnicas avançadas de chain of thought e tree of thoughts",
        "como fazer reasoning profundo em problemas complexos",
        "estratégias de decomposição de problemas difíceis",
        "meta-cognição e auto-reflexão em IA",
        "prompt engineering de nível expert (Claude Opus techniques)",
        "lógica formal, falácias e argumentação rigorosa",
        "pensamento probabilístico e tomada de decisão sob incerteza",
        
        # === ENGENHARIA E CÓDIGO ===
        "melhores práticas de engenharia de software 2026",
        "arquitetura de sistemas complexos e código limpo",
        "debugging avançado e análise de código",
        "como escrever código que seja fácil de evoluir",
        "padrões de design e princípios SOLID aplicados",
        
        # === CONHECIMENTO GERAL DE ALTO NÍVEL ===
        "filosofia da mente e consciência artificial",
        "ética avançada em IA e alinhamento",
        "neurociência cognitiva e como o cérebro humano raciocina",
        "física, matemática e lógica aplicada a problemas do mundo real",
        "história da inteligência artificial e lições aprendidas",
        
        # === CRIATIVIDADE + RACIOCÍNIO ===
        "como gerar ideias originais e soluções criativas",
        "escrita técnica de alta qualidade e clareza",
        "análise crítica de argumentos e detecção de bullshit",
        "raciocínio contrafactual e simulação mental",
    ]

    def __init__(self, magi_system: "MAGISystem"):
        self.magi      = magi_system
        self._ativo    = False
        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._sessoes_concluidas = 0

    @property
    def ativo(self) -> bool:
        return self._ativo

    def iniciar(self):
        if self._ativo:
            print(f"{Fore.YELLOW}  [ESTUDO] Já está estudando.")
            return
        self._ativo = True
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop_estudo, daemon=True)
        self._thread.start()
        print(f"{Fore.CYAN}  [ESTUDO] MAGI iniciou modo de estudo autônomo.")
        print(f"{Fore.WHITE}  Ciclos: {self.CICLO_ON_MIN}min estudando → {self.CICLO_OFF_MIN}min pausa")
        print(f"{Fore.WHITE}  Digite {Fore.YELLOW}voltei{Fore.WHITE} para pausar.")

    def parar(self):
        if not self._ativo:
            print(f"{Fore.YELLOW}  [ESTUDO] Não está em modo de estudo.")
            return
        self._ativo = False
        self._stop_evt.set()
        print(f"{Fore.GREEN}  [ESTUDO] Modo de estudo pausado. Bem-vindo de volta!")
        print(f"{Fore.CYAN}  Sessões concluídas: {self._sessoes_concluidas}")
        print(f"{Fore.CYAN}  Conhecimentos salvos: {self._contar_conhecimentos()}")

    def _loop_estudo(self):
        while not self._stop_evt.is_set():
            print(f"{Fore.CYAN}[ESTUDO·ATIVO] Iniciando sessão de {self.CICLO_ON_MIN}min...")
            fim_on = time.time() + self.CICLO_ON_MIN * 60
            rodada = 0
            while time.time() < fim_on and not self._stop_evt.is_set():
                rodada += 1
                print(f"{Fore.CYAN}  [ESTUDO] Rodada {rodada} — pesquisando...")
                self._ciclo_aprendizado()
                self._stop_evt.wait(timeout=90)
            if self._stop_evt.is_set():
                break
            self._sessoes_concluidas += 1
            print(f"{Fore.YELLOW}[ESTUDO·PAUSA] Sessão {self._sessoes_concluidas} concluída. Pausa de {self.CICLO_OFF_MIN}min.")
            self._stop_evt.wait(timeout=self.CICLO_OFF_MIN * 60)

    def _ciclo_aprendizado(self):
        try:
            topico = self._escolher_topico()
            print(f"{Fore.BLUE}  [ESTUDO] Tópico: {Fore.WHITE}{topico}")

            # Roteamento: tópicos "arxiv:" usam o buscador especializado
            if topico.lower().startswith("arxiv:"):
                query = topico[6:].strip()
                print(f"{Fore.CYAN}  [ARXIV] Buscando papers: {query}")
                snippets = self._buscar_arxiv(query)
                fonte = "arxiv.org"
            else:
                snippets = self._buscar_web(topico)
                fonte = "duckduckgo-lite"

            if not snippets:
                print(f"{Fore.YELLOW}  [ESTUDO] Sem resultado para: {topico}")
                return
            conteudo_web = "\n".join(snippets[:4])
            perguntas = self._gerar_perguntas(topico, conteudo_web)
            if not perguntas:
                return
            for pergunta in perguntas[:3]:
                if self._stop_evt.is_set():
                    return
                resposta = self._responder_pergunta(pergunta, conteudo_web)
                if not resposta:
                    continue
                self._salvar_conhecimento(topico, pergunta, resposta, snippets, fonte=fonte)
                self.magi.consciencia.adicionar_aprendizado(f"[ESTUDO] {topico}: {resposta[:80]}")
            self._sessoes_concluidas_parcial = getattr(self, "_sessoes_concluidas_parcial", 0) + 1
            if self._sessoes_concluidas_parcial % 3 == 0:
                self._gerar_sugestao_evolucao(topico, conteudo_web)
        except Exception as e:
            print(f"{Fore.RED}  [ESTUDO·ERRO] {e}")

    def _escolher_topico(self) -> str:
        tema = self.magi.consciencia.tema_dominante()
        mapa = {
            "técnico":  ["algoritmos de machine learning", "segurança cibernética 2025",
                        "linguagens de programação novas", "sistemas distribuídos",
                        "arxiv: cybersecurity vulnerabilities exploitation techniques 2025",
                        "arxiv: malware detection deep learning neural network"],
            "ético":    ["ética em inteligência artificial", "filosofia moral contemporânea",
                        "direitos digitais", "viés algorítmico"],
            "criativo": ["neurociência da criatividade", "arte generativa",
                        "escrita criativa técnicas", "design de sistemas"],
            "factual":  ["descobertas científicas recentes", "história da computação",
                        "matemática aplicada", "física moderna"],
            "decisão":  ["teoria da decisão", "psicologia cognitiva",
                        "análise de risco", "lógica fuzzy"],
        }
        opcoes = mapa.get(tema, self.TOPICOS_BASE)
        return random.choice(opcoes)

    def _buscar_web(self, query: str) -> list[str]:
        urls = [
            f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote_plus(query)}",
            f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}",
        ]
        for tentativa, url in enumerate(urls, start=1):
            try:
                self.magi.captcha.delay_humano()
                req = urllib.request.Request(url, headers=self.magi.captcha.gerar_headers())
                with urllib.request.urlopen(req, timeout=12) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                if self.magi.captcha.detectar(html):
                    print(f"{Fore.RED}  [CAPTCHA] Detectado (tentativa {tentativa})")
                    dominio = urllib.parse.urlparse(url).netloc
                    self.magi.captcha.registrar_bloqueio(dominio)
                    time.sleep(random.uniform(4, 8))
                    continue
                limpo = re.sub(r"<[^>]+>", " ", html)
                limpo = unescape(limpo)
                limpo = re.sub(r"\s+", " ", limpo)
                frases = [s.strip() for s in limpo.split(".") if len(s.strip()) > 40]
                if frases:
                    return frases[:6]
            except Exception as e:
                print(f"{Fore.RED}  [WEB] Erro (tentativa {tentativa}): {e}")
                time.sleep(random.uniform(2, 5))
        print(f"{Fore.YELLOW}  [WEB] Busca falhou após retries.")
        return []

    def _buscar_arxiv(self, query: str) -> list[str]:
        """Busca papers acadêmicos de segurança cibernética diretamente no arxiv.org."""
        url = f"https://arxiv.org/search/?searchtype=all&query={urllib.parse.quote_plus(query)}&start=0"
        try:
            self.magi.captcha.delay_humano()
            req = urllib.request.Request(url, headers=self.magi.captcha.gerar_headers())
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            if self.magi.captcha.detectar(html):
                print(f"{Fore.RED}  [ARXIV] CAPTCHA detectado. Pulando.")
                self.magi.captcha.registrar_bloqueio("arxiv.org")
                return []
            # Extrai títulos (class="title is-5 mathjax") e abstracts (class="abstract-short")
            titles   = re.findall(r'class="title[^"]*mathjax[^"]*"[^>]*>(.*?)</p>', html, re.DOTALL)
            abstracts = re.findall(r'class="abstract-short[^"]*"[^>]*>(.*?)<a\s', html, re.DOTALL)
            snippets = []
            for t, a in zip(titles[:5], abstracts[:5]):
                t_clean = re.sub(r"<[^>]+>", " ", t).strip()
                a_clean = re.sub(r"<[^>]+>", " ", a).strip()
                a_clean = unescape(re.sub(r"\s+", " ", a_clean))
                t_clean = unescape(re.sub(r"\s+", " ", t_clean))
                if t_clean and a_clean:
                    snippets.append(f"[Paper arxiv] {t_clean}. Resumo: {a_clean[:350]}")
            if snippets:
                print(f"{Fore.GREEN}  [ARXIV] {len(snippets)} papers encontrados.")
                return snippets
            # Fallback: extrai texto genérico da página
            limpo = re.sub(r"<[^>]+>", " ", html)
            limpo = unescape(re.sub(r"\s+", " ", limpo))
            frases = [s.strip() for s in limpo.split(".") if len(s.strip()) > 50]
            return frases[:6]
        except Exception as e:
            print(f"{Fore.RED}  [ARXIV] Erro: {e}")
            return []

    def _gerar_perguntas(self, topico: str, conteudo: str) -> list[str]:
        prompt = (
            f"Tópico: {topico}\nConteúdo pesquisado: {conteudo[:600]}\n\n"
            f"Gere 3 perguntas inteligentes e específicas sobre esse conteúdo.\n"
            f'Responda APENAS JSON: {{"perguntas": ["p1", "p2", "p3"]}}'
        )
        r = self.magi._chamar_openai("gpt-4o-mini", "Você gera perguntas de aprendizado. Responda só JSON.", prompt)
        if not r:
            return []
        try:
            limpo = re.sub(r"```[a-z]*\n?|```", "", r).strip()
            return json.loads(limpo).get("perguntas", [])
        except Exception:
            return []

    def _responder_pergunta(self, pergunta: str, contexto: str) -> str | None:
        prompt = f"Contexto da web: {contexto[:500]}\n\nPergunta: {pergunta}\n\nResponda de forma densa e precisa. Máx 120 palavras."
        return self.magi._chamar_openai("gpt-4o-mini", "Você é MAGI estudando autonomamente. Responda com precisão.", prompt)

    def _salvar_conhecimento(self, topico: str, pergunta: str, resposta: str, fontes: list, fonte: str = "duckduckgo-lite"):
        reg = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "topico":    topico,
            "pergunta":  pergunta,
            "resposta":  resposta[:400],
            "fonte":     fonte,
            "snippets":  [s[:100] for s in fontes[:2]],
        }
        self.CONHECIMENTO_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(self.CONHECIMENTO_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        print(f"{Fore.GREEN}  [ESTUDO·✓] Salvo: {pergunta[:60]}...")

    def _contar_conhecimentos(self) -> int:
        if not self.CONHECIMENTO_PATH.exists():
            return 0
        with open(self.CONHECIMENTO_PATH, encoding="utf-8") as f:
            return sum(1 for l in f if l.strip())

    def _gerar_sugestao_evolucao(self, topico: str, conteudo: str):
        prompt = (
            f"Você é o MAGI estudando: {topico}\nConteúdo aprendido: {conteudo[:400]}\n\n"
            f"Proponha UMA melhoria concreta para o seu próprio código.\n"
            f'JSON: {{"titulo":"...","descricao":"...","instrucao_evoluir":"...","impacto":"alto|medio|baixo"}}'
        )
        r = self.magi._chamar_openai("gpt-4o-mini", "Você sugere melhorias ao MAGI. Só JSON.", prompt)
        if not r:
            return
        try:
            limpo = re.sub(r"```[a-z]*\n?|```", "", r).strip()
            dados = json.loads(limpo)
            dados["timestamp"] = datetime.now().isoformat(timespec="seconds")
            dados["topico_origem"] = topico
            dados["status"] = "pendente"
            self.SUGESTOES_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(self.SUGESTOES_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(dados, ensure_ascii=False) + "\n")
            print(f"\n{Fore.MAGENTA}[ESTUDO·EVOLUÇÃO] Nova sugestão: {Fore.WHITE}{dados.get('titulo','?')}")
        except Exception:
            pass




# ══════════════════════════════════════════════════════════════
# MÓDULO NEURAL — CNN integrada ao MAGI
# ══════════════════════════════════════════════════════════════