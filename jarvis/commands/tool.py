from jarvis.commands.base import BaseCommand
from jarvis.events.types import JarvisStatus
from jarvis.tools import ToolRequest


class ToolCommand(BaseCommand):
    """Command that executes a registered safe tool."""

    name = "tool"
    description = "Execute a registered safe tool."

    def execute(self, context):
        """Execute one tool through the ToolDispatcher."""
        if context.tool_dispatcher is None:
            self.publish_status(context, JarvisStatus.ERROR, "Tool dispatcher is not available")
            return "Tool dispatcher is not available."

        lookup_output = handle_tool_lookup(context)

        if lookup_output != "":
            self.publish_status(context, JarvisStatus.SUCCESS, "Tool registry lookup completed")
            return lookup_output

        tool_name, input_data = parse_tool_command(context.command_text)

        if tool_name == "":
            self.publish_status(context, JarvisStatus.ERROR, "Tool name is required")
            return "Usage: tool <name> [input] | tool list | tool domains | tool domain <name>"

        self.publish_status(context, JarvisStatus.WORKING, f"Tool requested: {tool_name}")
        result = context.tool_dispatcher.execute(
            ToolRequest(
                tool_name=tool_name,
                input_data=input_data,
            )
        )

        if not result.success:
            self.publish_status(context, JarvisStatus.ERROR, "Tool execution failed")
            return f"Tool failed: {result.error}"

        self.publish_status(context, JarvisStatus.SUCCESS, "Tool execution completed")
        return format_tool_output(result.output)


def parse_tool_command(command_text):
    """Parse tool command text into tool name and input data."""
    parts = command_text.strip().split(maxsplit=1)

    if len(parts) == 0:
        return "", {}

    tool_name = parts[0].lower()
    raw_input = ""

    if len(parts) > 1:
        raw_input = parts[1].strip()

    if tool_name == "calculator":
        return tool_name, {"expression": raw_input}

    if tool_name == "memory_read":
        return tool_name, {"key": raw_input}

    return tool_name, {"text": raw_input}


def handle_tool_lookup(context):
    """Return registry lookup output for non-executing tool commands."""
    command_text = context.command_text.strip()

    if command_text == "list":
        return format_tool_list(context.tool_dispatcher.registry.list())

    if command_text == "domains":
        return format_domain_list(context.tool_dispatcher.registry.list_domains())

    if command_text.startswith("domain "):
        domain = command_text.split(maxsplit=1)[1].strip()
        return format_tool_list(context.tool_dispatcher.registry.list_by_domain(domain))

    return ""


def format_tool_list(tools):
    """Format a list of tool metadata for the CLI."""
    if len(tools) == 0:
        return "No tools found."

    lines = ["Tools"]

    for tool in tools:
        metadata = tool.metadata
        lines.append(f"{metadata.domain}.{metadata.name} - {metadata.description}")

    return "\n".join(lines)


def format_domain_list(domains):
    """Format registered tool domains for the CLI."""
    if len(domains) == 0:
        return "No tool domains found."

    return "\n".join(["Tool Domains"] + domains)


def format_tool_output(output):
    """Format tool output for the CLI."""
    if isinstance(output, dict):
        return "\n".join([f"{key}: {value}" for key, value in output.items()])

    return str(output)
