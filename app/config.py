from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings read from environment variables (and a local .env file).

    Secrets are optional here so the app boots without them; features that
    need a secret should fail loudly when it is missing.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    app_name: str = "Our Parks"

    session_idle_minutes: int = 30
    token_encryption_key: str | None = None
    database_url: str | None = None

    # Free key from nps.gov/subjects/developer. Without it the park list can't load.
    nps_api_key: str | None = None
    nps_api_url: str = "https://developer.nps.gov/api/v1"
    # OpenFreeMap style for the map; kept here so the tile source can be swapped.
    map_style_url: str = "https://tiles.openfreemap.org/styles/liberty"

    admin_email: str | None = None
    # Passkeys are bound to this domain; changing it invalidates every passkey.
    webauthn_rp_id: str = "localhost"

    @property
    def origin(self) -> str:
        return self.app_base_url.rstrip("/")

    @property
    def secure_cookies(self) -> bool:
        return self.origin.startswith("https://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
