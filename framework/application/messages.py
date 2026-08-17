from framework.core.engine import FrameworkEngine
from framework.core.models import IncomingMessage, ProcessingContext, RequestContext, ProcessingResult

class MessageApplicationService:
    def __init__(self, engine: FrameworkEngine, middleware=None, hooks=None): self.engine, self.middleware, self.hooks = engine, middleware, hooks
    async def process(self, message: IncomingMessage) -> ProcessingResult:
        context = ProcessingContext(message=message, request=RequestContext(project_id=message.project_id, user_id=message.user_id, channel=message.channel, metadata=dict(message.metadata)), metadata=dict(message.metadata))
        if self.hooks: context = await self.hooks.run("before_message", context)
        async def terminal(current):
            result = await self.engine.process_message(current.message)
            current.metadata["result"] = result
            return current
        if self.middleware: context = await self.middleware.run(context, terminal)
        else: context = await terminal(context)
        if self.hooks: context = await self.hooks.run("after_message", context)
        result = context.metadata.get("result")
        if not isinstance(result, ProcessingResult): raise RuntimeError("Message processing did not produce a ProcessingResult")
        return result
