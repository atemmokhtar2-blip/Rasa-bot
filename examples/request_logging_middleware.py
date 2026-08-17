import time

class RequestLoggingMiddleware:
    name = "request_logging"
    def __init__(self, logger): self.logger = logger
    async def __call__(self, context, next_handler):
        started = time.perf_counter()
        result = await next_handler(context)
        self.logger.info("extension_request", extra={"request_id": context.request.request_id, "project_id": context.message.project_id, "endpoint": context.metadata.get("endpoint"), "latency_ms": (time.perf_counter() - started) * 1000, "extension": self.name})
        return result
