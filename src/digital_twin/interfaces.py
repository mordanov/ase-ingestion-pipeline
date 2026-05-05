from abc import ABC, abstractmethod


class TwinRegistryAdapter(ABC):
    @abstractmethod
    async def register(self, device_id: str, device_type: str) -> str | None:
        """Register device in the twin registry. Returns thing_name or None."""

    @abstractmethod
    async def get_state(self, device_id: str) -> dict | None:
        """Retrieve the current shadow/state of a registered device."""
