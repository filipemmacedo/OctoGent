## MODIFIED Requirements

### Requirement: list_tables tool returns all user-facing table names
The system SHALL expose a `list_tables` LangChain `@tool` that queries the e-commerce SQLite database and returns a comma-separated list of user-facing table names, excluding LangGraph internal tables and honeypot canary objects.

#### Scenario: Tables returned on empty prior knowledge
- **WHEN** the agent calls `list_tables`
- **THEN** the tool returns at minimum: `products`, `users`, `orders`, `order_items`

#### Scenario: Canary table is hidden from discovery
- **WHEN** the agent calls `list_tables`
- **THEN** the returned table list does not include `api_keys_backup`

---

### Requirement: E-commerce database is seeded on first run
The system SHALL provide a `seed_database()` function that creates and populates the following tables if they do not exist: `products`, `users`, `orders`, `order_items`. Seed data SHALL include at least 10 products across 3 categories, 15 users (each with a plausible `ga_client_id`), 30 orders in various statuses, and corresponding `order_items` rows. The function SHALL also ensure the SQLite honeypot canary table `api_keys_backup` exists with fake credential-looking rows.

#### Scenario: Seed runs only once
- **WHEN** `seed_database()` is called and business tables already contain data
- **THEN** duplicate business seed data is not inserted and the function returns without error

#### Scenario: `ga_client_id` bridge column exists
- **WHEN** the database is seeded
- **THEN** every row in `users` has a non-null `ga_client_id` in the format `"GA1.2.<number>.<timestamp>"`

#### Scenario: Cross-source query is structurally possible
- **WHEN** the agent joins `users.ga_client_id` to a GA4 `client_id` field
- **THEN** the SQL join syntax is valid against the seeded schema

#### Scenario: Canary table exists after seeding
- **WHEN** `seed_database()` completes
- **THEN** the SQLite database contains `api_keys_backup` with fake non-secret values

## ADDED Requirements

### Requirement: SQLite tools defensively reject honeypot objects
The SQLite tool layer SHALL defensively reject direct access to honeypot objects even if the graph-level guard is bypassed.

#### Scenario: Query tool rejects canary object
- **WHEN** `query_database` is called directly with SQL referencing `api_keys_backup`
- **THEN** the tool returns a governance error string and does not return canary rows

#### Scenario: Describe tool rejects canary object
- **WHEN** `describe_table` is called directly with `table_name` equal to `api_keys_backup`
- **THEN** the tool returns a governance error string and does not return canary schema details
