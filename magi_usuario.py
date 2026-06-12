"""
MAGIUsuario — Memória de Usuário + Salvamento de Sessões
═══════════════════════════════════════════════════════════
- Detecta fatos pessoais na conversa e salva automaticamente
- Salva sessões completas em data/logs/sessoes/
- Injeta contexto do usuário em cada query ao CASPER

Integração:
    from magi_usuario import MAGIUsuario
    self.usuario = MAGIUsuario()
"""

import os
import re
import json
import time
from pathlib import Path
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────
BASE            = Path(__file__).parent
USUARIO_PATH    = BASE / "data" / "memory" / "magi_usuario.json"
SESSOES_DIR     = BASE / "data" / "logs" / "sessoes"
USUARIO_PATH.parent.mkdir(parents=True, exist_ok=True)
SESSOES_DIR.mkdir(parents=True, exist_ok=True)

# ── Padrões para extração de fatos pessoais ───────────────────
PADROES_FATOS = [
    # Nome
    (r"meu nome[é\s]+([A-Z][a-záàâãéèêíïóôõöúüç\s]{2,30})",      "nome"),
    (r"pode me chamar de ([A-Z][a-záàâãéèêíïóôõöúüç\s]{2,20})",   "nome"),
    (r"sou o ([A-Z][a-záàâãéèêíïóôõöúüç\s]{2,20})",               "nome"),
    (r"me chamo ([A-Z][a-záàâãéèêíïóôõöúüç\s]{2,20})",            "nome"),
    # Profissão
    (r"trabalho (?:como|de|na área de) ([a-záàâãéèêíïóôõöúüç\s]{3,40})", "profissao"),
    (r"sou (?:um|uma) ([a-záàâãéèêíïóôõöúüç\s]{3,30})",           "profissao"),
    (r"minha profissão[eé\s]+([a-záàâãéèêíïóôõöúüç\s]{3,30})",    "profissao"),
    # Localização
    (r"moro em ([A-Z][a-záàâãéèêíïóôõöúüç\s,]{3,40})",            "localizacao"),
    (r"sou de ([A-Z][a-záàâãéèêíïóôõöúüç\s]{3,30})",              "localizacao"),
    # Idade
    (r"tenho (\d{1,2}) anos",                                       "idade"),
    # Preferências
    (r"(?:prefiro|gosto de|adoro) ([a-záàâãéèêíïóôõöúüç\s]{3,40})", "preferencia"),
    (r"não (?:gosto|curto) de ([a-záàâãéèêíïóôõöúüç\s]{3,40})",    "nao_gosta"),
    # Projeto/trabalho atual
    (r"estou (?:desenvolvendo|trabalhando em|criando) ([a-záàâãéèêíïóôõöúüç\s]{3,50})", "projeto_atual"),
    # Linguagem/tecnologia favorita
    (r"uso (?:principalmente|bastante|muito) ([a-záàâãéèêíïóôõöúüç\w\s\+\#]{2,30})",   "tecnologia"),
]


