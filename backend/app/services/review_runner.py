from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from app.llm.ollama import OllamaError

T = TypeVar("T")


def run_with_ollama_retries(
    operation: Callable[[], T],
    *,
    attempts: int,
    retry_delay_seconds: float = 1.0,
    on_retry: Callable[[int, int, OllamaError], None] | None = None,
) -> T:
    """Run one bounded local-model operation with a finite retry budget."""

    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    last_error: OllamaError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except OllamaError as error:
            last_error = error
            if attempt >= attempts:
                break
            if on_retry is not None:
                on_retry(attempt, attempts, error)
            if retry_delay_seconds > 0:
                time.sleep(retry_delay_seconds)

    assert last_error is not None
    raise last_error
