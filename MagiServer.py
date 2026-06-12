"""
MAGI SERVER — Servidor de produção para acesso remoto
FastAPI + JWT + Rate limiting + Multi-usuário + HTTPS ready
"""
import os, time, json, hashlib, secrets, logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

# ── Dependências ──────────────────────────────────────────────────────────
try:
    from fastapi import FastAPI, HTTPException, Depends, Request, status
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
    from pydantic import BaseModel
    import uvicorn
    import jwt   # PyJWT
except ImportError as e:
    print(f"[ERRO] Instale as dependências: pip install fastapi uvicorn pyjwt python-multipart")
    raise

# ── Configuração ──────────────────────────────────────────────────────────
CONFIG_PATH  = Path(__file__).parent / "magi_server_config.json"
LOG_PATH     = Path(__file__).parent / "data" / "magi_server.log"
JWT_SECRET   = os.getenv("MAGI_JWT_SECRET", secrets.token_hex(32))
JWT_ALGO     = "HS256"
JWT_EXPIRE_H = int(os.getenv("MAGI_TOKEN_EXPIRE_H", "24"))
HOST         = os.getenv("MAGI_HOST", "0.0.0.0")
PORT         = int(os.getenv("MAGI_PORT", "8000"))
HTTPS_CERT   = os.getenv("MAGI_SSL_CERT", "")   # caminho para cert.pem
HTTPS_KEY    = os.getenv("MAGI_SSL_KEY",  "")   # caminho para key.pem

# ── Logging ───────────────────────────────────────────────────────────────
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("magi_server")

# ══════════════════════════════════════════════════════════════════════════
# GERENCIAMENTO DE USUÁRIOS
# ══════════════════════════════════════════════════════════════════════════