class MAGIUsuario:
    """
    Sistema de memória de usuário e sessões do MAGI.
    """

    def __init__(self):
        self._perfil   = self._carregar_perfil()
        self._sessao   = self._nova_sessao()

    # ── Perfil de usuário ──────────────────────────────────────
    def _carregar_perfil(self) -> dict:
        if USUARIO_PATH.exists():
            try:
                return json.loads(USUARIO_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "nome":         None,
            "profissao":    None,
            "localizacao":  None,
            "idade":        None,
            "preferencias": [],
            "nao_gosta":    [],
            "tecnologias":  [],
            "projetos":     [],
            "fatos_extras": [],
            "atualizado":   None,
            "total_sessoes": 0,
        }

    def _salvar_perfil(self):
        self._perfil["atualizado"] = datetime.now().isoformat(timespec="seconds")
        USUARIO_PATH.write_text(
            json.dumps(self._perfil, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def extrair_fatos(self, texto: str) -> list[dict]:
        """
        Detecta fatos pessoais no texto e atualiza o perfil.
        Retorna lista de fatos encontrados.
        """
        encontrados = []
        texto_lower = texto.lower()

        for padrao, categoria in PADROES_FATOS:
            for match in re.finditer(padrao, texto_lower):
                valor = match.group(1).strip().rstrip(".,!?")
                if len(valor) < 2:
                    continue
                # Capitaliza nome próprio
                if categoria == "nome":
                    valor = valor.title()
                fato = {"categoria": categoria, "valor": valor}
                encontrados.append(fato)
                self._aplicar_fato(categoria, valor)

        if encontrados:
            self._salvar_perfil()

        return encontrados

    def _aplicar_fato(self, categoria: str, valor: str):
        """Aplica um fato extraído ao perfil."""
        if categoria == "nome":
            self._perfil["nome"] = valor

        elif categoria == "profissao":
            self._perfil["profissao"] = valor

        elif categoria == "localizacao":
            self._perfil["localizacao"] = valor

        elif categoria == "idade":
            self._perfil["idade"] = int(valor)

        elif categoria == "preferencia":
            if valor not in self._perfil["preferencias"]:
                self._perfil["preferencias"].append(valor)

        elif categoria == "nao_gosta":
            if valor not in self._perfil["nao_gosta"]:
                self._perfil["nao_gosta"].append(valor)

        elif categoria == "tecnologia":
            if valor not in self._perfil["tecnologias"]:
                self._perfil["tecnologias"].append(valor)

        elif categoria == "projeto_atual":
            if valor not in self._perfil["projetos"]:
                self._perfil["projetos"].append(valor)

    def salvar_fato_manual(self, categoria: str, valor: str):
        """Salva um fato manualmente (ex: via comando 'lembre que...')"""
        self._aplicar_fato(categoria, valor)
        self._salvar_perfil()

    def contexto_para_ia(self) -> str:
        """
        Retorna bloco de contexto do usuário para injetar no prompt do CASPER.
        """
        p = self._perfil
        linhas = []

        if p.get("nome"):
            linhas.append(f"Nome do usuário: {p['nome']}")
        if p.get("profissao"):
            linhas.append(f"Profissão: {p['profissao']}")
        if p.get("localizacao"):
            linhas.append(f"Localização: {p['localizacao']}")
        if p.get("idade"):
            linhas.append(f"Idade: {p['idade']} anos")
        if p.get("tecnologias"):
            linhas.append(f"Tecnologias: {', '.join(p['tecnologias'][-5:])}")
        if p.get("projetos"):
            linhas.append(f"Projeto atual: {p['projetos'][-1]}")
        if p.get("preferencias"):
            linhas.append(f"Preferências: {', '.join(p['preferencias'][-3:])}")
        if p.get("total_sessoes"):
            linhas.append(f"Sessões anteriores: {p['total_sessoes']}")

        if not linhas:
            return ""

        return "─── PERFIL DO OPERADOR ───\n" + "\n".join(linhas) + "\n"

    def get_nome(self) -> str:
        return self._perfil.get("nome") or "Operador"

    # ── Sessões ────────────────────────────────────────────────
    def _nova_sessao(self) -> dict:
        return {
            "id":        datetime.now().strftime("%Y%m%d_%H%M%S"),
            "inicio":    datetime.now().isoformat(timespec="seconds"),
            "fim":       None,
            "trocas":    [],
            "total_q":   0,
            "modelos":   set(),
        }

    def registrar_troca(self, query: str, resposta: str, intencao: str = "?", modelo: str = ""):
        """Registra uma troca (pergunta + resposta) na sessão atual."""
        self._sessao["trocas"].append({
            "ts":       datetime.now().isoformat(timespec="seconds"),
            "q":        query,
            "r":        resposta[:800],  # limita tamanho
            "intencao": intencao,
            "modelo":   modelo,
        })
        self._sessao["total_q"] += 1
        if modelo:
            self._sessao["modelos"].add(modelo)

        # Tenta extrair fatos pessoais da query
        fatos = self.extrair_fatos(query)
        if fatos:
            return fatos
        return []

    def encerrar_sessao(self):
        """Finaliza e salva a sessão atual em disco."""
        self._sessao["fim"] = datetime.now().isoformat(timespec="seconds")
        self._sessao["modelos"] = list(self._sessao["modelos"])  # set → list

        # Nome do arquivo
        nome_arquivo = f"sessao_{self._sessao['id']}.json"
        caminho = SESSOES_DIR / nome_arquivo

        # Adiciona nome do usuário se conhecido
        self._sessao["operador"] = self._perfil.get("nome") or "Desconhecido"

        caminho.write_text(
            json.dumps(self._sessao, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # Atualiza total de sessões no perfil
        self._perfil["total_sessoes"] = self._perfil.get("total_sessoes", 0) + 1
        self._salvar_perfil()

        print(f"  [MAGIUsuario] Sessão salva: {nome_arquivo} ({self._sessao['total_q']} trocas)")

        # Inicia nova sessão
        self._sessao = self._nova_sessao()

    def listar_sessoes(self, n: int = 10) -> list[dict]:
        """Lista as últimas N sessões salvas."""
        arquivos = sorted(SESSOES_DIR.glob("sessao_*.json"), reverse=True)[:n]
        sessoes = []
        for arq in arquivos:
            try:
                s = json.loads(arq.read_text(encoding="utf-8"))
                sessoes.append({
                    "id":      s.get("id", "?"),
                    "inicio":  s.get("inicio", "?"),
                    "trocas":  s.get("total_q", 0),
                    "operador":s.get("operador", "?"),
                })
            except Exception:
                pass
        return sessoes

    def carregar_sessao(self, sessao_id: str) -> dict | None:
        """Carrega uma sessão específica pelo ID."""
        caminho = SESSOES_DIR / f"sessao_{sessao_id}.json"
        if caminho.exists():
            try:
                return json.loads(caminho.read_text(encoding="utf-8"))
            except Exception:
                pass
        return None

    def resumo_perfil(self) -> str:
        """Retorna resumo legível do perfil do usuário."""
        p = self._perfil
        linhas = [
            "╔══ PERFIL DO OPERADOR ══╗",
            f"  Nome       : {p.get('nome') or '(não informado)'}",
            f"  Profissão  : {p.get('profissao') or '(não informado)'}",
            f"  Localização: {p.get('localizacao') or '(não informado)'}",
            f"  Idade      : {p.get('idade') or '(não informado)'}",
            f"  Tecnologias: {', '.join(p.get('tecnologias', [])) or '(nenhuma)'}",
            f"  Projetos   : {', '.join(p.get('projetos', [])) or '(nenhum)'}",
            f"  Preferências:{', '.join(p.get('preferencias', [])) or '(nenhuma)'}",
            f"  Sessões    : {p.get('total_sessoes', 0)}",
            f"  Atualizado : {p.get('atualizado') or 'nunca'}",
            "╚══════════════════════╝",
        ]
        return "\n".join(linhas)
