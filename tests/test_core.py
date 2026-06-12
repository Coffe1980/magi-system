"""
magi/tests/test_core.py
Testes básicos para os módulos core.
Execute: python -m pytest magi/tests/ -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest


# ── magi_config ───────────────────────────────────────────────

def test_config_importa():
    from magi.core.magi_config import NUCLEOS, LOCAL_CONFIG, OPENROUTER_CONFIG
    assert isinstance(NUCLEOS, dict)
    assert len(NUCLEOS) >= 3
    assert "MELCHIOR-1" in NUCLEOS
    assert "BALTHASAR-2" in NUCLEOS
    assert "CASPER-3" in NUCLEOS


def test_config_nucleos_tem_campos_obrigatorios():
    from magi.core.magi_config import NUCLEOS
    for nome, cfg in NUCLEOS.items():
        assert "system"  in cfg, f"{nome} sem system"
        assert "model"   in cfg, f"{nome} sem model"
        assert "backend" in cfg, f"{nome} sem backend"


def test_config_local_config():
    from magi.core.magi_config import LOCAL_CONFIG
    assert "ativo"  in LOCAL_CONFIG
    assert "url"    in LOCAL_CONFIG
    assert "modelo" in LOCAL_CONFIG


# ── magi_logger ───────────────────────────────────────────────

def test_logger_cria_sem_arquivo():
    from magi.utils.magi_logger import MAGILogger
    logger = MAGILogger(log_path="/tmp/test_magi.jsonl", console=False)
    logger.info("teste", "mensagem de teste")
    logger.warn("teste", "aviso de teste")
    logger.error("teste", "erro de teste")
    # Não deve levantar exceção


def test_logger_capture():
    from magi.utils.magi_logger import MAGILogger
    logger = MAGILogger(log_path="/tmp/test_magi.jsonl", console=False)
    try:
        raise ValueError("erro de teste")
    except ValueError as e:
        logger.capture("teste", e, "contexto de teste")


def test_logger_tail():
    from magi.utils.magi_logger import MAGILogger
    logger = MAGILogger(log_path="/tmp/test_magi_tail.jsonl", console=False)
    for i in range(5):
        logger.info("teste", f"msg {i}")
    lines = logger.tail_plain(n=10, level="INFO")
    assert isinstance(lines, list)


# ── magi_security ─────────────────────────────────────────────

def test_security_eval_bloqueado():
    from magi.security.magi_security import ExprSeguros
    # Expressões perigosas devem ser bloqueadas
    assert not ExprSeguros.validar("__import__('os').system('rm -rf /')")
    assert not ExprSeguros.validar("import subprocess")
    assert not ExprSeguros.validar("exec('print(1)')")


def test_security_expr_matematica_valida():
    from magi.security.magi_security import ExprSeguros
    assert ExprSeguros.validar("x**2 + 2*x + 1")
    assert ExprSeguros.validar("sin(x) + cos(x)")


def test_security_resolver_matematica():
    from magi.security.magi_security import resolver_matematica_seguro
    r = resolver_matematica_seguro("derivada", "x**2")
    assert "2" in r  # derivada de x² = 2x


def test_security_validar_codigo_python():
    from magi.security.magi_security import validar_codigo_python
    ok, msg = validar_codigo_python("def foo():\n    return 42\n")
    assert ok
    assert msg == ""
    ok2, msg2 = validar_codigo_python("def foo(:\n    pass")
    assert not ok2
    assert msg2 != ""


def test_security_detectar_codigo_perigoso():
    from magi.security.magi_security import detectar_codigo_perigoso
    alertas = detectar_codigo_perigoso("import os\nos.system('ls')")
    assert len(alertas) > 0


def test_security_sanitizar_query():
    from magi.security.magi_security import sanitizar_query
    q = sanitizar_query("  olá\x00mundo  ")
    assert "\x00" not in q
    assert q == "olámundo"


# ── magi_llm (sem chamadas reais de API) ─────────────────────

def test_llm_router_cria():
    from magi.ai.magi_llm import LLMRouter
    router = LLMRouter()
    assert router is not None
    assert router._openai_client is None  # lazy — não inicializado ainda


def test_llm_router_sem_key_retorna_none():
    from magi.ai.magi_llm import LLMRouter
    import magi.core.magi_config as cfg
    orig = cfg.OPENAI_API_KEY
    cfg.OPENAI_API_KEY = ""
    router = LLMRouter()
    result = router.chamar_openai("gpt-4o-mini", "test", "test")
    cfg.OPENAI_API_KEY = orig
    # Sem key deve retornar None sem levantar exceção
    assert result is None


# ── magi_evolution ────────────────────────────────────────────

def test_evolution_validar_codigo():
    from magi.security.magi_security import validar_codigo_python
    codigo_bom = "class Foo:\n    def bar(self):\n        return 42\n"
    codigo_ruim = "class Foo\n    pass"
    assert validar_codigo_python(codigo_bom)[0] is True
    assert validar_codigo_python(codigo_ruim)[0] is False


def test_evolution_chunkar_codigo():
    from skill_rag import MAGIRAG
    chunks = MAGIRAG._chunkar_codigo("class A:\n    def x(self):\n        pass\n\ndef b():\n    pass", "test.py")
    assert len(chunks) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
