from framework.plugins.base import PluginManifest
from framework.extensions import action, tool

PLUGIN_MANIFEST = PluginManifest(plugin_id="orders_plugin", name="Orders Plugin", version="1.0.0", author="Framework", description="Specification 05 example extension", permissions={"messages.read", "actions.register", "tools.register", "storage.read", "storage.write"}, configuration_schema={"properties": {"orders": {"type": "object"}}})
_orders = {"ord_1": {"id": "ord_1", "status": "processing"}}

@tool("list_orders", description="List orders", output_schema={"type": "array"}, required_permissions={"storage.read"})
async def list_orders(**kwargs): return list(_orders.values())

@tool("get_order_status", description="Get order status", input_schema={"type": "object", "required": ["order_id"], "properties": {"order_id": {"type": "string"}}}, output_schema={"type": "object"}, required_permissions={"storage.read"})
async def get_order_status(order_id: str): return _orders.get(order_id, {"id": order_id, "status": "not_found"})

@action("cancel_order", description="Cancel an order", required_permissions={"storage.write"})
async def cancel_order(context):
    order_id = context.metadata.get("order_id")
    if order_id in _orders: _orders[order_id]["status"] = "cancelled"
    return {"id": order_id, "status": "cancelled"}

ACTIONS = [cancel_order]
TOOLS = [list_orders, get_order_status]
async def initialize(context): return None
async def shutdown(): return None
