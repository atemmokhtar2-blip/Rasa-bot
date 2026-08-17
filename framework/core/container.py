from framework.config import Settings, get_settings
from framework.core.engine import FrameworkEngine
from framework.core.state import SessionManager
from framework.core.persistent_state import PersistentSessionManager
from framework.core.events import EventBus
from framework.core.registries import ActionRegistry, PluginRegistry, ToolRegistry
from framework.nlu.base import RuleBasedNLUProvider
from framework.nlu.rasa import RasaProvider
from framework.nlu.registry import EntityRegistry, IntentRegistry
from framework.developers.service import DeveloperService
from framework.datasets.system import DatasetRegistry
from framework.models.registry import ModelRegistry
from framework.security.policy import FixedWindowRateLimiter, PermissionService, RedisRateLimiter
from framework.security.secrets import EnvironmentSecretProvider, HttpSecretProvider
from framework.observability import AuditLogger, UsageMeter
from framework.observability.metrics import MetricsRegistry
from framework.observability.tracing import configure_tracing
from framework.infrastructure.sql import SQLDatabase
from framework.infrastructure.redis import RedisProvider
from framework.infrastructure.idempotency import RedisIdempotencyStore
from framework.infrastructure.cache import RedisCache
from framework.infrastructure.queue import RedisQueue
from framework.infrastructure.domain_repositories import BotRepository, DatasetRepository, ModelRepository, TrainingJobRepository
from framework.channels.management import BotRegistry, CommandRegistry
from framework.channels.persistent_management import PersistentBotRegistry
from framework.channels.registry import ChannelRegistry
from framework.channels.telegram import TelegramAdapter
from framework.datasets.pipeline import DatasetPipeline
from framework.datasets.artifacts import DatasetArtifactService
from framework.infrastructure.object_storage import ObjectStorageSettings, S3ObjectStorage
from framework.models.evaluation import EvaluationEngine
from framework.models.training import RasaTrainer
from framework.models.artifacts import ModelArtifactService
from framework.models.deployment import ModelDeploymentService
from framework.plugins.runtime import PluginRuntime
from framework.plugins.loader import PluginLoader
from framework.plugins.process_runner import ProcessPluginRunner
from framework.core.integrations import ToolExecutionService, WebhookRegistry
from framework.application.messages import MessageApplicationService
from framework.core.event_delivery import EventSchemaRegistry, QueuedEventPublisher

class ApplicationContainer:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        configure_tracing(self.settings.otel_exporter_endpoint, self.settings.app_name)
        self.secrets = HttpSecretProvider(self.settings.secret_manager_url, self.settings.secret_manager_token) if self.settings.secret_manager_url and self.settings.secret_manager_token else EnvironmentSecretProvider()
        self.database = SQLDatabase(self.settings.database_url) if self.settings.database_url != "memory://" else None
        self.events = EventBus()
        self.event_schemas = EventSchemaRegistry()
        self.actions = ActionRegistry()
        self.tools = ToolRegistry()
        self.plugins = PluginRegistry()
        self.nlu = RasaProvider(self.settings.rasa_endpoint, self.settings.nlu_timeout) if self.settings.rasa_endpoint else RuleBasedNLUProvider()
        self.sessions = PersistentSessionManager(self.database, self.settings.session_timeout_minutes) if self.database else SessionManager(self.settings.session_timeout_minutes)
        self.intents = IntentRegistry()
        self.entities = EntityRegistry()
        self.developers = DeveloperService(self.database, self.settings.api_key_pepper)
        self.datasets = DatasetRegistry()
        self.models = ModelRegistry()
        self.permissions = PermissionService()
        self.redis = RedisProvider(self.settings.redis_url) if self.settings.redis_url else None
        self.idempotency = RedisIdempotencyStore(self.redis) if self.redis else None
        self.rate_limiter = RedisRateLimiter(self.redis, self.settings.rate_limit) if self.redis else FixedWindowRateLimiter(self.settings.rate_limit)
        self.cache = RedisCache(self.redis) if self.redis else None
        self.event_publisher = QueuedEventPublisher(RedisQueue(self.redis.client), self.event_schemas) if self.redis else None
        self.dataset_repository = DatasetRepository(self.database) if self.database else None
        self.model_repository = ModelRepository(self.database) if self.database else None
        self.training_job_repository = TrainingJobRepository(self.database) if self.database else None
        self.bot_repository = BotRepository(self.database) if self.database else None
        self.usage = UsageMeter(self.database)
        self.metrics = MetricsRegistry()
        self.audit = AuditLogger(self.database)
        self.engine = FrameworkEngine(self.nlu, self.events, self.actions, intent_threshold=self.settings.intent_low_threshold, usage=self.usage, audit=self.audit, entities=self.entities, sessions=self.sessions, metrics=self.metrics, idempotency=self.idempotency)
        self.messages = MessageApplicationService(self.engine)
        self.bots = PersistentBotRegistry(self.bot_repository) if self.bot_repository else BotRegistry()
        self.commands = CommandRegistry()
        self.channels = ChannelRegistry()
        self.channels.register("telegram", lambda **kwargs: TelegramAdapter(kwargs.get("token")))
        self.dataset_pipeline = DatasetPipeline()
        self.object_storage = S3ObjectStorage(ObjectStorageSettings(self.settings.s3_endpoint_url, self.settings.s3_bucket, self.settings.s3_region, self.settings.s3_access_key, self.settings.s3_secret_key)) if self.database and self.settings.s3_bucket else None
        self.dataset_artifacts = DatasetArtifactService(self.object_storage, self.database) if self.object_storage and self.database else None
        self.model_artifacts = ModelArtifactService(self.object_storage) if self.object_storage else None
        self.evaluation = EvaluationEngine()
        self.trainer = RasaTrainer()
        self.deployment = ModelDeploymentService(self.model_repository) if self.model_repository else None
        self.plugin_runtime = PluginRuntime(self.settings.plugin_timeout)
        self.plugin_loader = PluginLoader()
        self.process_plugin_runner = ProcessPluginRunner()
        self.tool_execution = ToolExecutionService(self.settings.action_timeout)
        self.webhooks = WebhookRegistry()

    async def startup(self) -> None:
        if self.database:
            await self.database.create_schema()

    async def shutdown(self) -> None:
        if self.database:
            await self.database.dispose()
        if self.redis:
            await self.redis.close()
