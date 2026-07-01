from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):

    POSTGRES_DSN: str
    MONGO_URI: str
    MONGO_DB: str
    REDIS_URL: str
    MQTT_HOST: str
    MQTT_PORT: int

    API_KEY: str

    MQTT_USERNAME: str | None = None
    MQTT_PASSWORD: str | None = None

    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_FROM: str = "notifications@yourapp.dev"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()