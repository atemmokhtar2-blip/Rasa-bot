from __future__ import annotations
from framework.plugins.base import PluginManifest
from framework.extensions import action, tool

PLUGIN_MANIFEST = PluginManifest(plugin_id="telegram_utilities", name="Telegram Utilities", version="1.0.0", author="Framework", description="First-party Telegram helpers built on the public Extension SDK", permissions={"events.subscribe", "messages.read"}, trust_level="first-party")

@tool("telegram_format_message", description="Format a Telegram-safe message", input_schema={"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}, output_schema={"type": "object"}, required_permissions={"messages.read"})
async def telegram_format_message(text: str):
    return {"text": text[:4096], "parse_mode": "HTML" if "<" in text and ">" in text else None}

@action("telegram_status", description="Report Telegram channel availability", required_permissions={"messages.read"})
async def telegram_status(context):
    return {"channel": "telegram", "status": "available", "project_id": getattr(getattr(context, "project", None), "id", None) or getattr(getattr(context, "project", None), "project_id", None)}

ACTIONS = [telegram_status]
TOOLS = [telegram_format_message]

async def initialize(context):
    async def on_message(event):
        return None
    context.events.subscribe("message.received", on_message)

async def shutdown():
    return None
