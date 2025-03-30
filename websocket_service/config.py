from typing import Literal

from pydantic import BaseModel, HttpUrl
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class Broker(BaseModel):
    broker_type: Literal["rabbitmq", "kafka"]
    host: str
    port: int
    username: str
    password: str

    message_ttl: int


class WebsocketServiceSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 15785
    api_prefix: str
    verbose: bool
    event_distributor: HttpUrl

    broker: Broker


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        nested_model_default_partial_update=True,
        env_nested_delimiter="__",
        yaml_file=["config.yaml"],
        extra="forbid",
    )
    websocket_service: WebsocketServiceSettings

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return env_settings, YamlConfigSettingsSource(settings_cls)


settings = Settings()

print(settings.model_dump_json())
