import json
import aiomqtt
from app.config import settings
from app.security import create_service_token

_SERVICE_USERNAME = "service"

async def publish_notification(user_id: str, notification: dict) -> None:

    topic = f"users/{user_id}/notifications"
  
    payload = json.dumps(notification, default=str)

    async with aiomqtt.Client(
        settings.MQTT_HOST,
        port=settings.MQTT_PORT,
        username=_SERVICE_USERNAME,
        password=create_service_token(),
    ) as client:
        await client.publish(topic, payload=payload, qos=1, retain=False)
