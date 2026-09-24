"""Shared HTTP client construction for future evidence/provider adapters."""

from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class HttpAdapterBase:
    """Safe defaults shared by explicit outbound-service adapters.

    Concrete PubMed, Crossref, OCR, and model adapters will own their request
    semantics. This class deliberately makes no network request by itself.
    """

    service_name: str
    timeout_seconds: float = 10.0

    def build_client(self) -> httpx.AsyncClient:
        """Return a bounded client without automatic redirect following."""

        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=False,
        )
