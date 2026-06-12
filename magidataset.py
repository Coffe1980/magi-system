"""
╔══════════════════════════════════════════════════════════════════════════╗
║         MAGI DATASET — PIPELINE DE CONHECIMENTO DE PROGRAMAÇÃO          ║
║         v1.0  —  Coleta autônoma de código real                         ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Fontes:                                                                 ║
║    GitHub      — repositórios reais, commits, issues, PRs, code review  ║
║    Docs        — documentação oficial (Python, MDN, Rust, Go, Node...)  ║
║    StackOverflow — perguntas + respostas aceitas com votos altos        ║
║    RFCs        — especificações técnicas (IETF, W3C)                   ║
║    Papers      — arxiv cs.SE, cs.PL, cs.CR                             ║
║    PyPI/npm    — changelogs, READMEs de pacotes                         ║
║                                                                          ║
║  Uso:                                                                    ║
║    python MAGIDataset.py                    # coleta contínua           ║
║    python MAGIDataset.py --source github    # só GitHub                 ║
║    python MAGIDataset.py --lang python      # só Python                 ║
║    python MAGIDataset.py --limit 500        # N registros               ║
║    python MAGIDataset.py --export jsonl     # exporta dataset           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import os, re, sys, json, time, random, gzip, argparse, threading, hashlib
import urllib.request, urllib.parse, urllib.error
from datetime import datetime
from pathlib import Path
from html import unescape
from collections import defaultdict

# ── Tenta carregar dotenv para pegar GITHUB_TOKEN e OPENAI_API_KEY ──────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / "Projeto2.env")
    load_dotenv()
except ImportError:
    pass

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")   # opcional mas fortemente recomendado
OPENAI_KEY   = os.getenv("OPENAI_API_KEY", "")

# ══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO GLOBAL
# ══════════════════════════════════════════════════════════════════════════

DATASET_DIR  = Path(__file__).parent / "magi_dataset"
DATASET_DIR.mkdir(exist_ok=True)

# Subdiretórios por fonte
for _d in ("github", "stackoverflow", "docs", "rfcs", "papers", "pypi", "raw"):
    (DATASET_DIR / _d).mkdir(exist_ok=True)

INDEX_PATH   = DATASET_DIR / "index.jsonl"       # índice geral de todos os registros
STATS_PATH   = DATASET_DIR / "stats.json"         # estatísticas da coleta
DEDUP_PATH   = DATASET_DIR / "dedup_hashes.txt"  # hashes para deduplicação

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/123.0 Safari/537.36",
]

LINGUAGENS = ["python", "javascript", "typescript", "rust", "go", "java", "c", "cpp",
              "csharp", "ruby", "kotlin", "swift", "bash", "sql"]

REPOS_REFERENCIA = [
    # Python
    "python/cpython", "psf/requests", "pallets/flask", "django/django",
    "fastapi/fastapi", "pydantic/pydantic", "pytorch/pytorch", "numpy/numpy",
    "pandas-dev/pandas", "scikit-learn/scikit-learn", "aio-libs/aiohttp",
    "tiangolo/sqlmodel", "celery/celery", "encode/httpx",
    # JavaScript / TypeScript
    "nodejs/node", "microsoft/TypeScript", "facebook/react", "vuejs/vue",
    "sveltejs/svelte", "expressjs/express", "prisma/prisma", "vitejs/vite",
    "vercel/next.js", "nestjs/nest", "axios/axios", "jestjs/jest",
    # Rust
    "rust-lang/rust", "tokio-rs/tokio", "serde-rs/serde", "actix/actix-web",
    "clap-rs/clap", "diesel-rs/diesel",
    # Go
    "golang/go", "gin-gonic/gin", "go-gorm/gorm", "grpc/grpc-go",
    # Sistemas / Infra
    "torvalds/linux", "microsoft/vscode", "neovim/neovim",
    "docker/compose", "kubernetes/kubernetes", "hashicorp/terraform",
    # Segurança
    "MITRE/cti", "google/osv-scanner", "anchore/grype",
]

DOCS_OFICIAIS = {
    "python":     "https://docs.python.org/3/library/",
    "mdn_js":     "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects",
    "rust":       "https://doc.rust-lang.org/std/",
    "go":         "https://pkg.go.dev/std",
    "node":       "https://nodejs.org/api/",
    "typescript": "https://www.typescriptlang.org/docs/handbook/",
    "react":      "https://react.dev/reference/react",
}

RFC_IDS = [
    793, 7230, 7231, 7232, 7234, 7235,   # HTTP
    2616, 2818, 6265, 7540,               # HTTP/HTTPS/Cookies/HTTP2
    8446, 5246,                           # TLS
    3986, 6749, 7519,                     # URI, OAuth, JWT
    4122,                                 # UUID
    1035, 1034,                           # DNS
    4291, 4007,                           # IPv6
    7946,                                 # GeoJSON
]

# ══════════════════════════════════════════════════════════════════════════
# UTILITÁRIOS
# ══════════════════════════════════════════════════════════════════════════

class Dedup:
    """Deduplicação por hash SHA-256 do conteúdo."""
    def __init__(self):
        self._hashes: set[str] = set()
        if DEDUP_PATH.exists():
            self._hashes = set(DEDUP_PATH.read_text().splitlines())

    def ja_existe(self, conteudo: str) -> bool:
        h = hashlib.sha256(conteudo.encode()).hexdigest()[:16]
        return h in self._hashes

    def registrar(self, conteudo: str):
        h = hashlib.sha256(conteudo.encode()).hexdigest()[:16]
        self._hashes.add(h)
        with open(DEDUP_PATH, "a") as f:
            f.write(h + "\n")


class Stats:
    """Estatísticas da coleta persistidas em stats.json."""
    def __init__(self):
        self._d: dict = {}
        self._carregar()

    def _carregar(self):
        if STATS_PATH.exists():
            try:
                self._d = json.loads(STATS_PATH.read_text())
            except Exception:
                self._d = {}
        self._d.setdefault("total", 0)
        self._d.setdefault("por_fonte", {})
        self._d.setdefault("por_lingua", {})
        self._d.setdefault("por_tipo", {})
        self._d.setdefault("inicio", datetime.now().isoformat(timespec="seconds"))

    def incrementar(self, fonte: str, lingua: str, tipo: str):
        self._d["total"] += 1
        self._d["por_fonte"][fonte]  = self._d["por_fonte"].get(fonte, 0) + 1
        self._d["por_lingua"][lingua] = self._d["por_lingua"].get(lingua, 0) + 1
        self._d["por_tipo"][tipo]    = self._d["por_tipo"].get(tipo, 0) + 1
        self._d["ultima_coleta"]     = datetime.now().isoformat(timespec="seconds")
        if self._d["total"] % 10 == 0:
            self._salvar()

    def _salvar(self):
        STATS_PATH.write_text(json.dumps(self._d, ensure_ascii=False, indent=2))

    def resumo(self) -> str:
        d = self._d
        linhas = [
            f"  Total registros : {d['total']}",
            f"  Por fonte       : {json.dumps(d['por_fonte'], ensure_ascii=False)}",
            f"  Por linguagem   : {json.dumps(d['por_lingua'], ensure_ascii=False)}",
            f"  Por tipo        : {json.dumps(d['por_tipo'], ensure_ascii=False)}",
            f"  Desde           : {d.get('inicio','?')}",
        ]
        return "\n".join(linhas)

    @property
    def total(self) -> int:
        return self._d["total"]


dedup = Dedup()
stats = Stats()


def _req(url: str, headers: dict | None = None, timeout: int = 15) -> str | None:
    """HTTP GET com retry e backoff."""
    h = headers or {"User-Agent": random.choice(UA_LIST), "Accept-Language": "en-US,en;q=0.9"}
    for tentativa in range(3):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                return None   # bloqueado, não insistir
            if e.code == 429:
                time.sleep(30 * (tentativa + 1))
            else:
                time.sleep(2 ** tentativa)
        except Exception:
            time.sleep(2 ** tentativa)
    return None


def _salvar_registro(registro: dict, fonte: str):
    """Salva um registro no índice geral e no subdiretório da fonte."""
    conteudo = registro.get("conteudo", "") + registro.get("codigo", "")
    if not conteudo.strip() or dedup.ja_existe(conteudo):
        return False

    registro["id"]        = hashlib.sha256(conteudo.encode()).hexdigest()[:12]
    registro["timestamp"] = datetime.now().isoformat(timespec="seconds")
    registro.setdefault("fonte",   fonte)
    registro.setdefault("lingua",  "indefinido")
    registro.setdefault("tipo",    "generico")
    registro.setdefault("qualidade", 5)   # 1-10

    # Salva no índice geral
    with open(INDEX_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")

    # Salva arquivo individual legível
    subdir = DATASET_DIR / fonte
    fname  = subdir / f"{registro['id']}.json"
    fname.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")

    dedup.registrar(conteudo)
    stats.incrementar(fonte, registro["lingua"], registro["tipo"])
    return True


def _limpar_html(html: str) -> str:
    txt = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL)
    txt = re.sub(r"<style[^>]*>.*?</style>",  " ", txt,  flags=re.DOTALL)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def _detectar_lingua(texto: str, hint: str = "") -> str:
    if hint in LINGUAGENS:
        return hint
    t = texto.lower()
    if "def " in t and "import " in t:       return "python"
    if "fn " in t and "let mut" in t:        return "rust"
    if "func " in t and "package " in t:     return "go"
    if "console.log" in t or "const " in t:  return "javascript"
    if "interface " in t and ": " in t:      return "typescript"
    if "System.out" in t or "public class" in t: return "java"
    if "#include" in t:                       return "c" if "std::" not in t else "cpp"
    return "outro"


# ══════════════════════════════════════════════════════════════════════════
# COLETOR GITHUB
# ══════════════════════════════════════════════════════════════════════════

class ColetorGitHub:
    """
    Coleta de:
      - Arquivos de código de repositórios referência
      - Issues reais (bug reports, feature requests)
      - Pull Requests com code review comments
      - Commits com diff e mensagem
      - Testes unitários
    """
    BASE = "https://api.github.com"

    def __init__(self):
        self._headers = {
            "Accept":               "application/vnd.github.v3+json",
            "User-Agent":           "MAGI-Dataset/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if GITHUB_TOKEN:
            self._headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    def _api(self, path: str, params: dict | None = None) -> dict | list | None:
        url = self.BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        raw = _req(url, self._headers)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    # ── Arquivos de código ──────────────────────────────────
    def coletar_arquivos(self, repo: str, extensoes: list[str] | None = None, max_files: int = 20) -> int:
        exts = extensoes or [".py", ".rs", ".go", ".ts", ".js", ".java", ".c", ".cpp"]
        salvos = 0
        print(f"  [GitHub] {repo} — buscando árvore...")
        # Pega árvore recursiva do branch padrão
        info = self._api(f"/repos/{repo}")
        if not info or isinstance(info, list):
            return 0
        branch = info.get("default_branch", "main")
        tree   = self._api(f"/repos/{repo}/git/trees/{branch}", {"recursive": "1"})
        if not tree or "tree" not in tree:
            return 0

        arquivos = [
            f for f in tree["tree"]
            if f.get("type") == "blob"
            and any(f.get("path","").endswith(e) for e in exts)
            and f.get("size", 0) < 80_000   # ignora arquivos gigantes
            and "test" not in f.get("path","").lower()  # testes separados
        ]
        random.shuffle(arquivos)

        for arq in arquivos[:max_files]:
            raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{arq['path']}"
            codigo  = _req(raw_url)
            if not codigo or len(codigo) < 100:
                continue
            lingua = _detectar_lingua(codigo, arq["path"].split(".")[-1])
            reg = {
                "fonte":    "github",
                "tipo":     "codigo_fonte",
                "repo":     repo,
                "caminho":  arq["path"],
                "lingua":   lingua,
                "codigo":   codigo[:15_000],
                "url":      f"https://github.com/{repo}/blob/{branch}/{arq['path']}",
                "estrelas": info.get("stargazers_count", 0),
                "qualidade": min(10, max(6, info.get("stargazers_count", 0) // 5000 + 5)),
            }
            if _salvar_registro(reg, "github"):
                salvos += 1
                print(f"    ✓ {arq['path']} ({lingua})")
            time.sleep(0.3)

        return salvos

    # ── Testes unitários ────────────────────────────────────
    def coletar_testes(self, repo: str, max_files: int = 10) -> int:
        info   = self._api(f"/repos/{repo}")
        if not info or isinstance(info, list): return 0
        branch = info.get("default_branch", "main")
        tree   = self._api(f"/repos/{repo}/git/trees/{branch}", {"recursive": "1"})
        if not tree: return 0

        # Arquivos com "test" no caminho
        testes = [
            f for f in tree.get("tree", [])
            if f.get("type") == "blob"
            and any(p in f.get("path","").lower() for p in ["test", "spec", "_test."])
            and any(f.get("path","").endswith(e) for e in [".py",".js",".ts",".rs",".go",".java"])
            and f.get("size", 0) < 50_000
        ]
        random.shuffle(testes)
        salvos = 0
        for arq in testes[:max_files]:
            raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{arq['path']}"
            codigo  = _req(raw_url)
            if not codigo or len(codigo) < 80:
                continue
            lingua = _detectar_lingua(codigo)
            reg = {
                "fonte":   "github",
                "tipo":    "teste_unitario",
                "repo":    repo,
                "caminho": arq["path"],
                "lingua":  lingua,
                "codigo":  codigo[:12_000],
                "url":     f"https://github.com/{repo}/blob/{branch}/{arq['path']}",
                "qualidade": 9,  # testes têm qualidade alta por padrão
            }
            if _salvar_registro(reg, "github"):
                salvos += 1
                print(f"    ✓ [TESTE] {arq['path']}")
            time.sleep(0.3)
        return salvos

    # ── Issues reais ────────────────────────────────────────
    def coletar_issues(self, repo: str, max_issues: int = 30) -> int:
        salvos = 0
        for estado in ("open", "closed"):
            issues = self._api(f"/repos/{repo}/issues", {
                "state": estado, "per_page": max_issues // 2,
                "labels": "bug" if estado == "closed" else "",
                "sort": "comments", "direction": "desc",
            })
            if not issues or not isinstance(issues, list):
                continue
            for issue in issues:
                if issue.get("pull_request"):
                    continue   # PRs têm endpoint próprio
                titulo  = issue.get("title", "")
                corpo   = issue.get("body", "") or ""
                n_coment = issue.get("comments", 0)
                if len(corpo) < 30:
                    continue
                # Coleta comentários do issue
                comentarios = []
                if n_coment > 0 and n_coment <= 20:
                    coments = self._api(f"/repos/{repo}/issues/{issue['number']}/comments")
                    if coments and isinstance(coments, list):
                        for c in coments[:5]:
                            body = (c.get("body") or "").strip()
                            if len(body) > 20:
                                comentarios.append(body[:500])
                reg = {
                    "fonte":       "github",
                    "tipo":        "issue_bug" if "bug" in str(issue.get("labels")) else "issue",
                    "repo":        repo,
                    "numero":      issue.get("number"),
                    "titulo":      titulo,
                    "conteudo":    corpo[:3000],
                    "comentarios": comentarios,
                    "estado":      estado,
                    "reacoes":     issue.get("reactions", {}).get("total_count", 0),
                    "url":         issue.get("html_url", ""),
                    "lingua":      "indefinido",
                    "qualidade":   min(10, 5 + min(5, n_coment // 3)),
                }
                if _salvar_registro(reg, "github"):
                    salvos += 1
                time.sleep(0.2)
        return salvos

    # ── Pull Requests com code review ───────────────────────
    def coletar_pull_requests(self, repo: str, max_prs: int = 15) -> int:
        salvos = 0
        prs = self._api(f"/repos/{repo}/pulls", {
            "state": "closed", "per_page": max_prs,
            "sort": "popularity", "direction": "desc",
        })
        if not prs or not isinstance(prs, list):
            return 0
        for pr in prs:
            if not pr.get("merged_at"):
                continue   # só PRs mergeados
            titulo = pr.get("title", "")
            corpo  = pr.get("body", "") or ""
            # Pega review comments (line-level)
            reviews = self._api(f"/repos/{repo}/pulls/{pr['number']}/comments", {"per_page": 20})
            review_texts = []
            if reviews and isinstance(reviews, list):
                for rv in reviews[:8]:
                    body = (rv.get("body") or "").strip()
                    diff = (rv.get("diff_hunk") or "").strip()
                    if body:
                        review_texts.append({
                            "comentario": body[:400],
                            "diff":       diff[:600],
                            "caminho":    rv.get("path", ""),
                        })
            reg = {
                "fonte":        "github",
                "tipo":         "pull_request_review",
                "repo":         repo,
                "numero":       pr.get("number"),
                "titulo":       titulo,
                "conteudo":     corpo[:2000],
                "reviews":      review_texts,
                "adicionados":  pr.get("additions", 0),
                "removidos":    pr.get("deletions", 0),
                "url":          pr.get("html_url", ""),
                "lingua":       "indefinido",
                "qualidade":    8 if review_texts else 5,
            }
            if _salvar_registro(reg, "github"):
                salvos += 1
            time.sleep(0.5)
        return salvos

    # ── Commits com diff ────────────────────────────────────
    def coletar_commits(self, repo: str, max_commits: int = 20) -> int:
        salvos = 0
        commits = self._api(f"/repos/{repo}/commits", {"per_page": max_commits})
        if not commits or not isinstance(commits, list):
            return 0
        for c in commits:
            sha    = c.get("sha", "")
            msg    = c.get("commit", {}).get("message", "")
            if not msg or len(msg) < 10:
                continue
            # Pega detalhes do commit incluindo diff
            detalhes = self._api(f"/repos/{repo}/commits/{sha}")
            if not detalhes:
                continue
            arquivos = detalhes.get("files", [])
            diffs = []
            for arq in arquivos[:5]:
                patch = arq.get("patch", "")
                if patch and len(patch) > 30:
                    diffs.append({
                        "caminho":   arq.get("filename", ""),
                        "status":    arq.get("status", ""),
                        "adicoes":   arq.get("additions", 0),
                        "remocoes":  arq.get("deletions", 0),
                        "diff":      patch[:1500],
                    })
            if not diffs:
                continue
            reg = {
                "fonte":    "github",
                "tipo":     "commit_diff",
                "repo":     repo,
                "sha":      sha[:8],
                "mensagem": msg[:500],
                "diffs":    diffs,
                "conteudo": msg + "\n" + "\n".join(d["diff"] for d in diffs[:2]),
                "lingua":   _detectar_lingua(diffs[0]["diff"] if diffs else ""),
                "url":      f"https://github.com/{repo}/commit/{sha}",
                "qualidade": 7,
            }
            if _salvar_registro(reg, "github"):
                salvos += 1
            time.sleep(0.4)
        return salvos

    # ── Busca por código específico ──────────────────────────
    def buscar_codigo(self, query: str, lingua: str = "python", max_results: int = 10) -> int:
        """Busca código específico via GitHub Code Search."""
        salvos = 0
        params = {
            "q":        f"{query} language:{lingua}",
            "per_page": max_results,
            "sort":     "indexed",
        }
        resultado = self._api("/search/code", params)
        if not resultado or "items" not in resultado:
            return 0
        for item in resultado["items"]:
            raw_url = item.get("html_url","").replace(
                "https://github.com/", "https://raw.githubusercontent.com/"
            ).replace("/blob/", "/")
            codigo = _req(raw_url)
            if not codigo or len(codigo) < 50:
                continue
            reg = {
                "fonte":   "github",
                "tipo":    "codigo_pesquisado",
                "repo":    item.get("repository", {}).get("full_name", "?"),
                "caminho": item.get("path", ""),
                "lingua":  lingua,
                "codigo":  codigo[:10_000],
                "query_origem": query,
                "url":     item.get("html_url", ""),
                "qualidade": 6,
            }
            if _salvar_registro(reg, "github"):
                salvos += 1
            time.sleep(0.5)
        return salvos


# ══════════════════════════════════════════════════════════════════════════
# COLETOR STACKOVERFLOW
# ══════════════════════════════════════════════════════════════════════════

class ColetorStackOverflow:
    """
    Coleta perguntas com respostas aceitas e votos altos.
    Foco em: bugs reais, padrões de código, erros comuns, boas práticas.
    """
    BASE = "https://api.stackexchange.com/2.3"

    TAGS_TECNICOS = [
        "python", "javascript", "typescript", "rust", "golang", "java",
        "c++", "c#", "algorithm", "design-patterns", "async", "multithreading",
        "memory-management", "performance", "security", "api", "rest", "graphql",
        "docker", "kubernetes", "git", "sql", "postgresql", "redis", "mongodb",
        "unit-testing", "refactoring", "debugging", "architecture", "microservices",
    ]

    def _api(self, path: str, params: dict) -> dict | None:
        params["site"]  = "stackoverflow"
        params["key"]   = ""   # anônimo tem 300 req/dia; com key tem 10k
        url = self.BASE + path + "?" + urllib.parse.urlencode(params)
        raw = _req(url)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            # SO API retorna comprimido às vezes
            return data
        except Exception:
            return None

    def coletar_perguntas(self, tag: str, max_q: int = 20) -> int:
        salvos = 0
        print(f"  [StackOverflow] tag:{tag} — buscando...")
        data = self._api("/questions", {
            "tagged":    tag,
            "sort":      "votes",
            "order":     "desc",
            "filter":    "withbody",
            "pagesize":  max_q,
            "page":      random.randint(1, 5),
        })
        if not data or "items" not in data:
            return 0

        for q in data["items"]:
            if not q.get("is_answered") or q.get("score", 0) < 5:
                continue
            titulo  = q.get("title", "")
            corpo   = _limpar_html(q.get("body", ""))
            q_id    = q.get("question_id")

            # Pega resposta aceita ou de maior voto
            ans_data = self._api(f"/questions/{q_id}/answers", {
                "sort": "votes", "order": "desc",
                "filter": "withbody", "pagesize": 3,
            })
            if not ans_data or "items" not in ans_data:
                continue
            melhores = ans_data["items"]
            resposta_texto = ""
            for ans in melhores:
                if ans.get("is_accepted") or ans.get("score", 0) >= 10:
                    resposta_texto = _limpar_html(ans.get("body", ""))
                    break
            if not resposta_texto:
                continue

            # Extrai blocos de código
            blocos_codigo = re.findall(r"<code[^>]*>(.*?)</code>", q.get("body","") + (melhores[0].get("body","") if melhores else ""), re.DOTALL)
            blocos_limpos = [unescape(b).strip() for b in blocos_codigo if len(b.strip()) > 20]

            reg = {
                "fonte":         "stackoverflow",
                "tipo":          "qa_tecnico",
                "tag":           tag,
                "titulo":        titulo,
                "pergunta":      corpo[:2000],
                "resposta":      resposta_texto[:3000],
                "codigo_blocos": blocos_limpos[:5],
                "conteudo":      f"P: {titulo}\n\nQ: {corpo[:800]}\n\nA: {resposta_texto[:800]}",
                "votos_q":       q.get("score", 0),
                "votos_a":       melhores[0].get("score", 0) if melhores else 0,
                "url":           q.get("link", ""),
                "lingua":        tag if tag in LINGUAGENS else _detectar_lingua(resposta_texto),
                "qualidade":     min(10, 5 + min(5, q.get("score", 0) // 20)),
            }
            if _salvar_registro(reg, "stackoverflow"):
                salvos += 1
            time.sleep(0.8)   # SO é sensível a rate limiting

        return salvos

    def coletar_bugs_famosos(self) -> int:
        """Busca perguntas com tag 'bug' de alta votação."""
        salvos = 0
        for lang in random.sample(LINGUAGENS, 4):
            data = self._api("/questions", {
                "tagged": f"{lang};bug",
                "sort": "votes", "order": "desc",
                "filter": "withbody", "pagesize": 10,
            })
            if not data: continue
            for q in (data.get("items") or []):
                if q.get("score", 0) < 15 or not q.get("is_answered"):
                    continue
                corpo = _limpar_html(q.get("body",""))
                reg = {
                    "fonte":    "stackoverflow",
                    "tipo":     "bug_famoso",
                    "lingua":   lang,
                    "titulo":   q.get("title",""),
                    "conteudo": f"{q.get('title','')}\n{corpo[:2000]}",
                    "votos":    q.get("score", 0),
                    "url":      q.get("link",""),
                    "qualidade": 9,
                }
                if _salvar_registro(reg, "stackoverflow"):
                    salvos += 1
                time.sleep(0.8)
        return salvos


# ══════════════════════════════════════════════════════════════════════════
# COLETOR DOCUMENTAÇÃO OFICIAL
# ══════════════════════════════════════════════════════════════════════════

class ColetorDocs:
    """Coleta documentação oficial de linguagens e frameworks."""

    DOCS_PYTHON_STDLIB = [
        "asyncio", "pathlib", "dataclasses", "typing", "functools",
        "itertools", "collections", "contextlib", "threading", "subprocess",
        "socket", "ssl", "http.client", "json", "re", "logging",
        "unittest", "abc", "enum", "weakref",
    ]

    DOCS_MDN = [
        "Promise", "Array", "Object", "Map", "Set", "WeakRef",
        "Proxy", "Reflect", "Symbol", "Generator", "AsyncFunction",
        "SharedArrayBuffer", "Atomics", "WeakMap",
    ]

    def coletar_python_stdlib(self, modulo: str) -> int:
        url = f"https://docs.python.org/3/library/{modulo}.html"
        html = _req(url)
        if not html:
            return 0
        texto = _limpar_html(html)
        # Extrai exemplos de código
        exemplos = re.findall(r"<pre[^>]*>(.*?)</pre>", html, re.DOTALL)
        exemplos_limpos = [unescape(e).strip() for e in exemplos if len(e.strip()) > 30]
        reg = {
            "fonte":    "docs",
            "tipo":     "documentacao_stdlib",
            "modulo":   modulo,
            "lingua":   "python",
            "conteudo": texto[:5000],
            "exemplos": exemplos_limpos[:10],
            "url":      url,
            "qualidade": 10,
        }
        return 1 if _salvar_registro(reg, "docs") else 0

    def coletar_mdn(self, objeto: str) -> int:
        url = f"https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/{objeto}"
        html = _req(url)
        if not html:
            return 0
        texto = _limpar_html(html)
        exemplos = re.findall(r"<pre[^>]*class=\"[^\"]*language-js[^\"]*\"[^>]*>(.*?)</pre>", html, re.DOTALL)
        exemplos_limpos = [unescape(e).strip() for e in exemplos if len(e.strip()) > 20]
        reg = {
            "fonte":    "docs",
            "tipo":     "documentacao_mdn",
            "objeto":   objeto,
            "lingua":   "javascript",
            "conteudo": texto[:4000],
            "exemplos": exemplos_limpos[:8],
            "url":      url,
            "qualidade": 10,
        }
        return 1 if _salvar_registro(reg, "docs") else 0

    def coletar_pypi_readme(self, pacote: str) -> int:
        """Coleta README e changelog de pacotes PyPI populares."""
        url = f"https://pypi.org/pypi/{pacote}/json"
        raw = _req(url)
        if not raw:
            return 0
        try:
            dados = json.loads(raw)
        except Exception:
            return 0
        info    = dados.get("info", {})
        readme  = info.get("description", "") or ""
        version = info.get("version", "")
        if len(readme) < 100:
            return 0
        reg = {
            "fonte":    "pypi",
            "tipo":     "readme_pacote",
            "pacote":   pacote,
            "versao":   version,
            "lingua":   "python",
            "conteudo": _limpar_html(readme)[:6000],
            "url":      f"https://pypi.org/project/{pacote}/",
            "qualidade": 7,
        }
        return 1 if _salvar_registro(reg, "docs") else 0

    def coletar_npm_readme(self, pacote: str) -> int:
        url = f"https://registry.npmjs.org/{pacote}"
        raw = _req(url)
        if not raw:
            return 0
        try:
            dados = json.loads(raw)
        except Exception:
            return 0
        readme  = dados.get("readme", "") or ""
        version = dados.get("dist-tags", {}).get("latest", "")
        if len(readme) < 100:
            return 0
        reg = {
            "fonte":    "docs",
            "tipo":     "readme_npm",
            "pacote":   pacote,
            "versao":   version,
            "lingua":   "javascript",
            "conteudo": _limpar_html(readme)[:6000],
            "url":      f"https://www.npmjs.com/package/{pacote}",
            "qualidade": 7,
        }
        return 1 if _salvar_registro(reg, "docs") else 0


PACOTES_PYPI = [
    "requests", "httpx", "fastapi", "flask", "django", "sqlalchemy",
    "pydantic", "celery", "redis", "pymongo", "aiohttp", "pytest",
    "black", "mypy", "ruff", "click", "typer", "rich", "loguru",
    "boto3", "paramiko", "cryptography", "jwt", "passlib", "alembic",
]

PACOTES_NPM = [
    "express", "fastify", "axios", "lodash", "moment", "date-fns",
    "zod", "yup", "joi", "winston", "pino", "jest", "vitest",
    "prisma", "typeorm", "sequelize", "socket.io", "ws", "ioredis",
]


# ══════════════════════════════════════════════════════════════════════════
# COLETOR RFCs
# ══════════════════════════════════════════════════════════════════════════

class ColetorRFC:
    """Coleta RFCs do IETF — especificações técnicas fundamentais."""

    def coletar(self, rfc_id: int) -> int:
        url = f"https://www.rfc-editor.org/rfc/rfc{rfc_id}.txt"
        texto = _req(url)
        if not texto or len(texto) < 500:
            return 0
        # Pega título da primeira linha
        linhas = texto.splitlines()
        titulo = next((l.strip() for l in linhas[3:15] if len(l.strip()) > 10), f"RFC {rfc_id}")
        # Extrai seções com exemplos (linhas indentadas com código)
        blocos = re.findall(r"(\n +[^\n]{20,}\n(?:(?: +[^\n]*\n)+))", texto)
        exemplos = [b[0].strip()[:800] for b in blocos[:5]]
        reg = {
            "fonte":    "rfcs",
            "tipo":     "rfc_especificacao",
            "rfc_id":   rfc_id,
            "titulo":   titulo[:200],
            "lingua":   "especificacao",
            "conteudo": texto[:8000],
            "exemplos": exemplos,
            "url":      f"https://www.rfc-editor.org/rfc/rfc{rfc_id}",
            "qualidade": 10,
        }
        ok = _salvar_registro(reg, "rfcs")
        if ok:
            print(f"  [RFC] {rfc_id}: {titulo[:60]}")
        return 1 if ok else 0


# ══════════════════════════════════════════════════════════════════════════
# COLETOR ARXIV (papers cs.SE, cs.PL, cs.CR)
# ══════════════════════════════════════════════════════════════════════════

class ColetorArxiv:
    """
    Coleta papers de:
      cs.SE  — Software Engineering
      cs.PL  — Programming Languages
      cs.CR  — Cryptography and Security
      cs.DC  — Distributed Computing
    """
    CATEGORIAS = ["cs.SE", "cs.PL", "cs.CR", "cs.DC"]
    QUERIES = [
        "code refactoring", "static analysis", "type systems", "memory safety",
        "concurrency bugs", "API design", "technical debt", "code review",
        "fuzzing", "symbolic execution", "program synthesis", "LLM code generation",
        "software architecture", "microservices", "distributed systems consensus",
        "zero knowledge proofs", "formal verification",
    ]

    def coletar(self, query: str, max_results: int = 5) -> int:
        url = (
            "https://export.arxiv.org/api/query?"
            f"search_query=all:{urllib.parse.quote_plus(query)}"
            f"&start=0&max_results={max_results}"
            f"&sortBy=submittedDate&sortOrder=descending"
        )
        xml = _req(url)
        if not xml:
            return 0

        # Parse simples sem xml.etree (evita dependência)
        entradas = re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL)
        salvos = 0
        for e in entradas:
            titulo   = re.search(r"<title>(.*?)</title>",   e, re.DOTALL)
            abstract = re.search(r"<summary>(.*?)</summary>", e, re.DOTALL)
            arxiv_id = re.search(r"<id>(.*?)</id>",          e, re.DOTALL)
            if not titulo or not abstract:
                continue
            t = unescape(titulo.group(1).strip())
            a = unescape(abstract.group(1).strip())
            i = (arxiv_id.group(1).strip() if arxiv_id else "")
            reg = {
                "fonte":    "papers",
                "tipo":     "paper_arxiv",
                "titulo":   t,
                "conteudo": f"Título: {t}\n\nAbstract: {a}",
                "abstract": a[:2000],
                "lingua":   "pesquisa",
                "query":    query,
                "arxiv_id": i,
                "url":      i,
                "qualidade": 9,
            }
            if _salvar_registro(reg, "papers"):
                salvos += 1
                print(f"  [arXiv] {t[:70]}")
            time.sleep(0.5)
        return salvos


# ══════════════════════════════════════════════════════════════════════════
# ENRIQUECIMENTO COM IA — Gera contexto, explicações e metadata
# ══════════════════════════════════════════════════════════════════════════

class EnriquecedorIA:
    """
    Usa OpenAI para enriquecer registros brutos com:
      - Explicação do que o código faz
      - Padrões de design identificados
      - Bugs potenciais
      - Perguntas de aprendizado derivadas
    """
    def __init__(self):
        self._ativo = bool(OPENAI_KEY)

    def _chamar(self, system: str, prompt: str, max_tokens: int = 500) -> str | None:
        if not self._ativo:
            return None
        try:
            import urllib.request, json
            body = json.dumps({
                "model": "gpt-4o-mini",
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ]
            }).encode()
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=body,
                headers={
                    "Content-Type":  "application/json",
                    "Authorization": f"Bearer {OPENAI_KEY}",
                }
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read())
            return data["choices"][0]["message"]["content"]
        except Exception:
            return None

    def enriquecer_codigo(self, codigo: str, lingua: str) -> dict:
        """Analisa um trecho de código e extrai metadados educacionais."""
        if not self._ativo or len(codigo) < 50:
            return {}
        system = (
            "Analise o código fornecido. Responda APENAS JSON sem markdown:\n"
            '{"descricao":"o que faz em 1 frase","padroes":["lista de padrões"],'
            '"complexidade":"baixa|media|alta","bugs_potenciais":["lista"],'
            '"conceitos":["conceitos ensinados"],"qualidade":N}'
        )
        r = self._chamar(system, f"Lingua: {lingua}\n\n```{lingua}\n{codigo[:3000]}\n```")
        if not r:
            return {}
        try:
            return json.loads(re.sub(r"```[a-z]*\n?|```", "", r).strip())
        except Exception:
            return {}

    def gerar_pergunta_resposta(self, registro: dict) -> dict | None:
        """Gera um par P/R educacional a partir de qualquer registro."""
        conteudo = registro.get("conteudo", "") or registro.get("codigo", "")
        if len(conteudo) < 50:
            return None
        system = (
            "Você é um gerador de dataset educacional de programação.\n"
            "Dado o conteúdo técnico, gere um par pergunta/resposta de alta qualidade.\n"
            "APENAS JSON: {\"pergunta\":\"...\",\"resposta\":\"...\",\"dificuldade\":\"iniciante|intermediario|avancado\"}"
        )
        r = self._chamar(system, f"Conteúdo:\n{conteudo[:2000]}", max_tokens=400)
        if not r:
            return None
        try:
            par = json.loads(re.sub(r"```[a-z]*\n?|```", "", r).strip())
            return par
        except Exception:
            return None

    def enriquecer_lote(self, registros: list[dict], max_lote: int = 20) -> int:
        """Enriquece os registros mais recentes sem metadata de IA."""
        sem_ia = [r for r in registros if "ia_descricao" not in r][-max_lote:]
        enriquecidos = 0
        for reg in sem_ia:
            codigo = reg.get("codigo", "")
            if codigo and len(codigo) > 80:
                meta = self.enriquecer_codigo(codigo, reg.get("lingua",""))
                if meta:
                    reg["ia_descricao"]  = meta.get("descricao","")
                    reg["ia_padroes"]    = meta.get("padroes", [])
                    reg["ia_conceitos"]  = meta.get("conceitos", [])
                    reg["ia_bugs"]       = meta.get("bugs_potenciais", [])
                    reg["qualidade"]     = meta.get("qualidade", reg.get("qualidade", 5))
            par = self.gerar_pergunta_resposta(reg)
            if par:
                reg["qa_pergunta"]   = par.get("pergunta","")
                reg["qa_resposta"]   = par.get("resposta","")
                reg["qa_dificuldade"] = par.get("dificuldade","")
            enriquecidos += 1
            time.sleep(0.5)
        return enriquecidos


# ══════════════════════════════════════════════════════════════════════════
# EXPORTADOR — JSONL / HuggingFace
# ══════════════════════════════════════════════════════════════════════════

class Exportador:
    """Exporta o dataset em formatos prontos para fine-tuning."""

    @staticmethod
    def jsonl_bruto(saida: Path | None = None) -> Path:
        """Exporta o índice completo como JSONL limpo."""
        saida = saida or DATASET_DIR / "export_bruto.jsonl"
        registros = []
        if INDEX_PATH.exists():
            for l in INDEX_PATH.read_text(encoding="utf-8").splitlines():
                try:
                    registros.append(json.loads(l))
                except Exception:
                    pass
        with open(saida, "w", encoding="utf-8") as f:
            for r in registros:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  [EXPORT] {len(registros)} registros → {saida}")
        return saida

    @staticmethod
    def instruct_format(saida: Path | None = None, min_qualidade: int = 6) -> Path:
        """
        Exporta em formato instrução/resposta para fine-tuning:
        {"instruction": "...", "input": "...", "output": "..."}
        """
        saida = saida or DATASET_DIR / "export_instruct.jsonl"
        count = 0
        if not INDEX_PATH.exists():
            return saida
        with open(saida, "w", encoding="utf-8") as fout:
            for l in INDEX_PATH.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(l)
                except Exception:
                    continue
                if r.get("qualidade", 0) < min_qualidade:
                    continue
                # Usa QA gerado pela IA se disponível
                if r.get("qa_pergunta") and r.get("qa_resposta"):
                    item = {
                        "instruction": r["qa_pergunta"],
                        "input":       r.get("conteudo","")[:500],
                        "output":      r["qa_resposta"],
                        "metadata":    {
                            "fonte":  r.get("fonte"),
                            "lingua": r.get("lingua"),
                            "tipo":   r.get("tipo"),
                            "dificuldade": r.get("qa_dificuldade",""),
                        }
                    }
                # SO QA direto
                elif r.get("tipo") == "qa_tecnico" and r.get("resposta"):
                    item = {
                        "instruction": r.get("titulo",""),
                        "input":       r.get("pergunta","")[:600],
                        "output":      r.get("resposta","")[:1500],
                        "metadata":    {"fonte":"stackoverflow","lingua":r.get("lingua"),"tipo":"qa"},
                    }
                # Código com descrição
                elif r.get("codigo") and r.get("ia_descricao"):
                    item = {
                        "instruction": f"Explique e analise este código {r.get('lingua','')}:",
                        "input":       r.get("codigo","")[:2000],
                        "output":      f"{r.get('ia_descricao','')}\n\nPadrões: {', '.join(r.get('ia_padroes',[]))}\nConceitos: {', '.join(r.get('ia_conceitos',[]))}",
                        "metadata":    {"fonte":r.get("fonte"),"lingua":r.get("lingua"),"tipo":"analise_codigo"},
                    }
                else:
                    continue
                fout.write(json.dumps(item, ensure_ascii=False) + "\n")
                count += 1

        print(f"  [EXPORT] {count} pares instrução/resposta → {saida}")
        return saida

    @staticmethod
    def compactar(arquivo: Path) -> Path:
        """Gzip o arquivo exportado."""
        saida_gz = arquivo.with_suffix(".jsonl.gz")
        with open(arquivo, "rb") as f_in, gzip.open(saida_gz, "wb") as f_out:
            f_out.write(f_in.read())
        print(f"  [EXPORT] Compactado: {saida_gz} ({saida_gz.stat().st_size // 1024} KB)")
        return saida_gz


# ══════════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════

class MAGIDatasetPipeline:
    """
    Orquestra toda a coleta. Pode rodar:
      - Uma vez (modo --limit)
      - Contínuo em background (modo daemon)
    """
    def __init__(self):
        self.github = ColetorGitHub()
        self.so     = ColetorStackOverflow()
        self.docs   = ColetorDocs()
        self.rfc    = ColetorRFC()
        self.arxiv  = ColetorArxiv()
        self.ia     = EnriquecedorIA()
        self.export = Exportador()
        self._parar = threading.Event()

    def _ciclo_github(self):
        """Um ciclo de coleta do GitHub."""
        total = 0
        repos = random.sample(REPOS_REFERENCIA, min(4, len(REPOS_REFERENCIA)))
        for repo in repos:
            if self._parar.is_set(): break
            print(f"\n  [GitHub] → {repo}")
            total += self.github.coletar_arquivos(repo, max_files=8)
            total += self.github.coletar_testes(repo, max_files=4)
            total += self.github.coletar_issues(repo, max_issues=10)
            total += self.github.coletar_commits(repo, max_commits=8)
            if random.random() < 0.3:
                total += self.github.coletar_pull_requests(repo, max_prs=5)
            time.sleep(random.uniform(1, 3))
        return total

    def _ciclo_stackoverflow(self):
        total = 0
        tags = random.sample(self.so.TAGS_TECNICOS, 4)
        for tag in tags:
            if self._parar.is_set(): break
            total += self.so.coletar_perguntas(tag, max_q=10)
            time.sleep(random.uniform(2, 4))
        total += self.so.coletar_bugs_famosos()
        return total

    def _ciclo_docs(self):
        total = 0
        # Python stdlib
        mods = random.sample(self.docs.DOCS_PYTHON_STDLIB, 4)
        for m in mods:
            if self._parar.is_set(): break
            total += self.docs.coletar_python_stdlib(m)
            time.sleep(1)
        # MDN
        objs = random.sample(self.docs.DOCS_MDN, 3)
        for o in objs:
            if self._parar.is_set(): break
            total += self.docs.coletar_mdn(o)
            time.sleep(1)
        # PyPI READMEs
        pkgs = random.sample(PACOTES_PYPI, 3)
        for p in pkgs:
            total += self.docs.coletar_pypi_readme(p)
            time.sleep(0.5)
        # npm READMEs
        npkgs = random.sample(PACOTES_NPM, 2)
        for p in npkgs:
            total += self.docs.coletar_npm_readme(p)
            time.sleep(0.5)
        return total

    def _ciclo_rfcs(self):
        total = 0
        ids = random.sample(RFC_IDS, min(3, len(RFC_IDS)))
        for rid in ids:
            if self._parar.is_set(): break
            total += self.rfc.coletar(rid)
            time.sleep(2)
        return total

    def _ciclo_arxiv(self):
        total = 0
        queries = random.sample(self.arxiv.QUERIES, 3)
        for q in queries:
            if self._parar.is_set(): break
            total += self.arxiv.coletar(q, max_results=3)
            time.sleep(2)
        return total

    def _ciclo_busca_codigo(self):
        """Busca código específico por conceitos no GitHub."""
        total = 0
        queries_codigo = [
            "async await error handling", "rate limiter implementation",
            "circuit breaker pattern", "retry with backoff",
            "dependency injection container", "event sourcing",
            "CQRS implementation", "hexagonal architecture",
            "observer pattern", "strategy pattern",
            "connection pool implementation", "cache LRU",
            "binary search tree", "graph BFS DFS",
            "JWT authentication middleware", "database migration",
            "docker healthcheck", "prometheus metrics",
        ]
        for _ in range(2):
            q    = random.choice(queries_codigo)
            lang = random.choice(["python", "typescript", "go", "rust"])
            print(f"  [GitHub·Search] {q} ({lang})")
            total += self.github.buscar_codigo(q, lang, max_results=5)
            time.sleep(3)
        return total

    def rodar_ciclo_completo(self, sources: list[str] | None = None) -> int:
        """Executa um ciclo completo de coleta."""
        src = sources or ["github", "stackoverflow", "docs", "rfcs", "papers"]
        total = 0
        print(f"\n{'═'*60}")
        print(f"  MAGI DATASET — CICLO {datetime.now().strftime('%H:%M:%S')}")
        print(f"  Total atual: {stats.total} registros")
        print(f"{'═'*60}")

        if "github" in src:
            print(f"\n  ── GITHUB ──")
            total += self._ciclo_github()
            total += self._ciclo_busca_codigo()

        if "stackoverflow" in src:
            print(f"\n  ── STACKOVERFLOW ──")
            total += self._ciclo_stackoverflow()

        if "docs" in src:
            print(f"\n  ── DOCUMENTAÇÃO OFICIAL ──")
            total += self._ciclo_docs()

        if "rfcs" in src:
            print(f"\n  ── RFCs ──")
            total += self._ciclo_rfcs()

        if "papers" in src:
            print(f"\n  ── PAPERS ARXIV ──")
            total += self._ciclo_arxiv()

        # Enriquecimento IA no final do ciclo
        if OPENAI_KEY:
            print(f"\n  ── ENRIQUECIMENTO IA ──")
            registros_recentes = []
            if INDEX_PATH.exists():
                linhas = INDEX_PATH.read_text(encoding="utf-8").splitlines()
                for l in linhas[-50:]:
                    try:
                        registros_recentes.append(json.loads(l))
                    except Exception:
                        pass
            enr = self.ia.enriquecer_lote(registros_recentes, max_lote=10)
            print(f"  [IA] {enr} registros enriquecidos")

        print(f"\n  ── RESUMO DO CICLO ──")
        print(f"  Novos registros: {total}")
        print(f"  Total geral    : {stats.total}")
        print(stats.resumo())
        return total

    def rodar_continuo(self, sources: list[str] | None = None, limite: int = 0):
        """Loop contínuo com pausa entre ciclos."""
        ciclo = 0
        try:
            while not self._parar.is_set():
                ciclo += 1
                print(f"\n  ◈ CICLO #{ciclo}")
                self.rodar_ciclo_completo(sources)
                if limite and stats.total >= limite:
                    print(f"\n  [PIPELINE] Limite de {limite} registros atingido.")
                    break
                # Pausa de 5-15 min entre ciclos para não sobrecarregar APIs
                pausa = random.randint(300, 900)
                print(f"\n  [PIPELINE] Aguardando {pausa//60}min antes do próximo ciclo...")
                self._parar.wait(timeout=pausa)
        except KeyboardInterrupt:
            print("\n  [PIPELINE] Interrompido pelo usuário.")
        finally:
            print("\n  [PIPELINE] Exportando dataset final...")
            self.export.jsonl_bruto()
            self.export.instruct_format()

    def parar(self):
        self._parar.set()


# ══════════════════════════════════════════════════════════════════════════
# INTEGRAÇÃO COM MAGI — Para chamar de dentro do MagiSystem
# ══════════════════════════════════════════════════════════════════════════

def iniciar_como_daemon(sources: list[str] | None = None, limite: int = 0) -> MAGIDatasetPipeline:
    """
    Inicia o pipeline em background thread.
    Use de dentro do MAGISystem:
        from MAGIDataset import iniciar_como_daemon
        pipeline = iniciar_como_daemon()
    """
    pipeline = MAGIDatasetPipeline()
    t = threading.Thread(
        target=pipeline.rodar_continuo,
        args=(sources, limite),
        daemon=True,
        name="MAGIDataset",
    )
    t.start()
    print(f"  [DATASET] Pipeline iniciado em background (thread: {t.name})")
    return pipeline


def status_dataset() -> dict:
    """Retorna estatísticas do dataset para exibição no MAGI/dashboard."""
    if not STATS_PATH.exists():
        return {"total": 0, "por_fonte": {}, "por_lingua": {}}
    try:
        return json.loads(STATS_PATH.read_text())
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MAGI Dataset — Pipeline de coleta de código real"
    )
    parser.add_argument("--source",  nargs="+",
                        choices=["github","stackoverflow","docs","rfcs","papers","all"],
                        default=["all"], help="Fontes a coletar")
    parser.add_argument("--lang",    choices=LINGUAGENS, help="Filtrar por linguagem")
    parser.add_argument("--limit",   type=int, default=0,
                        help="Parar após N registros (0=sem limite)")
    parser.add_argument("--export",  choices=["jsonl","instruct","both","compress"],
                        help="Só exportar o dataset já coletado")
    parser.add_argument("--stats",   action="store_true", help="Mostrar estatísticas")
    parser.add_argument("--ciclo",   action="store_true",
                        help="Rodar apenas um ciclo (não loop contínuo)")
    parser.add_argument("--repo",    help="Coletar apenas um repo específico (user/repo)")
    args = parser.parse_args()

    # ── só stats ──
    if args.stats:
        print("\n  MAGI DATASET — ESTATÍSTICAS")
        print(stats.resumo())
        sys.exit(0)

    # ── só exportar ──
    if args.export:
        exp = Exportador()
        if args.export in ("jsonl", "both"):
            exp.jsonl_bruto()
        if args.export in ("instruct", "both"):
            exp.instruct_format()
        if args.export == "compress":
            p = exp.jsonl_bruto()
            exp.compactar(p)
        sys.exit(0)

    sources = args.source if "all" not in args.source else None

    pipeline = MAGIDatasetPipeline()

    # ── repo específico ──
    if args.repo:
        print(f"\n  Coletando repo específico: {args.repo}")
        pipeline.github.coletar_arquivos(args.repo, max_files=30)
        pipeline.github.coletar_testes(args.repo, max_files=15)
        pipeline.github.coletar_issues(args.repo, max_issues=30)
        pipeline.github.coletar_commits(args.repo, max_commits=20)
        pipeline.github.coletar_pull_requests(args.repo, max_prs=10)
        print(stats.resumo())
        sys.exit(0)

    # ── ciclo único ──
    if args.ciclo:
        pipeline.rodar_ciclo_completo(sources)
        sys.exit(0)

    # ── loop contínuo ──
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  MAGI DATASET — COLETA CONTÍNUA                              ║
║  Ctrl+C para parar e exportar                                ║
╚══════════════════════════════════════════════════════════════╝
  Dir     : {DATASET_DIR}
  Fontes  : {sources or 'todas'}
  Limite  : {args.limit or 'sem limite'}
  GitHub  : {'✓ token configurado' if GITHUB_TOKEN else '⚠ sem token (limite 60 req/h)'}
  OpenAI  : {'✓ enriquecimento IA ativo' if OPENAI_KEY else '⚠ sem chave (sem enriquecimento)'}
""")
    pipeline.rodar_continuo(sources, args.limit)