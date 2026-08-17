from framework.config import Settings, get_settings
from framework.core.engine import FrameworkEngine
from framework.core.state import SessionManager
from framework.core.persistent_state import PersistentSessionManager
from framework.core.events import EventBus
from framework.core.registries import ActionRegistry, PluginRegistry, ToolRegistry, ProviderRegistry, PolicyRegistry, MiddlewareRegistry, HookRegistry
from framework.nlu.base import RuleBasedNLUProvider
from framework.nlu.rasa import RasaProvider
from framework.nlu.registry import EntityRegistry, IntentRegistry
from framework.developers.service import DeveloperService
from framework.datasets.system import DatasetRegistry
from framework.models.registry import ModelRegistry
from framework.security.policy import FixedWindowRateLimiter, PermissionService, RedisRateLimiter
from framework.security.secrets import EnvironmentSecretProvider, HttpSecretProvider, InMemorySecretProvider
from framework.security.webhook_secrets import WebhookSecretCipher
from framework.observability import AuditLogger, UsageMeter
from framework.observability.quota import QuotaService
from framework.observability.metrics import MetricsRegistry
from framework.observability.tracing import configure_tracing
from framework.infrastructure.sql import SQLDatabase, WebhookSubscriptionORM
from framework.infrastructure.redis import RedisProvider
from framework.infrastructure.idempotency import RedisIdempotencyStore
from framework.infrastructure.cache import RedisCache
from framework.infrastructure.queue import RedisQueue
from framework.infrastructure.domain_repositories import BotRepository, DatabaseDatasetLoader, DatasetCatalogRepository, DatasetRepository, ModelRepository, TrainingJobRepository, WebhookRepository, WebhookDeliveryLogRepository
from framework.channels.management import BotRegistry, CommandRegistry
from framework.channels.persistent_management import PersistentBotRegistry
from framework.channels.registry import ChannelRegistry
from framework.channels.telegram import TelegramAdapter
from framework.datasets.pipeline import DatasetPipeline
from framework.datasets.artifacts import DatasetArtifactService
from framework.infrastructure.object_storage import ObjectStorageSettings, S3ObjectStorage
from framework.models.comparison import ModelComparator
from framework.models.evaluation import EvaluationEngine
from framework.models.runtime import ModelRuntimeService
from framework.models.thresholds import ThresholdOptimizer
from framework.models.training import RasaTrainingProvider
from framework.models.artifacts import ModelArtifactService
from framework.models.deployment import ModelDeploymentService
from framework.training import TrainingQueue, LocalArtifactStore, ModelRouter, ConfigurableQualityGate, DeploymentManager
from framework.learning.continuous import InteractionCollectionService
from framework.learning.review import HumanReviewService
from framework.learning.policy import FeedbackService, ContinuousTrainingOrchestrator, ProductionPromotionPolicy
from framework.plugins.runtime import PluginRuntime
from framework.plugins.process_runner import ProcessPluginRunner
from framework.plugins.loader import PluginLoader
from framework.plugins.manager import ExtensionManager
from framework.core.integrations import ToolExecutionService, WebhookRegistry, QueuedWebhookDispatcher
from framework.application.messages import MessageApplicationService
from framework.core.event_delivery import EventSchemaRegistry, QueuedEventPublisher
from framework.core.middleware import MiddlewarePipeline
from framework.extensions.hooks import HookManager
from framework.extensions.providers import CoreNLUAdapter, ExtensionNLUAdapter

