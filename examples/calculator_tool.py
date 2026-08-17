from framework.extensions import tool

@tool("calculator", description="Evaluate a basic arithmetic expression", input_schema={"type": "object", "required": ["expression"], "properties": {"expression": {"type": "string"}}}, output_schema={"type": "number"}, required_permissions={"calculator.execute"}, timeout=2.0)
async def calculator(expression: str):
    import ast
    node = ast.parse(expression, mode="eval").body
    allowed = (ast.Expression, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.BinOp)
    if not all(isinstance(item, allowed) for item in ast.walk(node)) or not all(not isinstance(item, ast.Constant) or isinstance(item.value, (int, float)) for item in ast.walk(node)): raise ValueError("Only numeric arithmetic is supported")
    return _evaluate(node)

def _evaluate(node):
    import ast
    if isinstance(node, ast.Constant): return node.value
    if isinstance(node, ast.UnaryOp): return -_evaluate(node.operand)
    left, right = _evaluate(node.left), _evaluate(node.right)
    if isinstance(node.op, ast.Add): return left + right
    if isinstance(node.op, ast.Sub): return left - right
    if isinstance(node.op, ast.Mult): return left * right
    if isinstance(node.op, ast.Div): return left / right
    raise ValueError("Unsupported operator")
