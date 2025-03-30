from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class Redis(BaseModel):
    url: str
    password: str


class ZexSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 15782
    api_prefix: str
    state_dest: Path
    verbose: bool

    redis: Redis


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        nested_model_default_partial_update=True,
        env_nested_delimiter="__",
        yaml_file=["config.yaml"],
        extra="forbid",
    )
    state_manager: ZexSettings

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
