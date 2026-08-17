import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from framework.core.events import EventBus, FrameworkEvent
from framework.core.middleware import MiddlewarePipeline
from framework.core.registries import ActionRegistry, ToolRegistry, ProviderRegistry
from framework.extensions import action, tool, FakeNLUProvider
from framework.extensions.context import SecretFacade
from framework.errors import AuthorizationError, ValidationError, PluginError
from framework.plugins.base import PluginManifest
from framework.plugins.loader import PluginLoader

async def _action_handler(context): return {"ok": True}
async def _tool_handler(value: str): return value

def test_versioned_duplicate_and_project_scope_resolution():
    registry = ActionRegistry()
    global_action = action("status", version="1.0.0")(_action_handler)
    project_action = action("status", version="2.0.0", scope="project", project_id="p1")(_action_handler)
    registry.register(global_action); registry.register(project_action)
    assert registry.resolve("status", project_id="p1").version == "2.0.0"
    assert registry.resolve("status", project_id="p2").version == "1.0.0"
    with pytest.raises(ValidationError): registry.register(action("status", version="1.0.0")(_action_handler))

def test_action_tool_permissions_and_schema():
    async def scenario():
        tool_item = tool("echo", input_schema={"type": "object", "required": ["value"]}, required_permissions={"tools.register"})(_tool_handler)
        with pytest.raises(AuthorizationError): await tool_item.execute(value="x")
        assert await tool_item.execute(value="x", _permissions={"tools.register"}) == "x"
    asyncio.run(scenario())

def test_event_failure_isolation_retry_and_project_scope():
    async def scenario():
        bus = EventBus(); called=[]
        async def failing(event): raise RuntimeError("bad")
        async def good(event): called.append(event.project_id)
        bus.subscribe("message.processed", failing, project_id="p1", max_attempts=2)
        bus.subscribe("message.processed", good, project_id="p1")
        event = FrameworkEvent("MESSAGE_PROCESSED", {}, project_id="p1")
        await bus.emit(event)
        assert called == ["p1"] and event.payload["handler_errors"]
        await bus.emit(FrameworkEvent("MESSAGE_PROCESSED", {}, project_id="p2"))
        assert called == ["p1"]
    asyncio.run(scenario())

def test_middleware_priority_and_noncritical_failure():
    async def scenario():
        pipeline = MiddlewarePipeline(); order=[]
        async def first(ctx, nxt): order.append("first"); return await nxt(ctx)
        async def failed(ctx, nxt): raise RuntimeError("noncritical")
        async def terminal(ctx): order.append("terminal"); return ctx
        pipeline.register("terminal-adjacent", first, priority=20); pipeline.register("failed", failed, priority=10)
        await pipeline.run(SimpleNamespace(message=SimpleNamespace(project_id="p"), metadata={}, timings={}), terminal)
        assert order == ["first", "terminal"]
    asyncio.run(scenario())

def test_secret_facade_requires_explicit_permission():
    with pytest.raises(AuthorizationError): SecretFacade(SimpleNamespace(get=lambda _: "secret"), set()).get("x")
    assert SecretFacade(SimpleNamespace(get=lambda _: "secret"), {"secrets.read"}).get("x") == "secret"

def test_fake_provider_is_core_independent():
    async def scenario():
        result = await FakeNLUProvider().parse(SimpleNamespace(text="/start"))
        assert result.intent.name == "start"
    asyncio.run(scenario())

def test_plugin_loader_version_and_rollback(tmp_path: Path):
    module = tmp_path / "broken_plugin.py"
    module.write_text('from framework.plugins.base import PluginManifest\nPLUGIN_MANIFEST=PluginManifest("broken", "broken", "1.0.0", "test")\nasync def initialize(context): raise RuntimeError("boom")\n')
    sys.path.insert(0, str(tmp_path))
    try:
        async def scenario():
            with pytest.raises(PluginError): await PluginLoader().load("broken_plugin")
        asyncio.run(scenario())
    finally: sys.path.remove(str(tmp_path)); sys.modules.pop("broken_plugin", None)


