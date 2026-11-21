"""Settings from the environment (12-factor). Everything a user changes day to day lives in the database and the UI."""
from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TIRIS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://tiris:tiris@127.0.0.1:5432/tiris"
    # Tapo / TP-Link account the plugs are bound to (used locally for the plug handshake only).
    tapo_username: str = ""
    tapo_password: str = ""
    # Where discovery looks: subnet broadcast and/or fixed IPs, comma separated.
    discovery_targets: str = "255.255.255.255"
    timezone: str = "Europe/Berlin"

    host: str = "0.0.0.0"
    port: int = 8080
    # Optional single password for the UI. Empty = no login (home lab default).
    password: str = ""
    secret_key: str = Field(default="", description="Signs the session cookie; generated and stored if empty.")

    live_interval_s: float = 2.0          # the plug updates its power value about every 1.5 s [measured]
    collect_interval_min: int = 15
    raw_retention_days: int = 365         # raw 2-second samples; aggregates are kept forever
    static_dir: str = ""                  # built web UI; empty = API only

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def targets(self) -> list[str]:
        return [t.strip() for t in self.discovery_targets.split(",") if t.strip()]

    @property
    def has_tapo(self) -> bool:
        return bool(self.tapo_username and self.tapo_password)


@lru_cache
def settings() -> Settings:
    return Settings()
