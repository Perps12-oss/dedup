"""
DEDUP Error handling utilities - Structured logging and controlled degradation.

Use these to replace broad except Exception blocks with explicit failure contracts
and consistent logging. Part of the refactor foundation (Stage 0).
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Tuple, Type, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def log_exceptions(
    logger: logging.Logger,
    re_raise: bool = True,
    message: str = "Exception in {func_name}: {exc}",
) -> Callable[[F], F]:
    """Decorator to log any exception raised by the function."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.exception(
                    message.format(func_name=func.__name__, exc=e),
                    exc_info=True,
                )
                if re_raise:
                    raise
                return None

        return wrapper  # type: ignore[return-value]

    return decorator


class degrade_on_error:
    """
    Context manager that suppresses specified exceptions and logs a warning.

    Use when a non-critical operation may fail and the caller can proceed
    with a default. The context manager does not return a value; the caller
    should initialize a result variable to the default before the block and
    assign the real result inside the block. If an exception is raised,
    the exception is suppressed and the result variable keeps its initial
    (default) value.

    Example:
        result = []  # default
        with degrade_on_error([], logger, (OSError, ValueError)):
            result = fetch_list_from_disk()
        # result is either the list or [] on error
    """

    def __init__(
        self,
        default_value: Any,
        logger: logging.Logger,
        exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    ):
        self.default = default_value
        self.logger = logger
        self.exceptions = exceptions

    def __enter__(self) -> list:
        """Return a single-element list pre-filled with the default. Caller can mutate [0]."""
        return [self.default]

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        traceback: Any,
    ) -> bool:
        if exc_type is None:
            return False
        if issubclass(exc_type, self.exceptions):
            self.logger.warning(
                "Degraded operation (using default): %s",
                exc_val,
                exc_info=True,
            )
            return True  # suppress exception
        return False


def return_on_error(
    default: Any,
    logger: logging.Logger,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[[F], F]:
    """
    Decorator that returns a default value when specified exceptions are raised.

    Use for non-critical paths where degrading to a default is acceptable
    (e.g. loading optional config). Logs a warning and returns default
    instead of raising.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                logger.warning(
                    "Degraded: %s returned default due to %s: %s",
                    func.__name__,
                    type(e).__name__,
                    e,
                )
                return default

        return wrapper  # type: ignore[return-value]

    return decorator
