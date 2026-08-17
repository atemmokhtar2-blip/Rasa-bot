from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

_configured = False

def configure_tracing(endpoint: str | None, service_name: str) -> None:
    global _configured
    if _configured or not endpoint: return
    provider = TracerProvider(resource=Resource.create({'service.name': service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider); _configured = True

@contextmanager
def span(name: str, attributes: dict | None = None):
    tracer = trace.get_tracer('ai-developer-framework')
    with tracer.start_as_current_span(name, attributes=attributes or {}) as current:
        yield current
