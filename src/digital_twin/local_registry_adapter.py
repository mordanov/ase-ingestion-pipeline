from src.digital_twin.interfaces import TwinRegistryAdapter
from src.observability.logging import get_logger

logger = get_logger(__name__)

_registry: dict[str, dict] = {}


class LocalRegistryAdapter(TwinRegistryAdapter):
    """In-memory twin registry for local development (LOCAL_DEV=true)."""

    async def register(self, device_id: str, device_type: str) -> str | None:
        thing_name = f"local-{device_id}"
        _registry[device_id] = {"thing_name": thing_name, "device_type": device_type, "state": {}}
        logger.info("twin_registered_local", device_id=device_id, thing_name=thing_name)
        return thing_name

    async def get_state(self, device_id: str) -> dict | None:
        entry = _registry.get(device_id)
        return entry["state"] if entry else None
