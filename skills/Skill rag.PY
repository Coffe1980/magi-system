"""
╔══════════════════════════════════════════════════════════════╗
║  MAGI SKILL — RAG (Retrieval-Augmented Generation)           ║
║  Carregado sob demanda pelo sistema de memória e consultas   ║
╚══════════════════════════════════════════════════════════════╝
Fontes indexadas:
  - documentação interna (magi_conhecimento.jsonl)
  - código do próprio projeto (*.py)
  - web (via MAGICaptcha)
  - arquivos do usuário

Uso:
  from skill_rag import MAGIRAG
  rag = MAGIRAG(magi_instance)
  contexto = rag.buscar("como funciona o FAISS?", k=4)
"""

import os, re, json, time, hashlib
from pathlib import Path
from typing import Optional
from colorama import Fore


class MAGIRAG:
    """
    Sistema RAG do MAGI.
    Tenta ChromaDB primeiro (persistente, semântico).
    Fallback para FAISS em memória se Chroma não estiver instalado.
    Fallback final: busca por keywords simples no jsonl.
    """

    CONHECIMENTO_PATH = Path(__file__).parent / "magi_conhecimento.jsonl"
    CHROMA_DIR        = Path(__file__).parent / ".magi_chroma"
    COLLECTION_NAME   = "magi_rag"

    def __init__(self, magi_system=None):
        self.magi      = magi_system
        self._client   = None          # ChromaDB client
        self._colecao  = None          # ChromaDB collection
        self._faiss    = None          # FAISS index (fallback)
        self._textos   = []            # textos indexados (FAISS fallback)
        self._encoder  = None          # SentenceTransformer compartilhado
        self._modo     = None          # "chroma", "faiss", "keyword"
        self._indexado = 0

    # ── inicialização lazy ────────────────────────────────────

    def _init(self):
        if self._modo:
            return
        # Tenta ChromaDB
        try:
            import chromadb
            self.CHROMA_DIR.mkdir(exist_ok=True)
            self._client  = chromadb.PersistentClient(path=str(self.CHROMA_DIR))
            self._colecao = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
            self._modo = "chroma"
            print(f"{Fore.CYAN}  [RAG] ChromaDB iniciado ({self._colecao.count()} docs).")
        except ImportError:
            # Tenta FAISS
            try:
                import faiss as _faiss
                import numpy as np
                from sentence_transformers import SentenceTransformer
                self._encoder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                self._faiss   = _faiss.IndexFlatL2(384)
                self._np      = np
                self._modo    = "faiss"
                print(f"{Fore.YELLOW}  [RAG] FAISS iniciado (ChromaDB não instalado).")
            except ImportError:
                self._modo = "keyword"
                print(f"{Fore.YELLOW}  [RAG] Modo keyword (instale chromadb para RAG semântico).")

    # ── indexação ─────────────────────────────────────────────

    def indexar_conhecimento(self):
        """Indexa magi_conhecimento.jsonl no RAG."""
        self._init()
        if not self.CONHECIMENTO_PATH.exists():
            return 0
        count = 0
        with open(self.CONHECIMENTO_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    reg  = json.loads(line)
                    texto = f"Q: {reg.get('pergunta','')}\nR: {reg.get('resposta','')}\nTópico: {reg.get('topico','')}"
                    doc_id = hashlib.md5(texto.encode()).hexdigest()[:16]
                    self._add_doc(doc_id, texto, {"fonte": "conhecimento", "topico": reg.get("topico","")})
                    count += 1
                except Exception:
                    pass
        self._indexado += count
        print(f"{Fore.GREEN}  [RAG] {count} registros de conhecimento indexados.")
        return count

    def indexar_codigo_projeto(self, max_arquivos: int = 20):
        """Indexa os arquivos .py do projeto."""
        self._init()
        base = Path(__file__).parent
        count = 0
        for py in list(base.glob("*.py"))[:max_arquivos]:
            try:
                conteudo = py.read_text(encoding="utf-8", errors="ignore")
                # Divide por funções/classes para chunks menores
                chunks = self._chunkar_codigo(conteudo, py.name)
                for i, chunk in enumerate(chunks):
                    doc_id = hashlib.md5(chunk.encode()).hexdigest()[:16]
                    self._add_doc(doc_id, chunk, {"fonte": "codigo", "arquivo": py.name, "chunk": i})
                    count += 1
            except Exception:
                pass
        print(f"{Fore.GREEN}  [RAG] {count} chunks de código indexados.")
        return count

    def indexar_texto(self, texto: str, fonte: str = "manual", meta: dict | None = None):
        """Indexa um texto arbitrário."""
        self._init()
        doc_id = hashlib.md5(texto.encode()).hexdigest()[:16]
        self._add_doc(doc_id, texto, {"fonte": fonte, **(meta or {})})
        self._indexado += 1

    def _add_doc(self, doc_id: str, texto: str, meta: dict):
        texto = texto[:2000]  # limita tamanho do chunk
        if self._modo == "chroma":
            try:
                self._colecao.upsert(documents=[texto], ids=[doc_id], metadatas=[meta])
            except Exception:
                pass
        elif self._modo == "faiss":
            vec = self._encoder.encode([texto])
            self._faiss.add(self._np.array(vec).astype("float32"))
            self._textos.append(texto)
        else:
            # keyword: armazena em lista simples
            if not hasattr(self, "_kw_store"):
                self._kw_store = []
            self._kw_store.append(texto)

    # ── busca ─────────────────────────────────────────────────

    def buscar(self, query: str, k: int = 4) -> str:
        """
        Busca contexto relevante para a query.
        Retorna string formatada para incluir no prompt.
        """
        self._init()
        resultados = []

        if self._modo == "chroma" and self._colecao:
            try:
                res = self._colecao.query(query_texts=[query], n_results=min(k, max(1, self._colecao.count())))
                docs = res.get("documents", [[]])[0]
                metas = res.get("metadatas", [[]])[0]
                for doc, meta in zip(docs, metas):
                    fonte = meta.get("fonte","?")
                    resultados.append(f"[{fonte}] {doc[:400]}")
            except Exception:
                pass

        elif self._modo == "faiss" and self._faiss and self._textos:
            try:
                vec = self._encoder.encode([query])
                k_real = min(k, len(self._textos))
                _, I = self._faiss.search(self._np.array(vec).astype("float32"), k_real)
                for i in I[0]:
                    if 0 <= i < len(self._textos):
                        resultados.append(self._textos[i][:400])
            except Exception:
                pass

        else:
            # keyword fallback
            store = getattr(self, "_kw_store", [])
            q_lower = query.lower()
            scored = [(t, sum(1 for w in q_lower.split() if w in t.lower())) for t in store]
            scored.sort(key=lambda x: -x[1])
            resultados = [t[:400] for t, _ in scored[:k] if _ > 0]

        # Também busca na memória MAGI se disponível
        if self.magi and hasattr(self.magi, "memoria"):
            try:
                mem_results = self.magi.memoria.buscar(query, k=2)
                resultados.extend([f"[memória] {m[:300]}" for m in mem_results])
            except Exception:
                pass

        if not resultados:
            return ""

        return "=== CONTEXTO RAG ===\n" + "\n---\n".join(resultados[:k]) + "\n==================="

    def status(self) -> dict:
        self._init()
        base = {"modo": self._modo, "indexados": self._indexado}
        if self._modo == "chroma" and self._colecao:
            base["chroma_docs"] = self._colecao.count()
        elif self._modo == "faiss":
            base["faiss_docs"] = len(self._textos)
        return base

    # ── helpers ───────────────────────────────────────────────

    @staticmethod
    def _chunkar_codigo(conteudo: str, nome_arquivo: str) -> list[str]:
        """Divide código em chunks por função/classe."""
        linhas = conteudo.splitlines()
        chunks, atual = [], []
        for ln in linhas:
            if re.match(r'^(class |def )', ln) and atual:
                chunk_txt = "\n".join(atual)
                if len(chunk_txt) > 50:
                    chunks.append(f"# {nome_arquivo}\n{chunk_txt}")
                atual = [ln]
            else:
                atual.append(ln)
            if len(atual) > 80:
                chunks.append(f"# {nome_arquivo}\n" + "\n".join(atual))
                atual = []
        if atual:
            chunks.append(f"# {nome_arquivo}\n" + "\n".join(atual))
        return chunks[:40]  # máx 40 chunks por arquivo