class ApplicationContainer:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        configure_tracing(self.settings.otel_exporter_endpoint, self.settings.app_name)
        self.secrets = HttpSecretProvider(self.settings.secret_manager_url, self.settings.secret_manager_token) if self.settings.secret_manager_url and self.settings.secret_manager_token else EnvironmentSecretProvider()
        self.bot_secrets = InMemorySecretProvider()
        self.database = SQLDatabase(self.settings.database_url) if self.settings.database_url != "memory://" else None
        self.events = EventBus()
        self.event_schemas = EventSchemaRegistry()
        self.actions = ActionRegistry()
        self.tools = ToolRegistry()
        self.plugins = PluginRegistry()
        self.providers = ProviderRegistry()
        self.policies = PolicyRegistry()
        self.middleware = MiddlewarePipeline()
        self.hooks = HookManager()
        self.plugin_loader = PluginLoader(framework_version=self.settings.app_version)
        self.extensions = ExtensionManager(loader=self.plugin_loader, actions=self.actions, tools=self.tools, providers=self.providers, policies=self.policies, event_bus=self.events, secrets=self.secrets, plugin_registry=self.plugins)
        self.nlu = RasaProvider(self.settings.rasa_endpoint, self.settings.nlu_timeout) if self.settings.rasa_endpoint else RuleBasedNLUProvider()
        self.nlu.name = "rasa" if self.settings.rasa_endpoint else "rule-based"
        self.nlu.version = self.settings.app_version
        self.nlu.provider_type = "nlu"
        self.nlu_provider = CoreNLUAdapter(self.nlu, self.nlu.name)
        self.providers.register(self.nlu_provider)
        self.sessions = PersistentSessionManager(self.database, self.settings.session_timeout_minutes) if self.database else SessionManager(self.settings.session_timeout_minutes)
        self.intents = IntentRegistry()
        self.entities = EntityRegistry()
        self.developers = DeveloperService(self.database, self.settings.api_key_pepper)
        self.datasets = DatasetRegistry()
        self.models = ModelRegistry()
        self.training_queue = TrainingQueue()
        self.training_jobs_memory: dict[str, dict] = {}
        self.learning = InteractionCollectionService(low_confidence_threshold=self.settings.intent_low_threshold)
        self.reviews = HumanReviewService()
        self.feedback = FeedbackService()
        self.continuous_training = ContinuousTrainingOrchestrator()
        self.promotion_policy = ProductionPromotionPolicy()
        self.artifact_store = LocalArtifactStore(self.settings.training_artifact_root)
        self.model_router = ModelRouter()
        self.quality_gate = ConfigurableQualityGate()
        self.deployment_manager = DeploymentManager(self.model_router, self.artifact_store)
        self.permissions = PermissionService()
        self.redis = RedisProvider(self.settings.redis_url) if self.settings.redis_url else None
        self.idempotency = RedisIdempotencyStore(self.redis) if self.redis else None
        self.rate_limiter = RedisRateLimiter(self.redis, self.settings.rate_limit) if self.redis else FixedWindowRateLimiter(self.settings.rate_limit)
        self.cache = RedisCache(self.redis) if self.redis else None
        self.event_publisher = QueuedEventPublisher(RedisQueue(self.redis.client), self.event_schemas) if self.redis else None
        self.dataset_catalog_repository = DatasetCatalogRepository(self.database) if self.database else None
        self.dataset_repository = DatasetRepository(self.database) if self.database else None
        self.model_repository = ModelRepository(self.database) if self.database else None
        self.training_job_repository = TrainingJobRepository(self.database) if self.database else None
        self.bot_repository = BotRepository(self.database) if self.database else None
        self.webhook_repository = WebhookRepository(self.database) if self.database else None
        self.webhook_delivery_log_repository = WebhookDeliveryLogRepository(self.database) if self.database else None
        self.webhook_cipher = WebhookSecretCipher(self.settings.api_key_pepper)
        self.usage = UsageMeter(self.database)
        self.quotas = QuotaService(self.usage, self.developers.get_project)
        self.metrics = MetricsRegistry()
        self.audit = AuditLogger(self.database)
        self.extensions.audit = self.audit
        self.engine = FrameworkEngine(self.nlu, self.events, self.actions, intent_threshold=self.settings.intent_low_threshold, tools=self.tools, usage=self.usage, audit=self.audit, entities=self.entities, sessions=self.sessions, metrics=self.metrics, idempotency=self.idempotency, project_resolver=self.developers.get_project, allow_project_fallback=self.settings.app_env not in {"production", "staging"})
        self.messages = MessageApplicationService(self.engine, middleware=self.middleware, hooks=self.hooks)
        self.bots = PersistentBotRegistry(self.bot_repository) if self.bot_repository else BotRegistry()
        self.commands = CommandRegistry()
        self.channels = ChannelRegistry()
        self.channels.register("telegram", lambda **kwargs: TelegramAdapter(kwargs.get("token")))
        self.dataset_pipeline = DatasetPipeline()
        self.object_storage = S3ObjectStorage(ObjectStorageSettings(self.settings.s3_endpoint_url, self.settings.s3_bucket, self.settings.s3_region, self.settings.s3_access_key, self.settings.s3_secret_key)) if self.database and self.settings.s3_bucket else None
        self.dataset_artifacts = DatasetArtifactService(self.object_storage, self.database) if self.object_storage and self.database else None
        self.model_artifacts = ModelArtifactService(self.object_storage) if self.object_storage else None
        self.evaluation = EvaluationEngine()
        self.threshold_optimizer = ThresholdOptimizer()
        self.model_comparator = ModelComparator()
        self.runtime = ModelRuntimeService(self.model_repository, rasa_endpoint=self.settings.rasa_endpoint, router=self.model_router)
        self.trainer = RasaTrainingProvider()
        self.dataset_loader = DatabaseDatasetLoader(self.dataset_repository) if self.dataset_repository else None
        self.deployment = ModelDeploymentService(self.model_repository) if self.model_repository else None
        self.plugin_runtime = PluginRuntime(self.settings.plugin_timeout)
        self.process_plugin_runner = ProcessPluginRunner()
        self.tool_execution = ToolExecutionService(self.settings.action_timeout)
        self.webhooks = WebhookRegistry()
        self.webhook_dispatcher = QueuedWebhookDispatcher(RedisQueue(self.redis.client)) if self.redis else None
        self.events.subscribe("*", self._dispatch_webhook_event)

    async def _dispatch_webhook_event(self, event) -> None:
        if not self.webhook_dispatcher or not event.project_id: return
        envelope = {"event_id": event.event_id, "event": event.name, "request_id": event.request_id, "trace_id": event.trace_id, "project_id": event.project_id, "timestamp": event.timestamp.isoformat(), "payload": event.payload}
        for subscription in self.webhooks.for_event(event.name, event.project_id):
            await self.webhook_dispatcher.enqueue(subscription, envelope)

    async def startup(self) -> None:
        if self.database:
            await self.database.create_schema()
            if self.webhook_repository:
                for row in await self.webhook_repository.list_all():
                    try:
                        from framework.core.integrations import WebhookSubscription
                        self.webhooks.register(WebhookSubscription(row.event_name, row.url, self.webhook_cipher.decrypt(row.secret_ciphertext), row.timeout_seconds, row.max_retries, dict(row.metadata_json or {})))
                    except Exception:
                        continue

    def resolve_provider(self, provider_type: str, *, name: str | None = None, project_id: str | None = None, environment: str | None = None):
        return self.providers.resolve_provider(provider_type, name=name, project_id=project_id, environment=environment)

    def set_nlu_provider(self, provider) -> None:
        if not hasattr(provider, "analyze"):
            if not hasattr(provider, "parse"): raise TypeError("NLU provider must expose analyze or parse")
            provider = ExtensionNLUAdapter(provider)
        self.nlu = provider
        self.engine.nlu = provider

    async def shutdown(self) -> None:
        if self.database:
            await self.database.dispose()
        if self.runtime:
            await self.runtime.close()
        if self.redis:
            await self.redis.close()
