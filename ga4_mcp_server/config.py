import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from ga4_mcp_server.errors import GA4MCPError

ANALYTICS_READONLY_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"


class GA4ConfigError(GA4MCPError, ValueError):
    """Raised when required GA4 MCP configuration is missing or invalid."""


@dataclass(frozen=True)
class GA4MCPConfig:
    google_client_id: str
    google_client_secret: str
    google_project_id: str
    ga4_property_id: str | None
    token_path: Path
    oauth_host: str
    oauth_port: int

    @classmethod
    def from_env(cls) -> "GA4MCPConfig":
        load_dotenv()
        return cls(
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
            google_project_id=os.getenv("GOOGLE_PROJECT_ID", "").strip(),
            ga4_property_id=os.getenv("GA4_PROPERTY_ID", "").strip() or None,
            token_path=_token_path_from_env(),
            oauth_host=os.getenv("GA4_OAUTH_HOST", "127.0.0.1").strip()
            or "127.0.0.1",
            oauth_port=_oauth_port_from_env(),
        )

    def require_oauth_config(self) -> None:
        missing = [
            name
            for name, value in (
                ("GOOGLE_CLIENT_ID", self.google_client_id),
                ("GOOGLE_CLIENT_SECRET", self.google_client_secret),
            )
            if not value
        ]
        if missing:
            joined = ", ".join(missing)
            raise GA4ConfigError(
                f"Missing required Google OAuth configuration: {joined}. "
                "Set these environment variables before using GA4 MCP tools."
            )

    def require_default_property_id(self) -> str:
        if not self.ga4_property_id:
            raise GA4ConfigError(
                "GA4_PROPERTY_ID is not configured. Set it in the MCP server "
                "environment, or call the report tool with an explicit property_id."
            )
        return self.ga4_property_id


def _token_path_from_env() -> Path:
    configured = os.getenv("GA4_TOKEN_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()

    if os.name == "nt":
        base = (
            os.getenv("LOCALAPPDATA", "").strip()
            or os.getenv("APPDATA", "").strip()
            or str(Path.home())
        )
        return Path(base) / "ga4-mcp" / "token.json"

    base = os.getenv("XDG_STATE_HOME", "").strip() or str(Path.home() / ".local" / "state")
    return Path(base) / "ga4-mcp" / "token.json"


def _oauth_port_from_env() -> int:
    raw_value = os.getenv("GA4_OAUTH_PORT", "8080").strip()
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise GA4ConfigError("GA4_OAUTH_PORT must be an integer.") from exc
    if port < 1 or port > 65535:
        raise GA4ConfigError("GA4_OAUTH_PORT must be between 1 and 65535.")
    return port


def oauth_client_config(config: GA4MCPConfig) -> dict:
    config.require_oauth_config()
    return {
        "installed": {
            "client_id": config.google_client_id,
            "client_secret": config.google_client_secret,
            "project_id": config.google_project_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [
                f"http://{config.oauth_host}:{config.oauth_port}/",
                "http://localhost",
            ],
        }
    }
