## ADDED Requirements

### Requirement: State inspector displays honeypot governance events
The Chainlit state inspector SHALL display whether honeypot events have occurred and SHALL summarize recent honeypot blocks using the tool name, matched object, and action.

#### Scenario: Honeypot count shown after block
- **WHEN** Chainlit renders the state inspector after a honeypot access attempt is blocked
- **THEN** the inspector shows a non-zero honeypot event count

#### Scenario: Recent honeypot event is summarized
- **WHEN** Chainlit renders the state inspector after one or more honeypot access attempts are blocked
- **THEN** the inspector includes the most recent honeypot event summary with the matched object `api_keys_backup`
