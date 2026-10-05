"""Optional tool (Module 22): a SAFE calculator (no eval) usable by Explainer & Evaluator."""
import ast
import operator

from crewai.tools import tool

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        if isinstance(node.op, ast.Pow) and abs(_eval(node.right)) > 100:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


def safe_calc(expression: str) -> str:
    try:
        return str(_eval(ast.parse(expression.strip(), mode="eval").body))
    except Exception as exc:
        return f"Calculator error: {exc}"


@tool("Calculator")
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression such as '(3 + 4) * 2 / 5'. Use it for any exact number work."""
    return safe_calc(expression)
