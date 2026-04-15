from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    DATABASE_URL: str = "postgresql+asyncpg://fleet:fleet_secret@localhost:5432/fleet_db"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://fleet:fleet_secret@localhost:5432/fleet_db"
    POSTGRES_DB: str = "fleet_db"
    POSTGRES_USER: str = "fleet"
    POSTGRES_PASSWORD: str = "fleet_secret"

    MQTT_BROKER: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""

    FLEET_HOST: str = "0.0.0.0"
    FLEET_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "change-me"

    FIRMWARE_STORAGE_PATH: str = "./data/firmware"

    # Absolute path on the Docker host to this project root.
    # Used so fleet-api (running in a container) can launch sibling esphome
    # containers via /var/run/docker.sock with bind mounts that the host
    # daemon can resolve. Set to the host path on the droplet.
    HOST_PROJECT_DIR: str = "/opt/mdm_esp32"
    ESPHOME_IMAGE: str = "esphome/esphome:2024.12.4"

    # Public URL that ESP32 devices use to reach this server (for OTA firmware downloads)
    SERVER_URL: str = "http://192.168.1.231:8000"

    # Firebase Cloud Messaging (broadcast push notifications)
    FCM_PROJECT_ID: str = ""
    FCM_CREDENTIALS_PATH: str = ""

    # Alerting
    SLACK_WEBHOOK_URL: str = ""
    SENDGRID_API_KEY: str = ""
    ALERT_EMAIL: str = ""


settings = Settings()
