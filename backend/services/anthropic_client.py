"""Anthropic API client singleton with retry and circuit breaker."""

import logging
import os
import threading
import time
from typing import Optional

import anthropic as _anthropic_module
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 529}

_anthropic_client_singleton: Optional[Anthropic] = None


def get_anthropic_client() -> Anthropic:
    global _anthropic_client_singleton
    if _anthropic_client_singleton is None:
        _anthropic_client_singleton = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _anthropic_client_singleton


# ── Circuit breaker ──────────────────────────────────────────────────────────
_CB_FAILURE_THRESHOLD = 5
_CB_RECOVERY_TIMEOUT = 60

_cb_lock = threading.Lock()
_cb_failure_count = 0
_cb_state = "closed"
_cb_opened_at: float = 0.0


def _cb_record_success() -> None:
    global _cb_failure_count, _cb_state
    with _cb_lock:
        _cb_failure_count = 0
        _cb_state = "closed"


def _cb_record_failure() -> None:
    global _cb_failure_count, _cb_state, _cb_opened_at
    with _cb_lock:
        _cb_failure_count += 1
        if _cb_failure_count >= _CB_FAILURE_THRESHOLD:
            _cb_state = "open"
            _cb_opened_at = time.monotonic()
            logger.error(
                "Circuit breaker OPEN after %d consecutive Anthropic API failures; "
                "blocking requests for %ds",
                _cb_failure_count, _CB_RECOVERY_TIMEOUT,
            )


def _cb_allow_request() -> bool:
    global _cb_state
    with _cb_lock:
        if _cb_state == "closed":
            return True
        if _cb_state == "open":
            if time.monotonic() - _cb_opened_at >= _CB_RECOVERY_TIMEOUT:
                _cb_state = "half_open"
                logger.info("Circuit breaker HALF-OPEN — allowing probe request")
                return True
            return False
        return True


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is open and blocking requests."""


def anthropic_create(**kwargs):
    """Wrapper around messages.create with retry and circuit breaker."""
    if not _cb_allow_request():
        raise CircuitBreakerOpenError(
            "Anthropic API circuit breaker is open due to repeated failures. "
            f"Retry in {_CB_RECOVERY_TIMEOUT}s."
        )

    delays = [5, 15, 30]
    for attempt, delay in enumerate(delays + [None]):
        try:
            result = get_anthropic_client().messages.create(**kwargs)
            _cb_record_success()
            return result
        except _anthropic_module.APIStatusError as e:
            if e.status_code in _RETRYABLE_STATUS_CODES and delay is not None:
                logger.warning(
                    "Anthropic API %s (attempt %d/%d), retrying in %ds…",
                    e.status_code, attempt + 1, len(delays), delay,
                )
                time.sleep(delay)
            else:
                _cb_record_failure()
                raise
        except _anthropic_module.APIConnectionError as e:
            if delay is not None:
                logger.warning(
                    "Anthropic API %s (attempt %d/%d), retrying in %ds…",
                    type(e).__name__, attempt + 1, len(delays), delay,
                )
                time.sleep(delay)
            else:
                _cb_record_failure()
                raise
        except _anthropic_module.APITimeoutError:
            _cb_record_failure()
            raise
    _cb_record_failure()
