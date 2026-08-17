from framework.config import Settings, get_settings
from framework.core.engine import FrameworkEngine
from framework.core.events import EventBus
from framework.core.registries import ActionRegistry, PluginRegistry, ToolRegistry
from framework.nlu.base import RuleBasedNLUProvider
from framework.developers.service import DeveloperService

class ApplicationContainer:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.events = EventBus()
        self.actions = ActionRegistry()
        self.tools = ToolRegistry()
        self.plugins = PluginRegistry()
        self.nlu = RuleBasedNLUProvider()
        self.engine = FrameworkEngine(self.nlu, self.events, self.actions)
        self.developers = DeveloperService()

    async def startup(self) -> None: pass
    async def shutdown(self) -> None: pass
