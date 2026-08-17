# Specification 05 Extension SDK

## Public API version

The public extension contract is versioned as `extension_api_version = "1"`. Public contracts include `ExtensionContext`, `PluginManifest`, `@action`, `@tool`, provider interfaces, `MiddlewarePipeline`, `EventBus`, and `HookManager`.

## Actions and tools

```python
from framework.extensions import action, tool

@tool("get_weather", description="Read weather", required_permissions={"network.outbound"}, input_schema={"type": "object", "required": ["location"]})
async def get_weather(location: str):
    return {"location": location, "temperature": 20}

@action("answer_weather", description="Format a weather response", timeout=5)
async def answer_weather(context):
    return {"text": "Weather is ready"}
```

Every extension has an explicit version, schema, timeout, permissions, metadata, and scope. Duplicate registrations are rejected unless `override=True` is explicitly used.

## Plugin manifest and lifecycle

A plugin exports `PLUGIN_MANIFEST` and optionally `initialize`, `shutdown`, `ACTIONS`, `TOOLS`, `PROVIDERS`, and `POLICIES`. The loader performs discovery, manifest validation, framework compatibility checks, dependency resolution, initialization, activation, and rollback on activation failure. Lifecycle statuses are `discovered`, `validated`, `loaded`, `initialized`, `active`, `unhealthy`, `disabled`, and `unloaded`.

## Safe context

Plugins receive `ExtensionContext`, not raw database connections, filesystem roots, internal providers, or plaintext secrets. Storage is automatically project-prefixed. Secret access requires the explicit `secrets.read` permission. Background work must use `context.tasks` so shutdown can cancel tracked tasks.

## Providers

Custom NLU, model, storage, session, and channel implementations implement the corresponding provider interface and return framework objects. `FakeNLUProvider`, `FakeModelProvider`, `FakeStorageProvider`, `FakeSessionProvider`, and `FakeTelegramProvider` are available for local contract testing.

## Events and middleware

Middleware is registered with an explicit priority and can be marked security-critical. Security middleware fails closed; noncritical middleware failures are isolated. Events include event ID, type, version, timestamp, project, request, trace, payload, and metadata. Event handlers are project-scoped, ordered, bounded-retry, and isolated from noncritical main execution.

## Testing

Use `MockContext`, `provider_contract`, and `extension_contract` to test extensions without production infrastructure. The repository's extension tests cover lifecycle, permissions, duplicate registration, provider replacement, middleware ordering, event failure isolation, project scope, and secret protection.
