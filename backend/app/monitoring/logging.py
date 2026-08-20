"""结构化日志 + trace_id 关联

设计要点：
- JSON 单行输出，便于 Docker / 未来 Loki 采集与检索
- trace_id 经 ContextVar 贯穿一次请求内的全部日志（中间件/路由/后台任务）
- 上游已带 X-Trace-Id 则沿用，可与网关/前端日志串联
"""

import json
import logging
import sys
from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


class _TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "trace_id": getattr(record, "trace_id", "-"),
                "msg": record.getMessage(),
                "exc": self.formatException(record.exc_info) if record.exc_info else None,
            },
            ensure_ascii=False,
        )


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(_TraceIdFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
