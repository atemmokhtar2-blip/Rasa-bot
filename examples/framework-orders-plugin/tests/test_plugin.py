from framework_orders_plugin import PLUGIN_MANIFEST

def test_manifest():
    assert PLUGIN_MANIFEST.plugin_id == "orders_plugin"
    assert PLUGIN_MANIFEST.extension_api_version == "1"
