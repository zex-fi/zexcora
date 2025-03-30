from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, HttpUrl
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

type Chain = str
type TokenName = str


class Dummy(BaseModel):
    fill_dummy: bool
    client_private: str
    bot_private_seed: str


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
    host: str = "0.0.0.0"
    port: int = 15782
    api_prefix: str
    light_node: bool
    state_source: str
    state_dest: Path
    state_save_frequency: int
    state_manager: HttpUrl
    event_distributor: HttpUrl
    sequencer_subgraph: HttpUrl
    sequencer_whitelist: HttpUrl
    tx_transmit_delay: float
    mainnet: bool
    use_redis: bool
    verbose: bool
    sequencer_mode: Literal["local", "docker", "eigenlayer"]
    verifier_threads: int

    dummy: Dummy
    keys: Keys
    deployer_address: str
    byte_code_hash: str
    redis: Redis

    chains: list[str]

    usdt_mainnet: str

    verified_tokens: dict[TokenName, dict[Chain, Token]]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        nested_model_default_partial_update=True,
        env_nested_delimiter="__",
        yaml_file=["config.yaml"],
        extra="forbid",
    )
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
        return env_settings, YamlConfigSettingsSource(settings_cls)


settings = Settings()

print(settings.model_dump_json())
