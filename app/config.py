from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class Keys(BaseModel):
    deposit_public_key: int
    btc_xmr_deposit_public_key: str
    btc_public_key: str
    monero_public_address: str


class Redis(BaseModel):
    url: str
    password: str


class ZexSettings(BaseModel):
    host: str
    port: int
    api_prefix: str
    light_node: bool
    state_source: str
    state_dest: Path
    state_save_frequency: int
    mainnet: bool
    use_redis: bool
    verbose: bool

    keys: Keys
    redis: Redis

    deposited_block: dict[str, int]
    default_tokens_deciaml: dict[str, dict[str, int]]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(yaml_file="config.yaml", extra="forbid")

    zex: ZexSettings

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (YamlConfigSettingsSource(settings_cls),)


settings = Settings()