class GerenciadorUsuarios:
    """Usuários persistidos em JSON com senhas hasheadas com salt."""

    ROLES = {"admin", "user", "readonly"}

    def __init__(self):
        self._path = CONFIG_PATH
        self._dados = self._carregar()

    def _carregar(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"usuarios": {}, "sessoes_ativas": 0}

    def _salvar(self):
        self._path.write_text(
            json.dumps(self._dados, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _hash_senha(self, senha: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", senha.encode(), salt.encode(), 200_000
        ).hex()

    def criar_usuario(self, username: str, senha: str, role: str = "user") -> bool:
        if role not in self.ROLES:
            return False
        if username in self._dados["usuarios"]:
            return False
        salt = secrets.token_hex(16)
        self._dados["usuarios"][username] = {
            "hash":       self._hash_senha(senha, salt),
            "salt":       salt,
            "role":       role,
            "criado_em":  datetime.now().isoformat(timespec="seconds"),
            "ultimo_login": None,
            "queries":    0,
            "ativo":      True,
        }
        self._salvar()
        log.info(f"Usuário criado: {username} [{role}]")
        return True

    def autenticar(self, username: str, senha: str) -> Optional[dict]:
        u = self._dados["usuarios"].get(username)
        if not u or not u.get("ativo"):
            return None
        esperado = self._hash_senha(senha, u["salt"])
        if not secrets.compare_digest(esperado, u["hash"]):
            return None
        u["ultimo_login"] = datetime.now().isoformat(timespec="seconds")
        u["queries"] = u.get("queries", 0)
        self._salvar()
        return {"username": username, "role": u["role"]}

    def registrar_query(self, username: str):
        if username in self._dados["usuarios"]:
            self._dados["usuarios"][username]["queries"] = \
                self._dados["usuarios"][username].get("queries", 0) + 1
            self._salvar()

    def listar(self) -> list[dict]:
        return [
            {
                "username":    u,
                "role":        d["role"],
                "criado_em":   d["criado_em"],
                "ultimo_login": d.get("ultimo_login"),
                "queries":     d.get("queries", 0),
                "ativo":       d.get("ativo", True),
            }
            for u, d in self._dados["usuarios"].items()
        ]

    def desativar(self, username: str) -> bool:
        if username in self._dados["usuarios"]:
            self._dados["usuarios"][username]["ativo"] = False
            self._salvar()
            return True
        return False

    def alterar_senha(self, username: str, nova_senha: str) -> bool:
        if username not in self._dados["usuarios"]:
            return False
        salt = secrets.token_hex(16)
        self._dados["usuarios"][username]["hash"] = self._hash_senha(nova_senha, salt)
        self._dados["usuarios"][username]["salt"] = salt
        self._salvar()
        return True

# ══════════════════════════════════════════════════════════════════════════
# RATE LIMITING
# ══════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Rate limiting por usuário e por IP com janela deslizante."""

    LIMITES = {
        "admin":    {"por_min": 60,  "por_hora": 1000},
        "user":     {"por_min": 20,  "por_hora": 200},
        "readonly": {"por_min": 10,  "por_hora": 100},
    }

    def __init__(self):
        self._timestamps: dict[str, list[float]] = defaultdict(list)

    def verificar(self, chave: str, role: str = "user") -> tuple[bool, str]:
        agora  = time.time()
        limite = self.LIMITES.get(role, self.LIMITES["user"])
        ts     = self._timestamps[chave]

        # Remove timestamps antigos (>1h)
        self._timestamps[chave] = [t for t in ts if agora - t < 3600]
        ts = self._timestamps[chave]

        # Verifica por minuto
        por_min = sum(1 for t in ts if agora - t < 60)
        if por_min >= limite["por_min"]:
            return False, f"Rate limit: {limite['por_min']} requests/min excedido"

        # Verifica por hora
        if len(ts) >= limite["por_hora"]:
            return False, f"Rate limit: {limite['por_hora']} requests/hora excedido"

        self._timestamps[chave].append(agora)
        return True, ""

# ══════════════════════════════════════════════════════════════════════════
# JWT
# ══════════════════════════════════════════════════════════════════════════

def criar_token(username: str, role: str) -> str:
    payload = {
        "sub":  username,
        "role": role,
        "iat":  datetime.utcnow(),
        "exp":  datetime.utcnow() + timedelta(hours=JWT_EXPIRE_H),
        "jti":  secrets.token_hex(8),   # evita replay
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def verificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

# ══════════════════════════════════════════════════════════════════════════
# CAPTURA DE OUTPUT DO MAGI
# ══════════════════════════════════════════════════════════════════════════

import io, sys, threading

def capturar_processamento(magi, texto: str) -> tuple[str, dict]:
    """Executa magi.processar() e captura resposta do CASPER + metadados.

    Estratégia:
    - Detecta _e_conversa e _query_e_vaga ANTES do processar()
      → redireciona para _responder_conversa() ou lida localmente
    - Hooks em _chamar_nucleo e _chamar_deepseek para queries normais
    """
    capturada   = []
    nucleos_cap = {}
    erros       = []
    done        = threading.Event()
    meta        = {"intencao": "indefinido", "latencia_ms": 0,
                   "melchior": "", "balthasar": ""}
    t0          = time.time()
    hist_antes  = len(magi.historico) if hasattr(magi, "historico") else 0

    # ── Detecção antecipada: conversa ou query vaga ───────────────────────
    # Fazemos isso ANTES de instalar os hooks para tratar cada caso
    _eh_conversa  = hasattr(magi, "_e_conversa")  and magi._e_conversa(texto)
    _eh_vaga      = (not _eh_conversa) and hasattr(magi, "_query_e_vaga") and magi._query_e_vaga(texto)

    # ── Hook 1: _chamar_nucleo ────────────────────────────────────────────
    original_nucleo = magi._chamar_nucleo

    def _hook_nucleo(nome: str, prompt: str):
        try:
            r, mod = original_nucleo(nome, prompt)
        except Exception as e:
            erros.append(f"nucleo {nome}: {e}")
            return None, None
        if r:
            nucleos_cap[nome] = r
            if nome == "CASPER-3":
                capturada.insert(0, r)
            elif nome == "MELCHIOR-1":
                meta["melchior"] = r[:400]
            elif nome == "BALTHASAR-2":
                meta["balthasar"] = r[:400]
        return r, mod

    # ── Hook 2: _chamar_deepseek — captura QUALQUER chamada ao deepseek ──
    # Cobre _responder_conversa (saudações/conversa) e CASPER
    original_deepseek = getattr(magi, "_chamar_deepseek", None)
    _casper_prefix    = ""
    try:
        from MagiSystem import NUCLEOS
        _casper_prefix = NUCLEOS.get("CASPER-3", {}).get("system", "")[:50]
    except Exception:
        pass

    def _hook_deepseek(model: str, system: str, prompt: str):
        try:
            r = original_deepseek(model, system, prompt)
        except Exception as e:
            erros.append(f"deepseek: {e}")
            return None
        if r:
            eh_casper = (
                (_casper_prefix and system[:50].startswith(_casper_prefix[:40])) or
                "CASPER" in system[:200] or
                "veredito" in system[:200].lower()
            )
            eh_conversa = (
                "estado emocional" in system.lower() or
                "você é o magi" in system.lower() or
                "Max 3 frases" in system
            )
            if eh_casper:
                if r not in capturada:
                    capturada.insert(0, r)
            elif eh_conversa or _eh_conversa:
                if r not in capturada:
                    capturada.append(r)
            else:
                # Qualquer outra resposta deepseek também é candidata
                if r not in capturada:
                    capturada.append(r)
        return r

    # ── Executa em thread separada ────────────────────────────────────────
    def _run():
        try:
            magi._chamar_nucleo = _hook_nucleo
            if original_deepseek:
                magi._chamar_deepseek = _hook_deepseek

            if _eh_conversa:
                # Chama _responder_conversa diretamente — os hooks vão capturar
                magi._responder_conversa(texto)
            elif _eh_vaga:
                # Query vaga: chama _responder_conversa com a query original
                # (o MAGI responde conversacionalmente pedindo mais contexto)
                magi._responder_conversa(texto)
            else:
                magi.processar(texto)
        except Exception as e:
            erros.append(f"processar: {e}")
        finally:
            try:
                magi._chamar_nucleo = original_nucleo
            except Exception:
                pass
            try:
                if original_deepseek:
                    magi._chamar_deepseek = original_deepseek
            except Exception:
                pass
            meta["latencia_ms"] = int((time.time() - t0) * 1000)
            done.set()

    t = threading.Thread(target=_run, daemon=True, name="magi-processar")
    t.start()
    done.wait(timeout=180)

    # ── Extrai intenção do histórico ──────────────────────────────────────
    try:
        if hasattr(magi, "historico") and magi.historico:
            ultimo = list(magi.historico)[-1]
            if "[" in ultimo and "]" in ultimo:
                meta["intencao"] = ultimo.split("[")[1].split("]")[0].lower()
    except Exception:
        pass

    # ── Limpeza da resposta ───────────────────────────────────────────────
    import re as _re

    def _limpar(r: str) -> str:
        r = _re.sub(r"<think>.*?</think>", "", r, flags=_re.DOTALL).strip()
        linhas = [l for l in r.splitlines() if not l.strip().startswith("→")]
        return "\n".join(linhas).strip() or r

    # ── Camada 1: capturado pelos hooks ───────────────────────────────────
    if capturada:
        return _limpar(capturada[0]), meta

    # ── Camada 2: qualquer núcleo capturado ───────────────────────────────
    for nome in ("CASPER-3", "BALTHASAR-2", "MELCHIOR-1"):
        if nome in nucleos_cap:
            return _limpar(nucleos_cap[nome]), meta

    # ── Camada 3: histórico novo (só com separador explícito) ────────────
    try:
        if hasattr(magi, "historico"):
            novo_hist = list(magi.historico)[hist_antes:]
            for entrada in reversed(novo_hist):
                for sep in (" | CASPER: ", "| CASPER:", "CASPER:"):
                    if sep in entrada:
                        r = _limpar(entrada.split(sep, 1)[-1].strip())
                        if r and r != texto:
                            return r, meta
                if "|" in entrada:
                    r_hist = entrada.rsplit("|", 1)[-1].strip()
                    if r_hist and r_hist != texto:
                        return _limpar(r_hist), meta
    except Exception:
        pass

    # ── Camada 4: erro descritivo ─────────────────────────────────────────
    if erros:
        erros_filtrados = [e for e in erros if "intencao" not in e.lower()]
        msg = erros_filtrados[0] if erros_filtrados else erros[0]
        return f"[ERRO] {msg[:200]}", meta

    return "[Sem resposta — verifique o terminal do servidor]", meta

# ══════════════════════════════════════════════════════════════════════════
# APLICAÇÃO FASTAPI
# ══════════════════════════════════════════════════════════════════════════

app      = FastAPI(
    title="MAGI Server",
    description="API de acesso remoto ao sistema MAGI · NERV HQ",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
usuarios = GerenciadorUsuarios()
limiter  = RateLimiter()
bearer   = HTTPBearer()
magi_instance = None   # inicializado em startup

# CORS — ajuste origins conforme necessário
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # restrinja em produção: ["https://seu-dominio.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════════════════════════════
# PATCHES DE VELOCIDADE — desativa etapas lentas no modo servidor
# ══════════════════════════════════════════════════════════════════════════

def _aplicar_patches_velocidade(magi, MAGIInterface):
    """Aplica monkey-patches para eliminar latência desnecessária no servidor.

    No modo servidor (API), o dashboard exibe a resposta instantaneamente.
    Não há motivo para:
      - Animação de digitação char-a-char (digitar)
      - Metacognição (1 chamada LLM extra após o veredito)
      - CoT interno do CASPER (1 chamada LLM extra antes do veredito)
      - Reflexão pós-resposta (consumo de recursos em background)
    """

    # ── 1. Desativa animação de digitação ─────────────────────────────────
    # digitar() imprime char por char com sleep — no servidor é só ruído
    import time as _time
    original_digitar = MAGIInterface.digitar

    @staticmethod
    def _digitar_rapido(texto, cor="", delay=0):
        print(texto)   # imprime tudo de uma vez, sem sleep

    try:
        MAGIInterface.digitar = _digitar_rapido
        log.info("Patch velocidade: digitar() sem animação")
    except Exception as e:
        log.warning(f"Patch digitar falhou: {e}")

    # ── 2. Desativa metacognição (1 chamada LLM extra) ────────────────────
    # _metacognicao chama deepseek novamente após o veredito para "avaliar"
    # No servidor isso dobra a latência sem benefício visível
    def _metacognicao_rapida(query, veredito, intencao):
        return veredito   # retorna o veredito original sem chamar LLM

    try:
        magi._metacognicao = _metacognicao_rapida
        log.info("Patch velocidade: _metacognicao() desativada")
    except Exception as e:
        log.warning(f"Patch metacognicao falhou: {e}")

    # ── 3. Desativa CoT interno do CASPER ─────────────────────────────────
    # O CoT dispara uma chamada ao deepseek antes do veredito.
    # Vamos fazer o CoT retornar None imediatamente para pular essa etapa.
    # O CASPER ainda gera o veredito normalmente — só sem o "raciocínio" extra.
    original_chamar_deepseek = magi._chamar_deepseek

    _cot_system_marker = "Raciocine em etapas antes do veredito"

    def _chamar_deepseek_sem_cot(model, system, prompt):
        if _cot_system_marker in system:
            return None   # pula o CoT — CASPER vai para o veredito direto
        return original_chamar_deepseek(model, system, prompt)

    try:
        magi._chamar_deepseek = _chamar_deepseek_sem_cot
        log.info("Patch velocidade: CoT do CASPER desativado")
    except Exception as e:
        log.warning(f"Patch CoT falhou: {e}")

    # ── 4. Desativa reflexão pós-resposta ─────────────────────────────────
    # Roda em thread separada mas consome uma chamada LLM adicional
    def _reflexao_noop(query, veredito, intencao):
        pass   # noop — não chama LLM

    try:
        magi._reflexao_pos_resposta = _reflexao_noop
        log.info("Patch velocidade: _reflexao_pos_resposta() desativada")
    except Exception as e:
        log.warning(f"Patch reflexao falhou: {e}")

    log.info("Patches de velocidade aplicados — modo servidor ativo")


# ── Cria admin padrão se não existir ─────────────────────────────────────
@app.on_event("startup")
async def startup():
    global magi_instance
    # Cria admin padrão (troque a senha imediatamente após o primeiro login)
    if not usuarios._dados["usuarios"]:
        senha_padrao = os.getenv("MAGI_ADMIN_SENHA", "magi_admin_2026")
        usuarios.criar_usuario("admin", senha_padrao, role="admin")
        log.warning(f"Admin padrão criado. TROQUE A SENHA: {senha_padrao}")

    # Inicializa MAGISystem
    try:
        from MagiSystem import MAGISystem, MAGIInterface
        magi_instance = MAGISystem()
        _aplicar_patches_velocidade(magi_instance, MAGIInterface)
        log.info("MAGISystem inicializado com sucesso")
    except Exception as e:
        log.error(f"Erro ao inicializar MAGISystem: {e}")

# ── Dependências ──────────────────────────────────────────────────────────
async def get_usuario_atual(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(bearer)
) -> dict:
    payload = verificar_token(creds.credentials)
    usuario = {"username": payload["sub"], "role": payload["role"]}

    # Rate limit por usuário
    ok, msg = limiter.verificar(usuario["username"], usuario["role"])
    if not ok:
        log.warning(f"Rate limit: {usuario['username']} — {msg}")
        raise HTTPException(status_code=429, detail=msg)

    # Rate limit por IP (camada extra)
    ip = request.client.host if request.client else "unknown"
    ok_ip, msg_ip = limiter.verificar(f"ip:{ip}", "user")
    if not ok_ip:
        raise HTTPException(status_code=429, detail=f"IP rate limit: {msg_ip}")

    return usuario

async def requer_admin(usuario: dict = Depends(get_usuario_atual)) -> dict:
    if usuario["role"] != "admin":
        raise HTTPException(status_code=403, detail="Requer permissão de administrador")
    return usuario

# ══════════════════════════════════════════════════════════════════════════
# MODELOS PYDANTIC
# ══════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str
    senha:    str

class QueryRequest(BaseModel):
    texto:   str
    modo:    str = "processar"   # processar | debate | ego | memoria

class CriarUsuarioRequest(BaseModel):
    username: str
    senha:    str
    role:     str = "user"

class AlterarSenhaRequest(BaseModel):
    username:    str
    nova_senha:  str

class DebateRequest(BaseModel):
    tema: str

# ══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse, tags=["Sistema"])
async def raiz():
    """Serve o dashboard NERV HTML."""
    for nome in ["NERV_dashboard_da_NERV.HTML", "NERV_dashboard_da_NERV.html"]:
        p = Path(__file__).parent / nome
        if p.exists():
            return HTMLResponse(content=p.read_text(encoding="utf-8"))
    # Fallback mínimo
    online = magi_instance is not None
    cor = "#00ff88" if online else "#c8001a"
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>MAGI</title>
<meta http-equiv="refresh" content="5">
<style>*{margin:0;padding:0;box-sizing:border-box}
body{font-family:monospace;background:#020408;color:#c8d8e8;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;gap:20px}
.logo{font-size:48px;font-weight:900;color:#c8001a;letter-spacing:8px}
.st{font-size:16px;padding:10px 28px;border:1px solid """ + cor + """;color:""" + cor + """}
input{background:#071020;border:1px solid #0a2040;color:#c8d8e8;padding:10px 16px;font-family:monospace;font-size:14px;width:400px;outline:none}
button{background:#c8001a;border:none;color:#fff;padding:10px 20px;font-family:monospace;cursor:pointer;letter-spacing:2px}
#r{width:400px;background:#040c14;border:1px solid #0a2040;padding:14px;font-size:12px;line-height:1.7;min-height:50px;display:none}
a{color:#00d4ff}
</style></head>
<body>
<div class="logo">MAGI</div>
<div class="st">""" + ("◈ ONLINE" if online else "✗ OFFLINE") + """</div>
<input id="q" placeholder="Digite uma consulta..." onkeydown="if(event.key==='Enter')send()">
<button onclick="send()">ENVIAR</button>
<div id="r"></div>
<small><a href="/docs">/docs</a> &nbsp;|&nbsp; <a href="/api/status">/api/status</a></small>
<script>
async function send(){
  const q=document.getElementById('q').value.trim();if(!q)return;
  const r=document.getElementById('r');r.style.display='block';r.textContent='...';
  try{
    const res=await fetch('/api/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q})});
    const d=await res.json();r.textContent=d.veredito||d.resposta||d.detail||JSON.stringify(d);
  }catch(e){r.textContent='Erro: '+e.message}
}
</script>
</body></html>""")

@app.get("/saude", tags=["Sistema"])
async def saude():
    """Health check — não requer autenticação."""
    return {
        "status":   "ok",
        "magi":     "online" if magi_instance else "offline",
        "uptime":   time.time(),
        "ts":       datetime.now().isoformat(timespec="seconds"),
    }

# ── Auth ──────────────────────────────────────────────────────────────────

@app.post("/auth/login", tags=["Autenticação"])
async def login(body: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"

    # Rate limit por IP para login (anti brute-force)
    ok, msg = limiter.verificar(f"login:{ip}", "readonly")
    if not ok:
        log.warning(f"Brute-force detectado: {ip}")
        raise HTTPException(status_code=429, detail="Muitas tentativas de login")

    usuario = usuarios.autenticar(body.username, body.senha)
    if not usuario:
        log.warning(f"Login falhou: {body.username} de {ip}")
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    token = criar_token(usuario["username"], usuario["role"])
    log.info(f"Login: {usuario['username']} [{usuario['role']}] de {ip}")
    return {
        "token":      token,
        "tipo":       "Bearer",
        "expira_em":  JWT_EXPIRE_H * 3600,
        "username":   usuario["username"],
        "role":       usuario["role"],
    }

@app.post("/auth/renovar", tags=["Autenticação"])
async def renovar_token(usuario: dict = Depends(get_usuario_atual)):
    """Renova o token sem precisar fazer login novamente."""
    novo = criar_token(usuario["username"], usuario["role"])
    return {"token": novo, "tipo": "Bearer", "expira_em": JWT_EXPIRE_H * 3600}

# ── Queries ───────────────────────────────────────────────────────────────

@app.post("/magi/query", tags=["MAGI"])
async def query(body: QueryRequest, usuario: dict = Depends(get_usuario_atual)):
    """Envia uma query ao MAGI e retorna o veredito do CASPER-3."""
    if not magi_instance:
        raise HTTPException(status_code=503, detail="MAGISystem offline")
    if not body.texto.strip():
        raise HTTPException(status_code=400, detail="Texto vazio")
    if len(body.texto) > 4000:
        raise HTTPException(status_code=400, detail="Texto muito longo (máx 4000 chars)")

    log.info(f"Query: {usuario['username']} — {body.texto[:60]}")
    t0 = time.time()

    resposta, meta = capturar_processamento(magi_instance, body.texto)
    usuarios.registrar_query(usuario["username"])

    return {
        "resposta":    resposta,
        "intencao":    meta.get("intencao", "indefinido"),
        "latencia_ms": meta.get("latencia_ms", int((time.time() - t0) * 1000)),
        "usuario":     usuario["username"],
        "ts":          datetime.now().isoformat(timespec="seconds"),
    }

@app.post("/magi/debate", tags=["MAGI"])
async def debate(body: DebateRequest, usuario: dict = Depends(get_usuario_atual)):
    """Inicia um debate entre os núcleos sobre um tema."""
    if not magi_instance:
        raise HTTPException(status_code=503, detail="MAGISystem offline")

    log.info(f"Debate: {usuario['username']} — {body.tema[:60]}")
    output = io.StringIO()
    old = sys.stdout
    sys.stdout = output
    try:
        magi_instance.debate(body.tema)
    except Exception as e:
        sys.stdout = old
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        sys.stdout = old

    import re
    texto_limpo = re.sub(r"\x1b\[[0-9;]*m", "", output.getvalue())
    return {"debate": texto_limpo, "tema": body.tema}

@app.get("/magi/ego", tags=["MAGI"])
async def ego(usuario: dict = Depends(get_usuario_atual)):
    """Retorna o estado emocional e consciência atual do MAGI."""
    if not magi_instance:
        raise HTTPException(status_code=503, detail="MAGISystem offline")
    try:
        estado = magi_instance.consciencia._estado
        return {
            "emocao":        estado.get("emocao", "curioso"),
            "total_queries": estado.get("total_queries", 0),
            "aprendizados":  len(estado.get("aprendizados", [])),
            "versao":        getattr(magi_instance, "_versao_atual", "1.0.0"),
            "uptime_s":      int(time.time()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/magi/memoria", tags=["MAGI"])
async def memoria(
    q: Optional[str] = None,
    k: int = 5,
    usuario: dict = Depends(get_usuario_atual)
):
    """Busca na memória semântica do MAGI."""
    if not magi_instance:
        raise HTTPException(status_code=503, detail="MAGISystem offline")
    try:
        if q:
            resultados = magi_instance.memoria.buscar(q, k=min(k, 20))
            return {"query": q, "resultados": resultados, "total": len(resultados)}
        else:
            recentes = [r["texto"] for r in magi_instance.memoria.registros[-k:]]
            return {"recentes": recentes, "total": len(magi_instance.memoria.registros)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/magi/historico", tags=["MAGI"])
async def historico(n: int = 20, usuario: dict = Depends(get_usuario_atual)):
    """Retorna as últimas N entradas do histórico da sessão."""
    if not magi_instance:
        raise HTTPException(status_code=503, detail="MAGISystem offline")
    hist = list(magi_instance.historico)[-n:]
    return {"historico": hist, "total": len(magi_instance.historico)}

@app.get("/magi/saude", tags=["MAGI"])
async def magi_saude(usuario: dict = Depends(get_usuario_atual)):
    """Dashboard de saúde do MAGISystem."""
    if not magi_instance:
        raise HTTPException(status_code=503, detail="MAGISystem offline")
    try:
        texto = magi_instance.dashboard_saude()
        import re
        return {"dashboard": re.sub(r"\x1b\[[0-9;]*m", "", texto)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Admin ─────────────────────────────────────────────────────────────────

@app.get("/admin/usuarios", tags=["Administração"])
async def listar_usuarios(admin: dict = Depends(requer_admin)):
    return {"usuarios": usuarios.listar()}

@app.post("/admin/usuarios", tags=["Administração"])
async def criar_usuario(body: CriarUsuarioRequest, admin: dict = Depends(requer_admin)):
    ok = usuarios.criar_usuario(body.username, body.senha, body.role)
    if not ok:
        raise HTTPException(status_code=409, detail="Usuário já existe ou role inválido")
    log.info(f"Admin {admin['username']} criou usuário: {body.username} [{body.role}]")
    return {"ok": True, "username": body.username}

@app.delete("/admin/usuarios/{username}", tags=["Administração"])
async def desativar_usuario(username: str, admin: dict = Depends(requer_admin)):
    if username == admin["username"]:
        raise HTTPException(status_code=400, detail="Não pode desativar a si mesmo")
    ok = usuarios.desativar(username)
    if not ok:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    log.info(f"Admin {admin['username']} desativou: {username}")
    return {"ok": True}

@app.put("/admin/senha", tags=["Administração"])
async def alterar_senha(body: AlterarSenhaRequest, admin: dict = Depends(requer_admin)):
    ok = usuarios.alterar_senha(body.username, body.nova_senha)
    if not ok:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    log.info(f"Admin {admin['username']} alterou senha de: {body.username}")
    return {"ok": True}

@app.get("/admin/logs", tags=["Administração"])
async def ver_logs(n: int = 100, admin: dict = Depends(requer_admin)):
    """Últimas N linhas do log do servidor."""
    try:
        linhas = LOG_PATH.read_text(encoding="utf-8").splitlines()
        return {"logs": linhas[-n:], "total": len(linhas)}
    except Exception:
        return {"logs": [], "total": 0}

@app.post("/admin/evolucao", tags=["Administração"])
async def iniciar_evolucao(ciclos: int = 1, admin: dict = Depends(requer_admin)):
    """Inicia um ciclo de auto-evolução do MAGI."""
    if not magi_instance:
        raise HTTPException(status_code=503, detail="MAGISystem offline")
    output = io.StringIO()
    old    = sys.stdout
    sys.stdout = output
    try:
        magi_instance.autoevoluir(ciclos=ciclos, silencioso=True)
    except Exception as e:
        sys.stdout = old
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        sys.stdout = old
    import re
    return {"resultado": re.sub(r"\x1b\[[0-9;]*m", "", output.getvalue())}

# ══════════════════════════════════════════════════════════════════════════
# ROTAS /api/* — Aliases para o dashboard (sem autenticação obrigatória)
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/status", tags=["Dashboard"])
async def api_status():
    """Status público — usado pelo dashboard para checar conectividade."""
    estado = {}
    if magi_instance:
        try:
            s = magi_instance.consciencia._estado
            estado = {
                "online":          True,
                "total_queries":   s.get("total_queries", 0),
                "total_sessoes":   s.get("total_sessoes", 0),
                "estado_emocional":s.get("estado_emocional", s.get("emocao", "curioso")),
                "tema_dominante":  magi_instance.consciencia.tema_dominante() if hasattr(magi_instance.consciencia, "tema_dominante") else "?",
                "intensidade":     s.get("intensidade", 0.5),
                "autoavaliacao":   s.get("autoavaliacao", ""),
                "cache_entries":   len(getattr(magi_instance, "_cache_respostas", [])),
                "uptime_s":        int(time.time()),
            }
        except Exception:
            estado = {"online": True, "total_queries": 0}
    else:
        estado = {"online": False, "erro": "MAGISystem offline"}
    return estado


@app.post("/api/query", tags=["Dashboard"])
async def api_query(request: Request):
    """Query pública do dashboard — sem JWT obrigatório."""
    if not magi_instance:
        return {"erro": "MAGISystem offline"}
    try:
        body  = await request.json()
        texto = (body.get("query") or body.get("texto") or "").strip()
        if not texto:
            return {"erro": "Query vazia"}
        if len(texto) > 4000:
            return {"erro": "Texto muito longo (máx 4000 chars)"}

        resposta, meta = capturar_processamento(magi_instance, texto)

        if resposta.startswith("[ERRO]"):
            log.error(f"Falha ao processar query: {resposta}")

        return {
            "veredito":    resposta,
            "resposta":    resposta,
            "intencao":    meta.get("intencao", "indefinido"),
            "latencia_ms": meta.get("latencia_ms", 0),
            "casper":      {"resposta": resposta, "modelo": "deepseek"},
            "melchior":    {"resposta": meta.get("melchior", ""), "modelo": "deepseek"},
            "balthasar":   {"resposta": meta.get("balthasar", ""), "modelo": "deepseek"},
        }
    except Exception as e:
        log.error(f"api_query exception: {e}")
        return {"erro": str(e)}


@app.get("/api/nucleos/status", tags=["Dashboard"])
async def api_nucleos_status():
    from MagiSystem import NUCLEOS, LOCAL_CONFIG
    result = {}
    for nome, cfg in NUCLEOS.items():
        result[nome] = {
            "online":  True,
            "modelo":  cfg.get("model", "?"),
            "backend": cfg.get("backend", "?"),
        }
    return result


@app.get("/api/ego", tags=["Dashboard"])
async def api_ego():
    if not magi_instance:
        return {"erro": "offline"}
    try:
        s = magi_instance.consciencia._estado
        aprendizados = [
            {"texto": a.get("texto", str(a)), "ts": a.get("timestamp", "")}
            if isinstance(a, dict) else {"texto": str(a), "ts": ""}
            for a in (s.get("aprendizados") or [])[-10:]
        ]
        return {
            "estado_emocional":  s.get("estado_emocional", s.get("emocao", "curioso")),
            "intensidade":       s.get("intensidade", 0.5),
            "autoavaliacao":     s.get("autoavaliacao", ""),
            "total_queries":     s.get("total_queries", 0),
            "total_sessoes":     s.get("total_sessoes", 0),
            "acertos":           s.get("acertos", 0),
            "erros_admitidos":   s.get("erros_admitidos", 0),
            "tema_dominante":    magi_instance.consciencia.tema_dominante() if hasattr(magi_instance.consciencia, "tema_dominante") else "?",
            "temas_frequentes":  s.get("temas_frequentes", {}),
            "aprendizados":      aprendizados,
            "cache_entries":     len(getattr(magi_instance, "_cache_respostas", [])),
        }
    except Exception as e:
        return {"erro": str(e)}


@app.get("/api/memoria", tags=["Dashboard"])
async def api_memoria(k: int = 25):
    if not magi_instance:
        return []
    try:
        regs = list(reversed(magi_instance.memoria.registros[-k:]))
        return [{"texto": r.get("texto",""), "categoria": r.get("categoria","?"), "timestamp": r.get("timestamp","")} for r in regs]
    except Exception:
        return []


@app.get("/api/historico", tags=["Dashboard"])
async def api_historico():
    if not magi_instance:
        return []
    return list(magi_instance.historico)


@app.get("/api/logs", tags=["Dashboard"])
async def api_logs_pub(n: int = 80, nivel: str = "INFO"):
    try:
        path = Path("magi_log.jsonl")
        if not path.exists():
            path = Path("log_nerv.jsonl")
        if not path.exists():
            return {"logs": [], "total": 0}
        linhas = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        filtradas = [l for l in linhas if nivel == "DEBUG" or f'"lvl": "{nivel}"' in l or f"[{nivel}]" in l]
        return {"logs": filtradas[-n:], "total": len(filtradas)}
    except Exception:
        return {"logs": [], "total": 0}


@app.post("/api/memoria/salvar", tags=["Dashboard"])
async def api_memoria_salvar(request: Request):
    if not magi_instance:
        return {"ok": False}
    try:
        body = await request.json()
        magi_instance.memoria.salvar(body.get("query",""), body.get("veredito",""), body.get("intencao","indefinido"))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


@app.get("/api/config", tags=["Dashboard"])
async def api_config():
    import os
    from MagiSystem import LOCAL_CONFIG
    try:
        from MagiSystem import OPENROUTER_CONFIG
        or_modelo = OPENROUTER_CONFIG.get("modelo", "?")
    except Exception:
        or_modelo = "?"
    return {
        "google_key":     bool(os.getenv("GOOGLE_API_KEY")),
        "openai_key":     bool(os.getenv("OPENAI_API_KEY")),
        "openrouter_key": bool(os.getenv("OPENROUTER_API_KEY")),
        "anthropic_key":  bool(os.getenv("ANTHROPIC_API_KEY")),
        "deepseek_key":   bool(os.getenv("DEEPSEEK_API_KEY")),
        "local_ativo":    LOCAL_CONFIG["ativo"],
        "local_modelo":   LOCAL_CONFIG["modelo"],
        "openrouter_modelo": or_modelo,
        "versao": "15.0",
    }




# ══════════════════════════════════════════════════════════════════════════
# ROTAS /api/* — Dashboard (sem autenticação)
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/status", tags=["Dashboard"])
async def api_status():
    if not magi_instance:
        return {"online": False, "erro": "MAGISystem offline"}
    try:
        s = magi_instance.consciencia._estado
        return {
            "online":           True,
            "total_queries":    s.get("total_queries", 0),
            "total_sessoes":    s.get("total_sessoes", 0),
            "estado_emocional": s.get("estado_emocional", s.get("emocao", "curioso")),
            "tema_dominante":   magi_instance.consciencia.tema_dominante() if hasattr(magi_instance.consciencia, "tema_dominante") else "?",
            "intensidade":      s.get("intensidade", 0.5),
            "autoavaliacao":    s.get("autoavaliacao", ""),
            "cache_entries":    len(getattr(magi_instance, "_cache_respostas", [])),
            "uptime_s":         int(time.time()),
        }
    except Exception as e:
        return {"online": True, "total_queries": 0, "erro": str(e)}




@app.get("/api/nucleos/status", tags=["Dashboard"])
async def api_nucleos_status():
    try:
        from MagiSystem import NUCLEOS, LOCAL_CONFIG
        return {n: {"online": True, "modelo": c.get("model","?"), "backend": c.get("backend","?")} for n,c in NUCLEOS.items()}
    except Exception:
        return {}


@app.get("/api/ego", tags=["Dashboard"])
async def api_ego():
    if not magi_instance:
        return {"erro": "offline"}
    try:
        s = magi_instance.consciencia._estado
        aprendizados = [
            {"texto": a.get("texto", str(a)), "ts": a.get("timestamp", "")} if isinstance(a, dict) else {"texto": str(a), "ts": ""}
            for a in (s.get("aprendizados") or [])[-10:]
        ]
        return {
            "estado_emocional": s.get("estado_emocional", s.get("emocao", "curioso")),
            "intensidade":      s.get("intensidade", 0.5),
            "autoavaliacao":    s.get("autoavaliacao", ""),
            "total_queries":    s.get("total_queries", 0),
            "total_sessoes":    s.get("total_sessoes", 0),
            "acertos":          s.get("acertos", 0),
            "erros_admitidos":  s.get("erros_admitidos", 0),
            "tema_dominante":   magi_instance.consciencia.tema_dominante() if hasattr(magi_instance.consciencia, "tema_dominante") else "?",
            "temas_frequentes": s.get("temas_frequentes", {}),
            "aprendizados":     aprendizados,
            "cache_entries":    len(getattr(magi_instance, "_cache_respostas", [])),
        }
    except Exception as e:
        return {"erro": str(e)}


@app.get("/api/memoria", tags=["Dashboard"])
async def api_memoria(k: int = 25):
    if not magi_instance:
        return []
    try:
        return [{"texto": r.get("texto",""), "categoria": r.get("categoria","?"), "timestamp": r.get("timestamp","")}
                for r in list(reversed(magi_instance.memoria.registros[-k:]))]
    except Exception:
        return []


@app.post("/api/memoria/salvar", tags=["Dashboard"])
async def api_memoria_salvar(request: Request):
    if not magi_instance:
        return {"ok": False}
    try:
        body = await request.json()
        magi_instance.memoria.salvar(body.get("query",""), body.get("veredito",""), body.get("intencao","indefinido"))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


@app.get("/api/historico", tags=["Dashboard"])
async def api_historico():
    if not magi_instance:
        return []
    return list(magi_instance.historico)


@app.get("/api/logs", tags=["Dashboard"])
async def api_logs_pub(n: int = 80, nivel: str = "INFO"):
    try:
        for nome in ["magi_log.jsonl", "log_nerv.jsonl", "magi_log.json"]:
            p = Path(nome)
            if p.exists():
                linhas = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                filtradas = [l for l in linhas if nivel == "DEBUG" or f'"lvl": "{nivel}"' in l or f"[{nivel}]" in l]
                return {"logs": filtradas[-n:], "total": len(filtradas)}
        return {"logs": [], "total": 0}
    except Exception:
        return {"logs": [], "total": 0}


@app.get("/api/config", tags=["Dashboard"])
async def api_config():
    import os
    try:
        from MagiSystem import LOCAL_CONFIG
        local_ativo = LOCAL_CONFIG["ativo"]
        local_modelo = LOCAL_CONFIG["modelo"]
    except Exception:
        local_ativo, local_modelo = False, "?"
    return {
        "google_key":     bool(os.getenv("GOOGLE_API_KEY")),
        "openai_key":     bool(os.getenv("OPENAI_API_KEY")),
        "openrouter_key": bool(os.getenv("OPENROUTER_API_KEY")),
        "anthropic_key":  bool(os.getenv("ANTHROPIC_API_KEY")),
        "deepseek_key":   bool(os.getenv("DEEPSEEK_API_KEY")),
        "local_ativo":    local_ativo,
        "local_modelo":   local_modelo,
        "versao":         "15.0",
    }


# ── Middleware de log ─────────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0   = time.time()
    resp = await call_next(request)
    ms   = int((time.time() - t0) * 1000)
    ip   = request.client.host if request.client else "?"
    log.info(f"{request.method} {request.url.path} {resp.status_code} {ms}ms [{ip}]")
    return resp

# ══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    ssl_kwargs = {}
    if HTTPS_CERT and HTTPS_KEY:
        ssl_kwargs = {"ssl_certfile": HTTPS_CERT, "ssl_keyfile": HTTPS_KEY}
        log.info(f"HTTPS ativo — cert: {HTTPS_CERT}")
    else:
        log.warning("Rodando em HTTP. Em produção use HTTPS com Let's Encrypt.")

    log.info(f"MAGI Server iniciando em {HOST}:{PORT}")
    uvicorn.run(
        "magi_server:app",
        host=HOST,
        port=PORT,
        reload=False,
        workers=1,          # MAGISystem não é thread-safe para múltiplos workers
        log_level="warning",
        access_log=False,   # já logamos no middleware
        **ssl_kwargs,
    )