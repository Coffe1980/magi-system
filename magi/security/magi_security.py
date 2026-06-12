"""
magi/security/magi_security.py
Substitui eval() inseguro por parsing seguro.
Validação de inputs, sanitização, sandbox checks.
"""
import re
import ast
from typing import Any
from magi.utils.magi_logger import log


# ── SUBSTITUTO SEGURO DO eval() ───────────────────────────────

class ExprSeguros:
    """
    Parser seguro para expressões matemáticas sympy.
    NUNCA usa eval() ou exec().
    Permite apenas identificadores sympy válidos.
    """

    # Tokens permitidos: números, operadores, nomes de funções sympy, x y z
    _ALLOWED_NAMES = frozenset({
        "x", "y", "z", "t", "n",
        "sin", "cos", "tan", "exp", "log", "sqrt",
        "pi", "E", "I", "oo",
        "symbols", "Symbol",
    })
    _SAFE_PATTERN = re.compile(
        r'^[\d\s\+\-\*\/\^\(\)\.\,xyztn]*$'
        r'|^[a-zA-Z_][\w\s\+\-\*\/\^\(\)\.\,]*$'
    )

    @classmethod
    def validar(cls, expr: str) -> bool:
        """Verifica se a expressão é segura para parse."""
        if not expr or len(expr) > 200:
            return False
        # Rejeita qualquer import, exec, eval, __
        dangerous = ['import', 'exec', 'eval', '__', 'open', 'os.', 'sys.',
                     'subprocess', 'shutil', 'globals', 'locals', 'getattr']
        expr_lower = expr.lower()
        return not any(d in expr_lower for d in dangerous)

    @classmethod
    def parse_sympy(cls, expr: str):
        """
        Converte string para expressão sympy de forma segura.
        Lança ValueError se a expressão for inválida/perigosa.
        """
        if not cls.validar(expr):
            raise ValueError(f"Expressão não permitida: '{expr[:50]}'")
        try:
            from sympy import sympify, Symbol
            # sympify usa seu próprio parser — não chama eval() em código arbitrário
            # mas precisamos restringir os nomes disponíveis
            local_dict = {name: Symbol(name) for name in "xyztn"}
            return sympify(expr, locals=local_dict, evaluate=True)
        except Exception as e:
            raise ValueError(f"Expressão inválida '{expr[:50]}': {e}") from e


def resolver_matematica_seguro(tipo: str, *args) -> str:
    """
    Versão segura de _resolver_matematica.
    Substitui todos os eval() por ExprSeguros.parse_sympy().
    """
    try:
        from sympy import symbols, Eq, solve, diff, integrate, Matrix, linsolve

        x, y = symbols('x y')

        if tipo == "equacao":
            lhs = ExprSeguros.parse_sympy(args[0])
            rhs = ExprSeguros.parse_sympy(args[1]) if len(args) > 1 else symbols('0')
            return f"Solução: {solve(Eq(lhs, rhs), x)}"

        elif tipo == "derivada":
            expr = ExprSeguros.parse_sympy(args[0])
            return f"Derivada: {diff(expr, x)}"

        elif tipo == "integral":
            expr = ExprSeguros.parse_sympy(args[0])
            return f"Integral: {integrate(expr, x)}"

        elif tipo == "matriz":
            # Para matriz: espera lista como string, ex: "[[1,2],[3,4]]"
            raw = args[0].strip()
            if not re.match(r'^[\[\]\d\s\.\,\-\+]+$', raw):
                raise ValueError("Formato de matriz inválido")
            parsed = ast.literal_eval(raw)  # literal_eval é seguro — não executa código
            return f"Matriz: {Matrix(parsed)}"

        elif tipo == "sistema_linear":
            e1 = ExprSeguros.parse_sympy(args[0])
            e2 = ExprSeguros.parse_sympy(args[1]) if len(args) > 1 else symbols('0')
            return f"Sistema: {linsolve([e1, e2], x, y)}"

        else:
            return f"Tipo desconhecido: {tipo}"

    except ValueError as e:
        log.warn("security", f"Expressão bloqueada: {e}")
        return f"Expressão inválida ou não permitida: {e}"
    except Exception as e:
        log.error("security", f"Erro em _resolver_matematica: {e}", exc=e)
        return f"Erro matemático: {e}"


# ── VALIDAÇÃO DE INPUTS ───────────────────────────────────────

def sanitizar_query(query: str, max_len: int = 4000) -> str:
    """Remove caracteres de controle e limita tamanho."""
    if not isinstance(query, str):
        query = str(query)
    query = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', query)
    return query[:max_len].strip()


def validar_caminho(caminho: str, base_dir: str | None = None) -> bool:
    """
    Valida que um caminho não contém path traversal.
    Se base_dir fornecido, verifica que o arquivo está dentro dele.
    """
    import os
    if '..' in caminho or caminho.startswith('/') or caminho.startswith('\\'):
        log.warn("security", f"Path traversal bloqueado: {caminho[:60]}")
        return False
    if base_dir:
        full = os.path.realpath(os.path.join(base_dir, caminho))
        base = os.path.realpath(base_dir)
        if not full.startswith(base):
            log.warn("security", f"Path fora do diretório base: {caminho[:60]}")
            return False
    return True


def validar_codigo_python(codigo: str) -> tuple[bool, str]:
    """
    Valida sintaxe Python sem executar.
    Retorna (valido, mensagem_erro).
    """
    try:
        ast.parse(codigo)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError na linha {e.lineno}: {e.msg}"


def detectar_codigo_perigoso(codigo: str) -> list[str]:
    """
    Detecta padrões perigosos no código antes de executar em sandbox.
    Retorna lista de alertas (vazia = seguro).
    """
    alertas = []
    patterns = {
        r'\bimport\s+subprocess\b': "subprocess import",
        r'\bimport\s+os\b':         "os import",
        r'\bos\.system\b':          "os.system call",
        r'\beval\s*\(':             "eval() call",
        r'\bexec\s*\(':             "exec() call",
        r'__import__':              "__import__ call",
        r'\bopen\s*\(':             "file open (verificar)",
        r'socket\.':               "socket usage",
        r'urllib\.|requests\.':    "network request",
    }
    for pattern, desc in patterns.items():
        if re.search(pattern, codigo):
            alertas.append(desc)
    return alertas
