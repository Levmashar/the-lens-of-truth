"""Classified, public-safe retrieval failures."""

from typing import Literal

from app.core.errors import ExternalCapabilityError

RetrievalFailureKind = Literal[
    "timeout", "transport", "upstream_http", "rate_limited", "malformed_response"
]


class RetrievalError(ExternalCapabilityError):
    def __init__(self, kind: RetrievalFailureKind) -> None:
        status_code = 504 if kind == "timeout" else 503
        super().__init__(
            code=f"pubmed_{kind}",
            message="PubMed retrieval is temporarily unavailable.",
            status_code=status_code,
        )
        self.kind = kind