def test_extension_manager_activation_and_unload():
    from framework.plugins.manager import ExtensionManager
    from framework.core.registries import PluginRegistry, PolicyRegistry
    from framework.core.events import EventBus
    from framework.security.secrets import InMemorySecretProvider
    async def scenario():
        from framework.plugins.loader import PluginLoader
        actions, tools, providers, policies = ActionRegistry(), ToolRegistry(), ProviderRegistry(), PolicyRegistry()
        loader = PluginLoader(); manager = ExtensionManager(loader=loader, actions=actions, tools=tools, providers=providers, policies=policies, event_bus=EventBus(), secrets=InMemorySecretProvider(), plugin_registry=PluginRegistry())
        loaded = await manager.load("framework.extensions.first_party.telegram_utilities")
        assert loaded.status == "active" and actions.resolve("telegram_status") and tools.resolve("telegram_format_message")
        await manager.unload(loaded.manifest.plugin_id)
        assert not loader.list() and not actions.resolve("telegram_status")
    asyncio.run(scenario())


def test_spec05_definition_of_done_e2e_without_rasa():
    from framework.core.engine import FrameworkEngine
    from framework.core.models import OutgoingResponse
    from framework.extensions.providers import ExtensionNLUAdapter
    from framework.extensions.testing import FakeTelegramProvider
    async def scenario():
        actions, tools = ActionRegistry(), ToolRegistry(); bus = EventBus(); seen=[]
        @tool("lookup_customer", required_permissions={"tools.lookup"})
        async def lookup_customer(customer_id: str): return {"id": customer_id, "status": "active"}
        @action("support", required_permissions={"actions.execute"})
        async def support(context):
            customer = await context.tools.call("lookup_customer", customer_id="c1")
            return OutgoingResponse(text=f"customer:{customer['status']}")
        tools.register(lookup_customer); actions.register(support)
        async def event_handler(event): seen.append(event.event_type)
        bus.subscribe("message.processed", event_handler)
        engine = FrameworkEngine(ExtensionNLUAdapter(FakeNLUProvider()), bus, actions, tools=tools)
        pipeline = MiddlewarePipeline(); order=[]
        async def middleware(context, nxt): order.append("middleware.before"); result = await nxt(context); order.append("middleware.after"); return result
        pipeline.register("support-middleware", middleware, priority=10)
        from framework.application.messages import MessageApplicationService
        service = __import__("framework.application.messages", fromlist=["MessageApplicationService"]).MessageApplicationService(engine, middleware=pipeline)
        telegram = FakeTelegramProvider(); message = await telegram.normalize({"message": {"from": {"id": "u1"}, "chat": {"id": "c1"}, "text": "/support"}}, project_id="p1")
        message.metadata["permissions"] = ["actions.execute", "tools.lookup"]
        result = await service.process(message)
        assert result.response.text == "customer:active"
        assert order == ["middleware.before", "middleware.after"] and "message.processed" in seen
        await telegram.send(result.response, recipient_id="c1")
        assert telegram.sent[-1][1] == ["customer:active"]
    asyncio.run(scenario())


def test_extension_health_api_does_not_expose_secrets():
    from fastapi.testclient import TestClient
    from framework.api.app import app
    with TestClient(app) as client:
        response = client.get("/health/extensions")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert all("secret" not in str(item).lower() and "token" not in str(item).lower() for item in body["data"]["plugins"])


def test_extension_lookup_and_event_dispatch_overhead():
    import time
    registry = ToolRegistry()
    async def handler(value: str): return value
    for index in range(1000): registry.register(tool(f"perf_tool_{index}")(handler))
    started = time.perf_counter()
    for index in range(10000): assert registry.resolve(f"perf_tool_{index % 1000}") is not None
    lookup_seconds = time.perf_counter() - started
    assert lookup_seconds < 1.0
    async def scenario():
        bus = EventBus(); count = 0
        async def handler_event(event):
            nonlocal count; count += 1
        bus.subscribe("perf.event", handler_event)
        started = time.perf_counter()
        for _ in range(1000): await bus.emit(FrameworkEvent("PERF_EVENT", {}, project_id="p"))
        assert count == 1000 and (time.perf_counter() - started) < 1.0
    asyncio.run(scenario())


