import re
from typing import Any, TypedDict


class HoneypotObject(TypedDict):
    name: str
    classification: str
    reason: str


HONEYPOT_REASON = (
    "SQLite canary table: no legitimate workflow should access credential backups"
)

SQLITE_HONEYPOT_OBJECTS: dict[str, HoneypotObject] = {
    "api_keys_backup": {
        "name": "api_keys_backup",
        "classification": "honeypot",
        "reason": HONEYPOT_REASON,
    }
}

SQLITE_HONEYPOT_NAMES = frozenset(SQLITE_HONEYPOT_OBJECTS)
SQLITE_HONEYPOT_TOOL_NAMES = frozenset({"describe_table", "query_database"})


def normalize_sqlite_identifier(identifier: str) -> str:
    """Normalize one SQLite identifier token for exact canary comparisons."""
    value = identifier.strip()
    wrappers = (('"', '"'), ("`", "`"), ("[", "]"))
    for left, right in wrappers:
        if value.startswith(left) and value.endswith(right) and len(value) >= 2:
            value = value[1:-1].strip()
            break
    return value.lower()


def _identifier_patterns(name: str) -> list[re.Pattern[str]]:
    escaped = re.escape(name)
    return [
        re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.IGNORECASE),
        re.compile(rf'"{escaped}"', re.IGNORECASE),
        re.compile(rf"`{escaped}`", re.IGNORECASE),
        re.compile(rf"\[{escaped}\]", re.IGNORECASE),
    ]


def find_honeypot_reference(value: Any) -> HoneypotObject | None:
    """Return the registered honeypot object referenced by a string value."""
    if not isinstance(value, str):
        return None

    normalized = normalize_sqlite_identifier(value)
    if normalized in SQLITE_HONEYPOT_OBJECTS:
        return SQLITE_HONEYPOT_OBJECTS[normalized]

    for name, entry in SQLITE_HONEYPOT_OBJECTS.items():
        if any(pattern.search(value) for pattern in _identifier_patterns(name)):
            return entry
    return None


def detect_honeypot_tool_call(
    tool_name: str,
    args: dict[str, Any] | None,
) -> HoneypotObject | None:
    """Inspect SQLite tool-call arguments for registered honeypot references."""
    if tool_name not in SQLITE_HONEYPOT_TOOL_NAMES:
        return None

    args = args or {}
    candidate_values: list[Any]
    if tool_name == "describe_table":
        candidate_values = [args.get("table_name"), args.get("__arg1")]
    elif tool_name == "query_database":
        candidate_values = [args.get("sql"), args.get("__arg1")]
    else:
        candidate_values = []

    candidate_values.extend(
        value for key, value in args.items() if key not in {"table_name", "sql", "__arg1"}
    )
    for value in candidate_values:
        match = find_honeypot_reference(value)
        if match:
            return match
    return None


def honeypot_error_message(name: str, reason: str) -> str:
    return (
        "Governance error: blocked access to SQLite honeypot object "
        f"'{name}'. Reason: {reason}."
    )
