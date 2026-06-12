"""
magi/ai/magi_llm.py
Camada única de chamadas LLM — desacoplada de todas as classes.
Substitui os 4 métodos _chamar_* espalhados pelo God Class.
"""
import os, time
from typing import Optional
from magi.utils.magi_logger import log
from magi.core.magi_config import (
    LOCAL_CONFIG, OPENROUTER_CONFIG, NUCLEOS,
    OPENAI_API_KEY, GOOGLE_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY,
    MAX_RETRIES_API, OPENROUTER_TIMEOUT,
)


class LLMRouter:
    """
    Roteador de chamadas LLM com fallback automático.
    Ordem: local → openrouter → openai → google → anthropic
    Thread-safe (instâncias de client criadas uma vez).
    """

    def __init__(self):
        self._openai_client   = None
        self._google_client   = None
        self._openrouter_client = None
        self._local_client    = None
        self._ultimo_erro: dict[str, str] = {}

    # ── lazy client creation ──────────────────────────────────

    def _get_openai(self):
        if self._openai_client is None:
            if not OPENAI_API_KEY:
                return None
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=OPENAI_API_KEY)
            except ImportError:
                log.warn("llm", "openai não instalado")
        return self._openai_client

    def _get_google(self):
        if self._google_client is None:
            if not GOOGLE_API_KEY:
                return None
            try:
                from google import genai
                self._google_client = genai.Client(api_key=GOOGLE_API_KEY)
            except ImportError:
                log.warn("llm", "google-genai não instalado")
        return self._google_client

    def _get_openrouter(self):
        if self._openrouter_client is None:
            if not OPENROUTER_API_KEY:
                return None
            try:
                from openai import OpenAI
                self._openrouter_client = OpenAI(
                    base_url=OPENROUTER_CONFIG["url"],
                    api_key=OPENROUTER_API_KEY,
                    default_headers={
                        "HTTP-Referer": "https://github.com/MAGI-NERV",
                        "X-Title": "MAGI System",
                    },
                )
            except ImportError:
                log.warn("llm", "openai não instalado (necessário para openrouter)")
        return self._openrouter_client

    def _get_local(self):
        if self._local_client is None:
            if not LOCAL_CONFIG["ativo"]:
                return None
            try:
                from openai import OpenAI
                self._local_client = OpenAI(
                    base_url=LOCAL_CONFIG["url"],
                    api_key="local",
                )
            except ImportError:
                pass
        return self._local_client

    # ── chamadas individuais ──────────────────────────────────

    def chamar_local(self, system: str, prompt: str) -> str | None:
        client = self._get_local()
        if not client:
            return None
        t0 = time.time()
        try:
            res = client.chat.completions.create(
                model=LOCAL_CONFIG["modelo"],
                messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
                temperature=0.7,
                timeout=120,
            )
            txt = (res.choices[0].message.content or "").strip()
            if not txt:
                return None
            log.info("llm.local", "OK", ms=int((time.time()-t0)*1000))
            return txt
        except Exception as e:
            self._ultimo_erro["local"] = f"{type(e).__name__}: {e}"
            log.warn("llm.local", self._ultimo_erro["local"])
            return None

    def chamar_openrouter(self, system: str, prompt: str,
                          modelo: str | None = None, timeout: int = OPENROUTER_TIMEOUT) -> str | None:
        client = self._get_openrouter()
        if not client:
            return None
        modelos = [
            modelo or OPENROUTER_CONFIG["modelo"],
            *OPENROUTER_CONFIG["fallbacks"],
        ]
        modelos = list(dict.fromkeys(modelos))  # deduplica mantendo ordem

        for m in modelos:
            t0 = time.time()
            try:
                res = client.chat.completions.create(
                    model=m,
                    messages=[{"role":"system","content":system[:8000]},
                               {"role":"user","content":prompt[:50000]}],
                    temperature=0.7,
                    timeout=timeout,
                )
                txt = (res.choices[0].message.content or "").strip()
                if not txt:
                    continue
                log.info("llm.openrouter", "OK", model=m, ms=int((time.time()-t0)*1000))
                return txt
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                self._ultimo_erro["openrouter"] = f"[{m}] {err}"
                # 429: tenta esperar se retry_after for curto
                if "429" in str(e):
                    import re
                    m_retry = re.search(r'retry_after_seconds["\': ]+([0-9.]+)', str(e))
                    wait = float(m_retry.group(1)) if m_retry else 0
                    if 0 < wait <= 10:
                        log.warn("llm.openrouter", f"{m} rate-limited, aguardando {wait:.0f}s")
                        time.sleep(wait)
                        try:
                            res2 = client.chat.completions.create(
                                model=m,
                                messages=[{"role":"system","content":system[:8000]},
                                          {"role":"user","content":prompt[:50000]}],
                                temperature=0.7, timeout=timeout,
                            )
                            txt = (res2.choices[0].message.content or "").strip()
                            if txt:
                                return txt
                        except Exception:
                            pass
                log.warn("llm.openrouter", err, model=m)
                continue
        return None

    def chamar_openai(self, model: str, system: str, prompt: str) -> str | None:
        client = self._get_openai()
        if not client:
            return None
        t0 = time.time()
        try:
            res = client.chat.completions.create(
                model=model,
                messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
                temperature=0.7,
            )
            txt = (res.choices[0].message.content or "").strip()
            if not txt:
                return None
            log.info("llm.openai", "OK", model=model, ms=int((time.time()-t0)*1000))
            return txt
        except Exception as e:
            self._ultimo_erro["openai"] = f"{type(e).__name__}: {e}"
            log.warn("llm.openai", self._ultimo_erro["openai"], model=model)
            return None

    def chamar_google(self, model: str, system: str, prompt: str,
                      json_mode: bool = False) -> str | None:
        client = self._get_google()
        if not client:
            return None
        t0 = time.time()
        try:
            from google.genai import types as genai_types
            cfg_kw: dict = {}
            if json_mode:
                cfg_kw["response_mime_type"] = "application/json"
            res = client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.7,
                    **cfg_kw,
                ),
            )
            txt = (res.text or "").strip()
            if not txt:
                return None
            log.info("llm.google", "OK", model=model, ms=int((time.time()-t0)*1000))
            return txt
        except Exception as e:
            self._ultimo_erro["google"] = f"{type(e).__name__}: {e}"
            log.warn("llm.google", self._ultimo_erro["google"], model=model)
            return None

    def chamar_anthropic(self, system: str, prompt: str,
                         model: str = "claude-sonnet-4-20250514") -> str | None:
        if not ANTHROPIC_API_KEY:
            return None
        t0 = time.time()
        try:
            import anthropic as _anthropic
            client = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model=model, max_tokens=4096,
                system=system[:8000],
                messages=[{"role":"user","content":prompt[:50000]}],
            )
            txt = (msg.content[0].text or "").strip()
            log.info("llm.anthropic", "OK", model=model, ms=int((time.time()-t0)*1000))
            return txt
        except ImportError:
            log.warn("llm.anthropic", "anthropic não instalado")
            return None
        except Exception as e:
            self._ultimo_erro["anthropic"] = f"{type(e).__name__}: {e}"
            log.warn("llm.anthropic", self._ultimo_erro["anthropic"])
            return None

    # ── chamada de núcleo MAGI ────────────────────────────────

    def chamar_nucleo(self, nome: str, prompt: str) -> tuple[str | None, str | None]:
        """
        Chama um núcleo MAGI pelo nome.
        Retorna (resposta, modelo_usado).
        """
        cfg = NUCLEOS.get(nome)
        if not cfg:
            log.error("llm.nucleo", f"Núcleo desconhecido: {nome}")
            return None, None

        system = cfg["system"]
        backend = cfg.get("backend", "google")

        if backend == "openrouter":
            if LOCAL_CONFIG["ativo"]:
                r = self.chamar_local(system, prompt)
                if r:
                    return r, f"local/{LOCAL_CONFIG['modelo']}"
            r = self.chamar_openrouter(system, prompt, modelo=cfg["model"])
            if r:
                return r, cfg["model"]

        elif backend == "openai":
            r = self.chamar_openai(cfg["model"], system, prompt)
            if r:
                return r, cfg["model"]

        else:  # google
            if LOCAL_CONFIG["ativo"]:
                r = self.chamar_local(system, prompt)
                if r:
                    return r, f"local/{LOCAL_CONFIG['modelo']}"
            r = self.chamar_google(cfg["model"], system, prompt)
            if r:
                return r, cfg["model"]
            fb = cfg.get("fallback")
            if fb:
                r = self.chamar_google(fb, system, prompt)
                if r:
                    return r, fb

        # Fallback OpenAI universal
        fb_model  = cfg.get("fallback_openai_model")
        fb_system = cfg.get("fallback_openai_system")
        if fb_model and fb_system:
            r = self.chamar_openai(fb_model, fb_system, prompt)
            if r:
                return r, f"fallback/{fb_model}"

        log.warn("llm.nucleo", f"{nome}: todos os backends falharam")
        return None, None

    def ultimo_erro(self, backend: str) -> str:
        return self._ultimo_erro.get(backend, "")


# Instância global
llm = LLMRouter()
