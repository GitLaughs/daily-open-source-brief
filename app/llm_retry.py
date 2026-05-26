from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, TypeVar


F = TypeVar("F", bound=Callable[..., Any])


def retry_on_transient(max_retries: int = 2, base_delay: float = 1.0, backoff: float = 2.0) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: RuntimeError | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except RuntimeError as exc:
                    last_exc = exc
                    if not is_transient(str(exc)) or attempt == max_retries:
                        raise
                    time.sleep(base_delay * (backoff**attempt))
            raise last_exc or RuntimeError("retry failed")

        return wrapper  # type: ignore[return-value]

    return decorator


def is_transient(error_msg: str) -> bool:
    text = error_msg.lower()
    return any(marker in text for marker in ["timeout", "429", "500", "502", "503", "504", "rate limit", "connection"])
