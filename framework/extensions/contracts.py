from __future__ import annotations
import inspect
from typing import Any
from framework.extensions.providers import NLUProvider, ModelProvider, StorageProvider, SessionProvider, ChannelProvider

async def assert_provider_contract(provider: Any) -> dict[str, Any]:
    required = {
        "nlu": (NLUProvider, ("parse", "health")),
        "model": (ModelProvider, ("load", "unload", "predict", "health", "metadata")),
        "storage": (StorageProvider, ("get", "set", "delete", "list", "health")),
        "session": (SessionProvider, ("get_session", "create_session", "update_session", "delete_session", "health")),
        "channel": (ChannelProvider, ("normalize", "send", "health")),
    }
    kind = getattr(provider, "provider_type", None)
    if kind not in required: raise AssertionError(f"Unknown provider_type: {kind}")
    interface, methods = required[kind]
    if not isinstance(provider, interface): raise AssertionError(f"Provider does not implement {interface.__name__}")
    missing = [method for method in methods if not callable(getattr(provider, method, None))]
    if missing: raise AssertionError(f"Provider contract missing methods: {missing}")
    if not isinstance(await provider.health(), dict): raise AssertionError("Provider health must return dict")
    return {"provider": getattr(provider, "name", provider.__class__.__name__), "type": kind, "methods": list(methods), "valid": True}


def provider_contract_test(provider_factory):
    async def run(): return await assert_provider_contract(provider_factory())
    return run
