import logging
import sys

def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
        stream=sys.stdout,
    )

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not getattr(logger, "_framework_adapter", False):
        class RequestAdapter(logging.LoggerAdapter):
            def process(self, msg, kwargs):
                extra = kwargs.setdefault("extra", {})
                extra.setdefault("request_id", "-")
                return msg, kwargs
        adapted = RequestAdapter(logger, {})
        setattr(adapted, "_framework_adapter", True)
        return adapted
    return logger
