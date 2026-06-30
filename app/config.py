from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    POSTGRES_DSN: str
    MONGO_URI: str
    MONGO_DB: str
    REDIS_URL: str
    MQTT_HOST: str
    MQTT_PORT: int
    # API security
    API_KEY: str

    # MQTT credentials (used when VerneMQ secure mode is enabled; safe to leave
    # blank while ALLOW_ANONYMOUS is on for dev).
    MQTT_USERNAME: str | None = None
    MQTT_PASSWORD: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()


