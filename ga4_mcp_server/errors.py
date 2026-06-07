from __future__ import annotations


class GA4MCPError(Exception):
    """Base error for safe GA4 MCP tool failures."""


class GA4AuthError(GA4MCPError):
    """Authentication or token-refresh failure."""


class GA4ValidationError(GA4MCPError, ValueError):
    """Invalid tool input."""


def safe_error_message(exc: Exception) -> str:
    """Convert Google/client exceptions into concise, token-safe messages."""
    class_name = exc.__class__.__name__
    message = str(exc)
    lower = message.lower()

    if class_name in {"RefreshError", "ReauthFailError"}:
        return (
            "Authentication failed: saved Google OAuth credentials are expired, "
            "revoked, or cannot be refreshed. Delete the local GA4 token file and "
            "run the MCP tool again to complete browser login."
        )

    if class_name in {"PermissionDenied", "Forbidden"} or "permission" in lower:
        return (
            "Missing permission: the authenticated Google user cannot access the "
            "requested GA4 account or property."
        )

    if class_name in {"ResourceExhausted", "TooManyRequests"} or "quota" in lower:
        return "Quota error: Google Analytics API quota or rate limit was exceeded."

    if class_name in {"NotFound",} or "not found" in lower:
        return "Invalid property or account: Google Analytics could not find that resource."

    if class_name in {"InvalidArgument", "BadRequest"}:
        return f"Invalid GA4 request: {_truncate(message)}"

    if "api has not been used" in lower or "disabled" in lower:
        return (
            "Google API is disabled: enable the Google Analytics Data API and "
            "Google Analytics Admin API in Google Cloud Console."
        )

    return f"Google Analytics API error ({class_name}): {_truncate(message)}"


def _truncate(value: str, limit: int = 500) -> str:
    sanitized = value.replace("\n", " ").strip()
    if len(sanitized) <= limit:
        return sanitized
    return sanitized[: limit - 3] + "..."
