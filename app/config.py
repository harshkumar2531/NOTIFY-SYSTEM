from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # The names below must match the keys in the .env file.
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

    # SMTP / email (MailHog in dev; SendGrid/SES in prod).
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_FROM: str = "notifications@yourapp.dev"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# A single shared instance imported throughout the app.
settings = Settings()