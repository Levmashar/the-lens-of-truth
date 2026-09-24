"""Small common contracts for future external-service adapters."""

from typing import Protocol


class ExternalServiceAdapter(Protocol):
    """Every outbound integration identifies itself for configuration and audit."""

    @property
    def service_name(self) -> str:
        """Stable adapter name, not a provider credential or model alias."""

        ...
