from pathlib import Path
import sys

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class Keys(BaseModel):
    deposit_public_key: int
    deposit_shield_address: str
    btc_deposit_public_key: str
    btc_public_key: str


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
    deployer_address: str
    byte_code_hash: str
    redis: Redis

    chains: list[str]

    usdt_mainnet: str

    verified_tokens: dict[str, dict[str, str]]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(yaml_file=sys.argv[1], extra="forbid")

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
