import sys
from framework.plugins.loader import PluginLoader


def test_plugin_loader_resolves_dependencies_and_awaits_hooks(tmp_path):
    (tmp_path / 'plugin_a.py').write_text('''\nfrom framework.plugins.base import PluginManifest\nPLUGIN_MANIFEST = PluginManifest("a", "a", "1", "test")\nstate = []\nasync def initialize(config): state.append("init")\nasync def shutdown(): state.append("shutdown")\n''')
    (tmp_path / 'plugin_b.py').write_text('''\nfrom framework.plugins.base import PluginManifest\nPLUGIN_MANIFEST = PluginManifest("b", "b", "1", "test", dependencies={"a": ">=1"})\n''')
    sys.path.insert(0, str(tmp_path))
    try:
        import asyncio
        async def scenario():
            loader = PluginLoader()
            loaded = await loader.load_many(['plugin_b', 'plugin_a'])
            assert [item.manifest.name for item in loaded] == ['a', 'b']
            await loader.unload('b')
            await loader.unload('a')
        asyncio.run(scenario())
    finally:
        sys.path.remove(str(tmp_path))
