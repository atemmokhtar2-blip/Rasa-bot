import asyncio
import json
import sys
from framework.errors import PluginError

class ProcessPluginRunner:
    def __init__(self, timeout_seconds: float = 10.0): self.timeout_seconds = timeout_seconds
    async def call(self, module: str, operation: str, payload: dict) -> dict:
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', module, operation, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdin = json.dumps(payload).encode()
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(stdin), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            process.kill(); await process.wait(); raise PluginError(f'Plugin process timed out: {module}') from exc
        if process.returncode != 0: raise PluginError(stderr.decode(errors='replace')[-4000:])
        try: return json.loads(stdout)
        except json.JSONDecodeError as exc: raise PluginError('Plugin process returned invalid JSON') from exc
