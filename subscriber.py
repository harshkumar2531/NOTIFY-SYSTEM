import asyncio
import json
import sys
import aiomqtt
from app.config import settings

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main(user_id: str) -> None:
    topic = f"users/{user_id}/notifications"

    MQTT_HOST = "localhost"  # Windows connects through the published Docker port

    print(f"Connecting to {MQTT_HOST}:{settings.MQTT_PORT}...")

    async with aiomqtt.Client(
    MQTT_HOST,
    port=settings.MQTT_PORT,
    ) as client:

            print("Connected to MQTT broker.")

            await client.subscribe(topic, qos=1)
            print(f"Subscribed to '{topic}'")
            print("Waiting for notifications...\n")

            async for message in client.messages:
                try:
                    payload = message.payload.decode()
                    data = json.loads(payload)

                    print("=" * 50)
                    print("NEW NOTIFICATION")
                    print("=" * 50)
                    print(f"ID    : {data.get('id')}")
                    print(f"Title : {data.get('title')}")
                    print(f"Body  : {data.get('body')}")
                    print(f"Type  : {data.get('type')}")
                    print()

                except Exception:
                    print("Raw payload:", message.payload)

                except Exception as e:
                    print(f"MQTT Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage:")
        print("python subscriber.py <user_id>")
        sys.exit(1)

    asyncio.run(main(sys.argv[1]))