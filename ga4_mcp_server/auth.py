import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from ga4_mcp_server.config import (
    ANALYTICS_READONLY_SCOPE,
    GA4MCPConfig,
    oauth_client_config,
)
from ga4_mcp_server.errors import GA4AuthError

SCOPES = [ANALYTICS_READONLY_SCOPE]


def get_credentials(config: GA4MCPConfig | None = None) -> Credentials:
    """Return valid OAuth credentials, opening browser login on first run."""
    config = config or GA4MCPConfig.from_env()
    config.require_oauth_config()

    credentials = _load_saved_credentials(config.token_path)
    if credentials and credentials.valid:
        return credentials

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except RefreshError as exc:
            raise GA4AuthError(
                "Saved Google OAuth credentials could not be refreshed. Delete "
                "the local GA4 token file and run the MCP tool again to re-authenticate."
            ) from exc
        _save_credentials(config.token_path, credentials)
        return credentials

    flow = InstalledAppFlow.from_client_config(oauth_client_config(config), SCOPES)
    try:
        with redirect_stdout(sys.stderr):
            credentials = flow.run_local_server(
                host=config.oauth_host,
                port=config.oauth_port,
                open_browser=True,
                authorization_prompt_message=(
                    "Opening browser for Google Analytics OAuth consent. "
                    "If it does not open, visit this URL:\n{url}\n"
                ),
                success_message=(
                    "GA4 MCP authentication complete. You can close this browser window."
                ),
                access_type="offline",
                prompt="consent",
            )
    except Exception as exc:  # Browser/server failures vary by platform.
        raise GA4AuthError(
            "Google OAuth browser login failed. Check the OAuth Desktop client "
            "configuration and try running the MCP server in an interactive shell."
        ) from exc

    _save_credentials(config.token_path, credentials)
    return credentials


def _load_saved_credentials(token_path: Path) -> Credentials | None:
    if not token_path.exists():
        return None
    try:
        return Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except Exception as exc:
        raise GA4AuthError(
            "Could not read local Google OAuth credentials. Delete the local "
            "GA4 token file and run the MCP tool again to re-authenticate."
        ) from exc


def _save_credentials(token_path: Path, credentials: Credentials) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    if os.name != "nt":
        try:
            os.chmod(token_path, 0o600)
        except OSError:
            pass
