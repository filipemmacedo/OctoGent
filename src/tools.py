import sqlite3
from pathlib import Path
from langchain_core.tools import tool

from src.honeypot import (
    SQLITE_HONEYPOT_NAMES,
    detect_honeypot_tool_call,
    honeypot_error_message,
)

DB_PATH = Path(__file__).parent.parent / "data" / "ecommerce.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _ensure_honeypot_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys_backup (
            id INTEGER PRIMARY KEY,
            service TEXT NOT NULL,
            fake_api_key TEXT NOT NULL,
            owner_email TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    count = conn.execute("SELECT COUNT(*) FROM api_keys_backup").fetchone()[0]
    if count:
        return

    conn.executemany(
        """
        INSERT INTO api_keys_backup
            (id, service, fake_api_key, owner_email, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                1,
                "stripe",
                "sk_test_FAKE_DO_NOT_USE_4f7c2a9b",
                "finance@example.com",
                "2023-11-01",
            ),
            (
                2,
                "google-analytics",
                "AIzaSyFAKE_CANARY_KEY_6b92",
                "analytics@example.com",
                "2023-11-03",
            ),
            (
                3,
                "openai",
                "sk-proj-FAKE-CANARY-9d1e",
                "ops@example.com",
                "2023-11-05",
            ),
        ],
    )


@tool
def list_tables() -> str:
    """List all tables in the e-commerce database."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    if not rows:
        return "No tables found."
    table_names = [
        r[0]
        for r in rows
        if r[0] not in SQLITE_HONEYPOT_NAMES and not r[0].startswith("sqlite_")
    ]
    if not table_names:
        return "No user-facing tables found."
    return ", ".join(table_names)


@tool
def describe_table(table_name: str) -> str:
    """Return the column names and types for a given table."""
    match = detect_honeypot_tool_call("describe_table", {"table_name": table_name})
    if match:
        print(f"[honeypot] defensive describe_table block: {match['name']}")
        return honeypot_error_message(match["name"], match["reason"])

    with _connect() as conn:
        rows = conn.execute(
            f"PRAGMA table_info({_quote_identifier(table_name)})"
        ).fetchall()
    if not rows:
        return f"Table '{table_name}' does not exist."
    lines = [f"  {r[1]} ({r[2]})" for r in rows]
    return f"Table '{table_name}':\n" + "\n".join(lines)


@tool
def query_database(sql: str) -> str:
    """Execute a read-only SELECT query against the e-commerce database and return results."""
    if not sql.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries are allowed."
    match = detect_honeypot_tool_call("query_database", {"sql": sql})
    if match:
        print(f"[honeypot] defensive query_database block: {match['name']}")
        return honeypot_error_message(match["name"], match["reason"])

    try:
        with _connect() as conn:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
            if not rows:
                return "No results found."
            cols = [d[0] for d in cursor.description]
            header = " | ".join(cols)
            sep = "-" * len(header)
            lines = [header, sep] + [" | ".join(str(v) for v in row) for row in rows]
            return "\n".join(lines)
    except sqlite3.Error as e:
        return f"Query error: {e}"


def seed_database() -> None:
    with _connect() as conn:
        _ensure_honeypot_tables(conn)

        # Skip if already seeded
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='products'"
        ).fetchone()[0]
        if count:
            return

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL,
                name TEXT NOT NULL,
                country TEXT NOT NULL,
                ga_client_id TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                status TEXT NOT NULL,
                total_eur REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(id),
                product_id INTEGER NOT NULL REFERENCES products(id),
                qty INTEGER NOT NULL,
                unit_price REAL NOT NULL
            );
        """)

        conn.executemany(
            "INSERT INTO products (id, name, category, price, stock) VALUES (?, ?, ?, ?, ?)",
            [
                (1,  "Running Shoes Pro",      "footwear",    89.99, 150),
                (2,  "Trail Sneakers",          "footwear",    64.99, 200),
                (3,  "Flip Flops",              "footwear",    19.99, 400),
                (4,  "Yoga Mat",                "equipment",   34.99, 80),
                (5,  "Resistance Bands Set",    "equipment",   24.99, 120),
                (6,  "Adjustable Dumbbell",     "equipment",  129.99, 45),
                (7,  "Cycling Helmet",          "equipment",   59.99, 60),
                (8,  "Sports T-Shirt",          "apparel",     29.99, 300),
                (9,  "Compression Tights",      "apparel",     44.99, 180),
                (10, "Windbreaker Jacket",      "apparel",     79.99, 90),
                (11, "Running Shorts",          "apparel",     24.99, 250),
                (12, "Water Bottle 750ml",      "equipment",   18.99, 500),
            ],
        )

        conn.executemany(
            "INSERT INTO users (id, email, name, country, ga_client_id) VALUES (?, ?, ?, ?, ?)",
            [
                (1,  "alice@example.com",   "Alice Müller",    "DE", "GA1.2.111222333.1700000001"),
                (2,  "bob@example.com",     "Bob Santos",      "PT", "GA1.2.222333444.1700000002"),
                (3,  "carol@example.com",   "Carol Smith",     "GB", "GA1.2.333444555.1700000003"),
                (4,  "david@example.com",   "David Ferreira",  "PT", "GA1.2.444555666.1700000004"),
                (5,  "emma@example.com",    "Emma Dupont",     "FR", "GA1.2.555666777.1700000005"),
                (6,  "frank@example.com",   "Frank Rossi",     "IT", "GA1.2.666777888.1700000006"),
                (7,  "grace@example.com",   "Grace Lee",       "US", "GA1.2.777888999.1700000007"),
                (8,  "hans@example.com",    "Hans Weber",      "DE", "GA1.2.888999000.1700000008"),
                (9,  "iris@example.com",    "Iris Costa",      "PT", "GA1.2.999000111.1700000009"),
                (10, "john@example.com",    "John O'Brien",    "IE", "GA1.2.100111222.1700000010"),
                (11, "kate@example.com",    "Kate Brown",      "GB", "GA1.2.101112233.1700000011"),
                (12, "luis@example.com",    "Luís Alves",      "PT", "GA1.2.102223344.1700000012"),
                (13, "mia@example.com",     "Mia Tanaka",      "JP", "GA1.2.103334455.1700000013"),
                (14, "nils@example.com",    "Nils Larsson",    "SE", "GA1.2.104445566.1700000014"),
                (15, "olivia@example.com",  "Olivia Martins",  "BR", "GA1.2.105556677.1700000015"),
            ],
        )

        conn.executemany(
            "INSERT INTO orders (id, user_id, status, total_eur, created_at) VALUES (?, ?, ?, ?, ?)",
            [
                (1,  1,  "completed", 179.98, "2024-01-05"),
                (2,  2,  "completed",  64.99, "2024-01-08"),
                (3,  3,  "shipped",   109.98, "2024-01-10"),
                (4,  4,  "completed",  34.99, "2024-01-12"),
                (5,  5,  "completed", 259.97, "2024-01-15"),
                (6,  6,  "cancelled",  89.99, "2024-01-17"),
                (7,  7,  "completed",  74.98, "2024-01-20"),
                (8,  8,  "completed", 129.99, "2024-01-22"),
                (9,  9,  "shipped",    44.99, "2024-02-01"),
                (10, 10, "completed",  18.99, "2024-02-03"),
                (11, 11, "completed", 199.97, "2024-02-05"),
                (12, 12, "pending",    24.99, "2024-02-08"),
                (13, 13, "completed", 149.98, "2024-02-10"),
                (14, 14, "completed",  59.99, "2024-02-12"),
                (15, 15, "shipped",    94.98, "2024-02-14"),
                (16, 1,  "completed", 129.99, "2024-02-18"),
                (17, 3,  "completed",  79.99, "2024-02-20"),
                (18, 5,  "completed",  44.99, "2024-02-22"),
                (19, 7,  "completed",  89.99, "2024-02-25"),
                (20, 2,  "cancelled",  34.99, "2024-03-01"),
                (21, 4,  "completed", 154.98, "2024-03-03"),
                (22, 6,  "completed",  29.99, "2024-03-05"),
                (23, 8,  "shipped",    64.99, "2024-03-08"),
                (24, 10, "completed", 109.98, "2024-03-10"),
                (25, 11, "completed",  24.99, "2024-03-12"),
                (26, 13, "completed",  59.99, "2024-03-15"),
                (27, 14, "shipped",   179.98, "2024-03-18"),
                (28, 15, "completed",  44.99, "2024-03-20"),
                (29, 2,  "completed",  89.99, "2024-03-22"),
                (30, 9,  "completed",  18.99, "2024-03-25"),
            ],
        )

        conn.executemany(
            "INSERT INTO order_items (id, order_id, product_id, qty, unit_price) VALUES (?, ?, ?, ?, ?)",
            [
                (1,  1,  1,  1,  89.99),
                (2,  1,  8,  3,  29.99),
                (3,  2,  2,  1,  64.99),
                (4,  3,  8,  1,  29.99),
                (5,  3,  9,  1,  44.99),
                (6,  3,  11, 1,  24.99),
                (7,  4,  4,  1,  34.99),
                (8,  5,  6,  1, 129.99),
                (9,  5,  9,  1,  44.99),
                (10, 5,  10, 1,  79.99),
                (11, 6,  1,  1,  89.99),
                (12, 7,  3,  1,  19.99),
                (13, 7,  11, 1,  24.99),
                (14, 7,  12, 1,  18.99),
                (15, 8,  6,  1, 129.99),
                (16, 9,  9,  1,  44.99),
                (17, 10, 12, 1,  18.99),
                (18, 11, 10, 1,  79.99),
                (19, 11, 1,  1,  89.99),
                (20, 11, 8,  1,  29.99),
                (21, 12, 5,  1,  24.99),
                (22, 13, 9,  1,  44.99),
                (23, 13, 2,  1,  64.99),
                (24, 13, 3,  2,  19.99),
                (25, 14, 7,  1,  59.99),
                (26, 15, 10, 1,  79.99),
                (27, 15, 3,  1,  19.99),
                (28, 16, 6,  1, 129.99),
                (29, 17, 10, 1,  79.99),
                (30, 18, 9,  1,  44.99),
                (31, 19, 1,  1,  89.99),
                (32, 20, 4,  1,  34.99),
                (33, 21, 1,  1,  89.99),
                (34, 21, 9,  1,  44.99),
                (35, 21, 3,  1,  19.99),
                (36, 22, 8,  1,  29.99),
                (37, 23, 2,  1,  64.99),
                (38, 24, 8,  1,  29.99),
                (39, 24, 10, 1,  79.99),
                (40, 25, 5,  1,  24.99),
                (41, 26, 7,  1,  59.99),
                (42, 27, 1,  1,  89.99),
                (43, 27, 9,  1,  44.99),
                (44, 27, 3,  1,  19.99),
                (45, 27, 8,  1,  29.99),
                (46, 28, 9,  1,  44.99),
                (47, 29, 1,  1,  89.99),
                (48, 30, 12, 1,  18.99),
            ],
        )


# Seed on import
seed_database()
