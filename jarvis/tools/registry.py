from jarvis.tools.safe_tools import (
    CalculatorTool,
    DiagnosticsSummaryTool,
    MemoryReadTool,
    TimeTool,
)


class ToolRegistry:
    """Store and look up available tools."""

    def __init__(self):
        """Create an empty tool registry."""
        self.tools = {}

    def register(self, tool):
        """Register one tool by metadata name."""
        self.tools[tool.metadata.name] = tool

    def get(self, tool_name):
        """Return one tool by name, or None when unavailable."""
        return self.tools.get(tool_name)

    def list(self):
        """Return all registered tools sorted by name."""
        return [self.tools[name] for name in sorted(self.tools)]

    def list_by_domain(self, domain):
        """Return all tools in one domain sorted by name."""
        return [
            tool
            for tool in self.list()
            if tool.metadata.domain == domain
        ]

    def list_domains(self):
        """Return all registered tool domains sorted by name."""
        return sorted({tool.metadata.domain for tool in self.tools.values()})

    def exists(self, tool_name):
        """Return whether a tool is registered."""
        return tool_name in self.tools


def create_default_tool_registry(diagnostics_collector=None, memory_service=None, memory_manager=None, config=None):
    """Create the default registry with safe built-in tools."""
    registry = ToolRegistry()
    registry.register(TimeTool())
    registry.register(CalculatorTool())
    registry.register(DiagnosticsSummaryTool(diagnostics_collector=diagnostics_collector))
    registry.register(MemoryReadTool(memory_service=memory_service, memory_manager=memory_manager))
    register_default_abilities(registry, config=config)
    return registry


def register_default_abilities(registry, config=None):
    """Register built-in abilities through ToolRouter-compatible adapters."""
    from jarvis.abilities import AbilityRegistry
    from jarvis.abilities.integration.n8n import N8nIntegrationAbility
    from jarvis.abilities.native.calendar import CalendarAbility
    from jarvis.abilities.native.calendar.provider import create_calendar_provider
    from jarvis.abilities.native.contacts import ContactAbility
    from jarvis.abilities.native.mail import MailAbility
    from jarvis.abilities.native.memory import MemoryAbility
    from jarvis.abilities.native.reminder import ReminderAbility
    from jarvis.abilities.native.todo import TodoAbility
    from jarvis.abilities.native.weather import WeatherAbility
    from jarvis.abilities.native.weather.provider import create_weather_provider
    from jarvis.config.loader import ConfigurationLoader
    from jarvis.core.events import InMemoryEventBus, ReminderScheduleHandler
    from jarvis.core.todos import TodoRepository
    from jarvis.native.reminder.registry import get_default_reminder_engine

    runtime_config = config or ConfigurationLoader().load()
    weather_provider = create_weather_provider(runtime_config.weather)
    calendar_provider = create_calendar_provider(runtime_config.calendar)
    reminder_engine = get_default_reminder_engine()
    todo_event_bus = InMemoryEventBus()
    todo_event_bus.subscribe("TodoCreated", ReminderScheduleHandler(reminder_engine, event_bus=todo_event_bus))
    todo_event_bus.subscribe("TodoUpdated", ReminderScheduleHandler(reminder_engine, event_bus=todo_event_bus))
    todo_event_bus.subscribe("TodoCompleted", ReminderScheduleHandler(reminder_engine, event_bus=todo_event_bus))
    todo_event_bus.subscribe("TodoDeleted", ReminderScheduleHandler(reminder_engine, event_bus=todo_event_bus))

    contact_ability = ContactAbility(config=getattr(runtime_config, "contacts", None))
    ability_registry = AbilityRegistry()
    ability_registry.register(CalendarAbility(provider=calendar_provider, reminder_engine=reminder_engine))
    ability_registry.register(contact_ability)
    ability_registry.register(
        MailAbility(
            config=getattr(runtime_config, "mail", None),
            contacts_provider=getattr(contact_ability, "provider", None),
        )
    )
    ability_registry.register(TodoAbility(repository=TodoRepository(event_bus=todo_event_bus)))
    ability_registry.register(WeatherAbility(provider=weather_provider))
    ability_registry.register(MemoryAbility())
    ability_registry.register(ReminderAbility(engine=reminder_engine))
    ability_registry.register(N8nIntegrationAbility())
    ability_registry.register_tools(registry)
