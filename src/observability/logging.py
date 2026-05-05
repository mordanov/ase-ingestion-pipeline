import logging
import sys
from contextvars import ContextVar

import structlog

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def bind_trace_id(trace_id: str) -> None:
    _trace_id_var.set(trace_id)
    structlog.contextvars.bind_contextvars(trace_id=trace_id)


def get_trace_id() -> str:
    return _trace_id_var.get()


def configure_logging(level: str = "INFO") -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    return structlog.get_logger(name)
