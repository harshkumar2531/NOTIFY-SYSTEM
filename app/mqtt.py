import json
import aiomqtt

from app.config import settings

async def publish_notification(user_id: str, notification: dict) -> None:

    topic = f"users/{user_id}/notifications"

    payload = json.dumps(notification, default=str)
    async with aiomqtt.Client(
        settings.MQTT_HOST,
        port=settings.MQTT_PORT,
        username=settings.MQTT_USERNAME,
        password=settings.MQTT_PASSWORD,
    ) as client:
        await client.publish(topic, payload=payload, qos=1, retain=False)
