"""In-memory ring buffer of recent log records, exposed via /admin/logs.

Single-process by design — same constraint as RunRegistry. For real
multi-worker deployments you'd switch to a shared sink (Loki, journald,
or an OTel logs pipeline); at demo scale a deque on app.state is the
minimum-viable thing that lets the UI surface what uvicorn already prints.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from itertools import count
from typing import Iterable

from pydantic import BaseModel


class LogEntry(BaseModel):
    id: int
    ts: str  # ISO 8601 with millisecond precision
    level: str  # "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL"
    logger: str
    message: str


_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class RingBufferHandler(logging.Handler):
    """Stores the most recent N log records. Drops oldest on overflow.
    Thread-safe — Python's logging framework can call emit() from worker
    threads (httpx, asyncio executor, etc.)."""

    def __init__(self, capacity: int = 500, level: int = logging.INFO) -> None:
        super().__init__(level=level)
        self._buf: deque[LogEntry] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._counter = count(1)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = LogEntry(
                id=next(self._counter),
                ts=self.formatter.formatTime(record, "%Y-%m-%dT%H:%M:%S")  # type: ignore[union-attr]
                if self.formatter
                else "",
                level=record.levelname,
                logger=record.name,
                message=record.getMessage(),
            )
        except Exception:  # noqa: BLE001 — never let logging crash the producer
            self.handleError(record)
            return
        with self._lock:
            self._buf.append(entry)

    def snapshot(self, *, min_level: str = "INFO", limit: int = 200) -> list[LogEntry]:
        """Return up to `limit` most-recent entries at or above `min_level`,
        newest first. Filtering happens here (not server-side SQL) because the
        buffer lives in memory and `min_level` is rarely set."""
        threshold = _LEVELS.get(min_level.upper(), logging.INFO)
        with self._lock:
            entries: Iterable[LogEntry] = reversed(self._buf)
        out: list[LogEntry] = []
        for e in entries:
            if _LEVELS.get(e.level, logging.NOTSET) < threshold:
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out


def install(capacity: int = 500) -> RingBufferHandler:
    """Attach the buffer to the root logger. Idempotent — calling twice
    (uvicorn --reload triggers lifespan twice in dev) replaces the handler
    instead of stacking duplicates."""
    root = logging.getLogger()
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)
    for h in list(root.handlers):
        if isinstance(h, RingBufferHandler):
            root.removeHandler(h)
    handler = RingBufferHandler(capacity=capacity)
    handler.setFormatter(logging.Formatter())  # default — only used for ts
    root.addHandler(handler)
    return handler
