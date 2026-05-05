import asyncio

from src.digital_twin.interfaces import TwinRegistryAdapter
from src.observability.logging import get_logger

logger = get_logger(__name__)


class IotCoreAdapter(TwinRegistryAdapter):
    """AWS IoT Core thing registry adapter using boto3 (asyncio.to_thread for blocking calls)."""

    def __init__(self, region: str, endpoint: str, policy_name: str, thing_type: str):
        self._region = region
        self._endpoint = endpoint
        self._policy_name = policy_name
        self._thing_type = thing_type
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("iot", region_name=self._region)
        return self._client

    async def register(self, device_id: str, device_type: str) -> str | None:
        client = self._get_client()
        thing_name = device_id
        try:
            await asyncio.to_thread(
                client.create_thing,
                thingName=thing_name,
                thingTypeName=self._thing_type,
                attributePayload={"attributes": {"device_type": device_type}},
            )
            logger.info("iot_thing_created", device_id=device_id, thing_name=thing_name)
            return thing_name
        except client.exceptions.ResourceAlreadyExistsException:
            logger.info("iot_thing_already_exists", device_id=device_id)
            return thing_name
        except Exception as exc:
            logger.error("iot_thing_creation_failed", device_id=device_id, error=str(exc))
            return None

    async def get_state(self, device_id: str) -> dict | None:
        try:
            data_client = self._get_data_client()
            response = await asyncio.to_thread(
                data_client.get_thing_shadow,
                thingName=device_id,
            )
            import json

            payload = json.loads(response["payload"].read())
            return payload.get("state", {}).get("reported")
        except Exception as exc:
            logger.warning("iot_shadow_fetch_failed", device_id=device_id, error=str(exc))
            return None

    def _get_data_client(self):
        import boto3

        return boto3.client(
            "iot-data",
            region_name=self._region,
            endpoint_url=f"https://{self._endpoint}",
        )
