## Purpose

Define human answer-quality feedback controls in Chainlit and their forwarding
to LangSmith as `user_score`.

## Requirements

### Requirement: Feedback controls on agent answers
The Chainlit UI SHALL present the built-in thumbs-up/thumbs-down feedback
controls (with optional comment) on agent answer messages, and feedback
actions SHALL be persisted through the configured Chainlit data layer.
Non-answer operational messages such as HITL approval status, tool-run display
steps, cost badges, MCP status, and the state inspector SHALL NOT be presented
as answer-feedback targets.

#### Scenario: Rating an agent answer
- **WHEN** the agent sends a final answer message in Chainlit and the user
  clicks thumbs-up or thumbs-down
- **THEN** the rating (and any comment) is persisted in the local Chainlit
  database via the data layer

#### Scenario: Final answer is the feedback target
- **WHEN** a turn includes HITL approval, tool execution, state inspection, and
  a final answer
- **THEN** the final answer is the only assistant answer message rendered for
  feedback, is sent after non-answer state/cost messages, and preserves
  Chainlit's scorable run parent

#### Scenario: Local persistence without LangSmith
- **WHEN** LangSmith is not configured and the user rates an agent answer
- **THEN** the rating is persisted locally, no exception is raised, and the UI
  behaves normally

---

### Requirement: Answer messages are linked to their LangSmith trace
Each graph invocation from the Chainlit surface SHALL use a pre-generated root
`run_id` in its invocation config, and the final answer message of a turn
SHALL carry the `run_id` of the invocation that produced it as message
metadata (`langsmith_run_id`), so the link survives app restarts.

#### Scenario: New run id per invocation including HITL resumes
- **WHEN** a turn requires one or more HITL resumes, producing multiple graph
  invocations
- **THEN** each invocation uses a distinct pre-generated root `run_id`, and the
  final answer message carries the `run_id` of the last invocation

#### Scenario: Link survives restart on resumed threads
- **WHEN** the app restarts, a persisted thread is resumed, and the user rates
  an answer message sent before the restart (but after this capability was
  deployed)
- **THEN** the message's `langsmith_run_id` metadata is read from the Chainlit
  database and resolves to the original trace

---

### Requirement: Feedback is forwarded to LangSmith as user_score
When a feedback action resolves to a LangSmith run id, the system SHALL record
it on that run as a feedback score with key `user_score`, scoring 1.0 for
thumbs-up and 0.0 for thumbs-down, attaching the user's comment when present.
Forwarding MUST be non-blocking for the UI: LangSmith failures or absence
SHALL never fail local feedback persistence.

#### Scenario: Thumbs-up forwarded
- **WHEN** the user rates an answer thumbs-up with a comment and LangSmith is
  configured
- **THEN** a `user_score` feedback with score 1.0 and the comment is created on
  the root run that produced the answer

#### Scenario: HITL status feedback is attributed to the answer
- **WHEN** Chainlit submits feedback for a HITL action status message such as
  `**Selected:** Approve`
- **AND** a later assistant answer in the same thread has `langsmith_run_id`
  metadata
- **THEN** the feedback is forwarded as `user_score` on the root run that
  produced that answer

#### Scenario: LangSmith outage does not break the UI
- **WHEN** the LangSmith API call fails during feedback forwarding
- **THEN** the error is printed, the local rating is still persisted, and no
  exception propagates to Chainlit

#### Scenario: Unresolvable message is a no-op
- **WHEN** the user rates a message that has no resolvable `langsmith_run_id`
  (for example, a thread created before this capability existed)
- **THEN** the rating is persisted locally, no LangSmith feedback is created,
  and a notice is printed

---

### Requirement: Re-rating and deletion are idempotent in LangSmith
The system SHALL derive a deterministic LangSmith feedback id from the rated
message so that changing a rating updates the existing `user_score` feedback
instead of creating a duplicate, and removing the rating in Chainlit SHALL
delete the corresponding LangSmith feedback.

#### Scenario: Toggling a rating
- **WHEN** the user changes a rating from thumbs-up to thumbs-down
- **THEN** the run has exactly one `user_score` feedback, now with score 0.0

#### Scenario: Removing a rating
- **WHEN** the user removes their rating in Chainlit
- **THEN** the corresponding `user_score` feedback is deleted from LangSmith,
  and a deletion failure never blocks local deletion
