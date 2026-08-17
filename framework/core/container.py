from framework.config import Settings, get_settings
from framework.core.engine import FrameworkEngine
from framework.core.state import SessionManager
from framework.core.persistent_state import PersistentSessionManager
from framework.core.events import EventBus
from framework.core.registries import ActionRegistry, PluginRegistry, ToolRegistry
from framework.nlu.base import RuleBasedNLUProvider
from framework.nlu.registry import EntityRegistry, IntentRegistry
from framework.developers.service import DeveloperService
from framework.datasets.system import DatasetRegistry
from framework.models.registry import ModelRegistry
from framework.security.policy import FixedWindowRateLimiter, PermissionService, RedisRateLimiter
from framework.observability import AuditLogger, UsageMeter
from framework.infrastructure.sql import SQLDatabase
from framework.infrastructure.redis import RedisProvider
from framework.infrastructure.cache import RedisCache
from framework.infrastructure.domain_repositories import BotRepository, DatasetRepository, ModelRepository, TrainingJobRepository
from framework.channels.management import BotRegistry, CommandRegistry
from framework.channels.persistent_management import PersistentBotRegistry
from framework.datasets.pipeline import DatasetPipeline
from framework.models.evaluation import EvaluationEngine
from framework.models.training import RasaTrainer
from framework.models.deployment import ModelDeploymentService
from framework.plugins.runtime import PluginRuntime
from framework.plugins.loader import PluginLoader
from framework.plugins.process_runner import ProcessPluginRunner
from framework.core.integrations import ToolExecutionService, WebhookRegistry

class ApplicationContainer:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.database = SQLDatabase(self.settings.database_url) if self.settings.database_url != "memory://" else None
        self.events = EventBus()
        self.actions = ActionRegistry()
        self.tools = ToolRegistry()
        self.plugins = PluginRegistry()
        self.nlu = RuleBasedNLUProvider()
        self.sessions = PersistentSessionManager(self.database) if self.database else SessionManager()
        self.intents = IntentRegistry()
        self.entities = EntityRegistry()
        self.developers = DeveloperService(self.database, self.settings.api_key_pepper)
        self.datasets = DatasetRegistry()
        self.models = ModelRegistry()
        self.permissions = PermissionService()
        self.redis = RedisProvider(self.settings.redis_url) if self.settings.redis_url else None
        self.rate_limiter = RedisRateLimiter(self.redis) if self.redis else FixedWindowRateLimiter()
        self.cache = RedisCache(self.redis) if self.redis else None
        self.dataset_repository = DatasetRepository(self.database) if self.database else None
        self.model_repository = ModelRepository(self.database) if self.database else None
        self.training_job_repository = TrainingJobRepository(self.database) if self.database else None
        self.bot_repository = BotRepository(self.database) if self.database else None
        self.usage = UsageMeter(self.database)
        self.audit = AuditLogger(self.database)
        self.engine = FrameworkEngine(self.nlu, self.events, self.actions, usage=self.usage, audit=self.audit, entities=self.entities, sessions=self.sessions)
        self.bots = PersistentBotRegistry(self.bot_repository) if self.bot_repository else BotRegistry()
        self.commands = CommandRegistry()
        self.dataset_pipeline = DatasetPipeline()
        self.evaluation = EvaluationEngine()
        self.trainer = RasaTrainer()
        self.deployment = ModelDeploymentService(self.model_repository) if self.model_repository else None
        self.plugin_runtime = PluginRuntime()
        self.plugin_loader = PluginLoader()
        self.process_plugin_runner = ProcessPluginRunner()
        self.tool_execution = ToolExecutionService()
        self.webhooks = WebhookRegistry()

    async def startup(self) -> None:
        if self.database:
            await self.database.create_schema()

    async def shutdown(self) -> None:
        if self.database:
            await self.database.dispose()
        if self.redis:
            await self.redis.close()
