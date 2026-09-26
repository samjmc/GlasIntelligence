"""One asyncio event loop on a daemon thread, for sync callers of async libraries.

Graphiti and the Neo4j async driver are async-only, and the driver is bound to
the loop that created it. Every caller here is a sync Flask or worker thread, so
they all submit coroutines to this single long-lived loop. Never call
``asyncio.run`` per request: that would create a new loop each time.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


class AsyncBridge:
    def __init__(self, name: str = "graph-store-loop") -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name=name, daemon=True)
        self._thread.start()

    def run(self, coro: Coroutine[Any, Any, T], timeout: float | None = None) -> T:
        """Run ``coro`` on the bridge loop and block until it finishes (or ``timeout`` seconds)."""
        if threading.current_thread() is self._thread:
            raise RuntimeError("AsyncBridge.run called from its own loop thread; await the coroutine instead")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout)
        except TimeoutError:
            future.cancel()
            raise

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
