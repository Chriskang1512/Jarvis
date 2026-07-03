import ast
import operator
from datetime import datetime

from jarvis.permissions import PermissionLevel
from jarvis.tools.contracts import ToolMetadata, ToolResult


class TimeTool:
    """Safe tool that returns the current local time."""

    metadata = ToolMetadata(
        name="time",
        description="Return the current local time.",
        domain="core",
        permission_level=PermissionLevel.SAFE,
        safe=True,
    )

    def execute(self, input_data):
        """Return current local time as text."""
        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output=datetime.now().isoformat(timespec="seconds"),
        )


class CalculatorTool:
    """Safe arithmetic calculator tool."""

    metadata = ToolMetadata(
        name="calculator",
        description="Evaluate a safe arithmetic expression.",
        domain="core",
        permission_level=PermissionLevel.SAFE,
        safe=True,
    )

    def execute(self, input_data):
        """Evaluate an arithmetic expression without eval."""
        expression = str(input_data.get("expression", "")).strip()

        if expression == "":
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error="Calculator expression is required.",
            )

        try:
            value = evaluate_expression(expression)
        except (SyntaxError, ValueError, TypeError, ZeroDivisionError) as error:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=str(error),
            )

        return ToolResult(tool_name=self.metadata.name, success=True, output=value)


class DiagnosticsSummaryTool:
    """Safe tool that summarizes current diagnostics state."""

    metadata = ToolMetadata(
        name="diagnostics",
        description="Return a short diagnostics summary.",
        domain="core",
        permission_level=PermissionLevel.SAFE,
        safe=True,
    )

    def __init__(self, diagnostics_collector=None):
        """Create a diagnostics tool."""
        self.diagnostics_collector = diagnostics_collector

    def execute(self, input_data):
        """Return diagnostics summary text."""
        if self.diagnostics_collector is None:
            return ToolResult(
                tool_name=self.metadata.name,
                success=True,
                output="Diagnostics collector is not connected.",
            )

        snapshot = self.diagnostics_collector.get_snapshot()
        output = {
            "session_id": snapshot.session.session_id,
            "stage": snapshot.pipeline.current_stage,
            "overall": snapshot.health.overall,
            "events": len(snapshot.events),
        }
        return ToolResult(tool_name=self.metadata.name, success=True, output=output)


class MemoryReadTool:
    """Safe tool that reads a value from the current memory service."""

    metadata = ToolMetadata(
        name="memory_read",
        description="Read one value from the current memory service.",
        domain="memory",
        permission_level=PermissionLevel.SAFE,
        safe=True,
    )

    def __init__(self, memory_service=None, memory_manager=None):
        """Create a memory read tool."""
        self.memory_service = memory_service
        self.memory_manager = memory_manager

    def execute(self, input_data):
        """Read one memory key."""
        key = str(input_data.get("key", "")).strip()

        if key == "":
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error="Memory key is required.",
            )

        if self.memory_service is not None:
            value = self.memory_service.recall(key)

            if value != "":
                return ToolResult(
                    tool_name=self.metadata.name,
                    success=True,
                    output=value,
                )

        if self.memory_manager is not None:
            memories = self.memory_manager.search(key)
            return ToolResult(
                tool_name=self.metadata.name,
                success=True,
                output=[memory.to_dict() for memory in memories],
            )

        if self.memory_service is None:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error="Memory service is not connected.",
            )

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            output=self.memory_service.recall(key),
        )


ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

ALLOWED_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def evaluate_expression(expression):
    """Evaluate a safe arithmetic expression."""
    if len(expression) > 80:
        raise ValueError("Expression is too long.")

    node = ast.parse(expression, mode="eval")
    return evaluate_node(node.body)


def evaluate_node(node):
    """Evaluate one AST node for safe arithmetic."""
    if isinstance(node, ast.Constant) and type(node.value) in [int, float]:
        return node.value

    if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_OPERATORS:
        left = evaluate_node(node.left)
        right = evaluate_node(node.right)

        if isinstance(node.op, ast.Pow) and abs(right) > 10:
            raise ValueError("Exponent is too large.")

        return ALLOWED_OPERATORS[type(node.op)](left, right)

    if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_UNARY_OPERATORS:
        value = evaluate_node(node.operand)
        return ALLOWED_UNARY_OPERATORS[type(node.op)](value)

    raise ValueError("Expression contains unsupported syntax.")
