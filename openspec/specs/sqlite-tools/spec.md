## ADDED Requirements

### Requirement: list_tables tool returns all user-facing table names
The system SHALL expose a `list_tables` LangChain `@tool` that queries the e-commerce SQLite database and returns a comma-separated list of table names, excluding LangGraph internal tables.

#### Scenario: Tables returned on empty prior knowledge
- **WHEN** the agent calls `list_tables`
- **THEN** the tool returns at minimum: `products`, `users`, `orders`, `order_items`

---

### Requirement: describe_table tool returns schema for a named table
The system SHALL expose a `describe_table(table_name: str)` LangChain `@tool` that returns the column names and types for the given table using `PRAGMA table_info`.

#### Scenario: Schema returned for known table
- **WHEN** the agent calls `describe_table("orders")`
- **THEN** the tool returns a formatted list of columns including `id`, `user_id`, `status`, `total_eur`, `created_at`

#### Scenario: Error returned for unknown table
- **WHEN** the agent calls `describe_table("nonexistent")`
- **THEN** the tool returns an error string indicating the table does not exist

---

### Requirement: query_database tool executes read-only SQL
The system SHALL expose a `query_database(sql: str)` LangChain `@tool` that executes the provided SQL against the e-commerce database and returns results as a formatted string. The tool SHALL only allow `SELECT` statements; any other statement type SHALL be rejected with an error message.

#### Scenario: Valid SELECT query returns results
- **WHEN** the agent calls `query_database("SELECT name, price FROM products LIMIT 5")`
- **THEN** the tool returns a formatted table of up to 5 product rows

#### Scenario: Non-SELECT statement is rejected
- **WHEN** the agent calls `query_database("DROP TABLE products")`
- **THEN** the tool returns an error string: "Only SELECT queries are allowed"

#### Scenario: Empty result set
- **WHEN** the agent calls a valid SELECT that matches no rows
- **THEN** the tool returns "No results found"

---

### Requirement: E-commerce database is seeded on first run
The system SHALL provide a `seed_database()` function that creates and populates the following tables if they do not exist: `products`, `users`, `orders`, `order_items`. Seed data SHALL include at least 10 products across 3 categories, 15 users (each with a plausible `ga_client_id`), 30 orders in various statuses, and corresponding `order_items` rows.

#### Scenario: Seed runs only once
- **WHEN** `seed_database()` is called and tables already contain data
- **THEN** no data is inserted and the function returns without error

#### Scenario: `ga_client_id` bridge column exists
- **WHEN** the database is seeded
- **THEN** every row in `users` has a non-null `ga_client_id` in the format `"GA1.2.<number>.<timestamp>"`

#### Scenario: Cross-source query is structurally possible
- **WHEN** the agent joins `users.ga_client_id` to a GA4 `client_id` field
- **THEN** the SQL join syntax is valid against the seeded schema
