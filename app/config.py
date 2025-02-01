from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

type Chain = str
type TokenName = str


class Keys(BaseModel):
    deposit_public_key: int
    deposit_shield_address: str
    btc_public_key: str


class Redis(BaseModel):
    url: str
    password: str


class Token(BaseModel):
    contract_address: str
    balance_withdraw_limit: Decimal
    decimal: int


class ZexSettings(BaseModel):
    host: str
    port: int
    api_prefix: str
    light_node: bool
    state_source: str
    state_dest: Path
    state_save_frequency: int
    tx_transmit_delay: float
    mainnet: bool
    use_redis: bool
    verbose: bool
    fill_dummy: bool
    sequencer_mode: Literal["local", "docker", "eigenlayer"]

    keys: Keys
    deployer_address: str
    byte_code_hash: str
    redis: Redis

    chains: list[str]

    usdt_mainnet: str

    verified_tokens: dict[TokenName, dict[Chain, Token]]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(yaml_file=["config.yaml"], extra="forbid")
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
