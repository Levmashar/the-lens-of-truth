"""Outbound-service adapter boundary.

Concrete adapters are intentionally deferred until their owning implementation
phase. Routes and future pipeline code must not call third-party SDKs directly.
"""

from app.adapters.base import ExternalServiceAdapter
from app.adapters.http import HttpAdapterBase

__all__ = ["ExternalServiceAdapter", "HttpAdapterBase"]
