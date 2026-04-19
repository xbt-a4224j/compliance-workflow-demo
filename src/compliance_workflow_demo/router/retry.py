from __future__ import annotations

from dataclasses import dataclass

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from compliance_workflow_demo.router.types import TransientError


@dataclass(frozen=True)
class RetryPolicy:
    """Tenacity wrapper that only retries TransientError.

    Exponential backoff with jitter (not plain exponential) — see CLAUDE.md
    landmine table: synchronized retries without jitter create thundering herds.
    """

    max_attempts: int = 3
    initial_wait_s: float = 0.25
    max_wait_s: float = 4.0
    jitter_s: float = 0.25

    def attempts(self) -> AsyncRetrying:
        return AsyncRetrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential_jitter(
                initial=self.initial_wait_s,
                max=self.max_wait_s,
                jitter=self.jitter_s,
            ),
            retry=retry_if_exception_type(TransientError),
            reraise=True,
        )