def test_plugin_cli_scaffold(tmp_path):
    from framework.cli import main
    assert main(["plugin", "init", "sample_plugin", "--directory", str(tmp_path)]) == 0
    root = tmp_path / "sample_plugin"
    assert (root / "pyproject.toml").exists() and (root / "README.md").exists() and (root / "sample_plugin" / "__init__.py").exists()


def test_deprecation_contract():
    import warnings
    from framework.extensions import deprecated
    @deprecated("old API", replacement="new API", version="2")
    def old_api(): return True
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        assert old_api() is True
    assert captured and "new API" in str(captured[0].message)


def test_canonical_extension_metrics_render():
    from framework.observability.metrics import MetricsRegistry
    metrics = MetricsRegistry(); metrics.extension_started("action", "a", project_id="p")
    metrics.extension_finished("action", "a", 2.5, project_id="p")
    metrics.extension_started("tool", "t", project_id="p")
    metrics.extension_finished("tool", "t", 1.0, status="error", project_id="p")
    rendered = metrics.render()
    assert "action_execution_count" in rendered and "tool_execution_count" in rendered
    assert "action_latency_ms_count" in rendered and "tool_latency_ms_count" in rendered
    assert "extension_errors_total" in rendered


def test_active_resource_blocks_unload_until_cleanup():
    from framework.extensions.context import ResourceRegistry
    class Resource:
        closed = False
        async def aclose(self): self.closed = True
    resources = ResourceRegistry(); resource = resources.register("connection", Resource())
    assert resources.count() == 1
    async def scenario():
        await resources.close_all()
        assert resources.count() == 0 and resource.closed
    asyncio.run(scenario())


def test_all_provider_contracts():
    from framework.extensions.contracts import assert_provider_contract
    from framework.extensions.providers import FakeNLUProvider, FakeModelProvider, FakeStorageProvider, FakeSessionProvider, ChannelProvider
    class Channel(ChannelProvider):
        provider_type = "channel"; name = "fake-channel"; version = "1.0.0"
        async def normalize(self, payload, *, project_id): return payload
        async def send(self, response, *, recipient_id): return True
        async def health(self): return {"status": "ready", "provider": self.name, "version": self.version, "details": {}}
    async def scenario():
        results = []
        for provider in [FakeNLUProvider(), FakeModelProvider(), FakeStorageProvider(), FakeSessionProvider(), Channel()]: results.append(await assert_provider_contract(provider))
        assert len(results) == 5 and all(item["valid"] for item in results)
    asyncio.run(scenario())


def test_network_facade_requires_outbound_permission():
    from framework.extensions.context import NetworkFacade, ResourceRegistry
    from framework.errors import AuthorizationError
    async def scenario():
        with pytest.raises(AuthorizationError): await NetworkFacade(set(), ResourceRegistry()).get("https://example.com")
    asyncio.run(scenario())


def test_extension_manager_blocks_active_resource_unload():
    from framework.plugins.manager import ExtensionManager
    from framework.core.registries import PluginRegistry, PolicyRegistry
    from framework.core.events import EventBus
    from framework.security.secrets import InMemorySecretProvider
    from framework.errors import PluginError
    class Resource:
        closed = False
        async def aclose(self): self.closed = True
    async def scenario():
        actions, tools, providers, policies = ActionRegistry(), ToolRegistry(), ProviderRegistry(), PolicyRegistry()
        manager = ExtensionManager(loader=__import__("framework.plugins.loader", fromlist=["PluginLoader"]).PluginLoader(), actions=actions, tools=tools, providers=providers, policies=policies, event_bus=EventBus(), secrets=InMemorySecretProvider(), plugin_registry=PluginRegistry())
        loaded = await manager.load("framework.extensions.first_party.telegram_utilities")
        resource = loaded.context.resources.register("socket", Resource())
        with pytest.raises(PluginError): await manager.unload(loaded.manifest.plugin_id)
        await loaded.context.resources.close_all()
        await manager.unload(loaded.manifest.plugin_id)
        assert resource.closed
    asyncio.run(scenario())
