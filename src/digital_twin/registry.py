"""DeviceRegistry — coordinates DB upsert and twin adapter registration."""
from src.digital_twin.interfaces import TwinRegistryAdapter
from src.observability.logging import get_logger

logger = get_logger(__name__)


class DeviceRegistry:
    def __init__(self, twin_adapter: TwinRegistryAdapter):
        self._twin = twin_adapter

    async def register(self, device_id: str, device_type: str) -> str | None:
        """Register device in the twin registry and return the thing_name."""
        try:
            thing_name = await self._twin.register(device_id, device_type)
            return thing_name
        except Exception as exc:
            logger.warning("twin_register_failed", device_id=device_id, error=str(exc))
            return None

    async def get_state(self, device_id: str) -> dict | None:
        try:
            return await self._twin.get_state(device_id)
        except Exception as exc:
            logger.warning("twin_get_state_failed", device_id=device_id, error=str(exc))
            return None
