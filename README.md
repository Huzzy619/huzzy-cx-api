# Kora CX API

Contact-centre control plane for Kora CX. The API owns organisations, contact
centres, queues, agents, customers, interactions, telephony connections and the
configuration/lifecycle of AI voice agents. A separate LiveKit-based worker
(`voice_worker/`) runs the real-time voice agent and talks back to this API over
an internal, service-authenticated interface.

## Architecture

Kora CX is a **modular monolith**: one Django deployment (`config/`) with
bounded-context apps under `apps/`, plus a separate deployable voice worker.
The design rules that shape the code are:

- **The LLM never owns truth.** Models may propose actions, but routing,
  permissions, tenant scope, verification gates and financial state are decided
  in domain services, never by model output.
- **Tenant isolation is enforced in code.** Every model carries an
  `organisation`; service functions call `assert_same_organisation` before
  linking records across the tenant boundary.
- **Transactions + outbox.** State changes happen inside `transaction.atomic`
  with row locks (`select_for_update`). Cross-service side effects are written
  as outbox events and dispatched by Celery, not performed inline.
- **At-least-once delivery.** Event handlers assume duplicate delivery and
  deduplicate with database unique constraints rather than existence checks.
- **Provider neutrality.** Telephony is behind a port/adapter boundary; only a
  `mock` adapter ships today, so the rest of the platform is written against
  canonical events, not a vendor SDK.

## Applications

| App | Responsibility |
| --- | --- |
| `apps.common` | Shared base model, outbox, tenancy guards, errors, permissions. |
| `apps.organisations` | Tenant root: `Organisation`, `Membership`, `Team`, auth. |
| `apps.contact_centres` | `ContactCentre`, `Queue`, `ChannelConnection`. |
| `apps.agents` | `AgentProfile`, queue membership, ephemeral presence leases. |
| `apps.customers` | `Customer` and normalised `CustomerIdentifier`s. |
| `apps.interactions` | `Interaction` lifecycle, `InteractionEvent`s, state machine. |
| `apps.telephony` | Provider port/adapter registry, webhook ingestion, canonical events. |
| `apps.routing` | Eligibility and human handoff/transfer request records. |
| `apps.voice_agents` | Voice agent config/versioning, sessions, tool execution boundary. |
| `apps.integrations` | Provider-neutral support-case integration. |
| `apps.audit` | Append-only audit trail for sensitive actions. |

## API surface

All routes are versioned under `/api/v1/` (`config/api.py`):

| Mount | Auth | Purpose |
| --- | --- | --- |
| `/interactions/` | `SessionMembershipAuth` | Read interaction state and events. |
| `/voice-agents/` | `SessionMembershipAuth` | Voice agent config lifecycle (create/version/publish/archive). |
| `/internal/voice/` | Worker token | Worker-facing: initialize/end sessions, execute tools. |
| `/webhooks/telephony/{provider}` | Provider secret | Inbound telephony events. |

Human-facing auth (`apps/organisations/auth.py`) currently resolves the caller
from the Django session and validates an `X-Organisation-Id` header against the
caller's `Membership`. The bearer token value itself is a placeholder to be
replaced by real token validation. The worker authenticates with a shared
secret (`VOICE_WORKER_TOKEN`) compared in constant time and fails closed.

## Voice layer

### Control plane (`apps/voice_agents`)

- **Config lifecycle**: `VoiceAgent` → immutable `VoiceAgentVersion`s. A version
  is validated (`VoiceAgentConfig`) then published; publishing flips the agent's
  `active_version` and emits `voice_agent.published` to the outbox.
- **Sessions**: `initialize_voice_session` resolves the tenant *from the provider
  connection* (the caller cannot choose an organisation), picks the active agent
  version for the contact centre, creates/reconciles the `Interaction`, and
  creates a `VoiceSession`. In-flight sessions keep their original agent version.
- **Identity gate**: sessions whose tools require verification start
  `authentication_status=pending` and cannot use those tools until
  `mark_authentication_verified`.
- **Tool boundary** (`tools.py`): the only path from the model to the outside
  world. It enforces the per-session tool allow-list, the verification gate,
  tenant scope, and idempotency (unique `VoiceToolInvocation` per
  `idempotency_key`), and writes an audit event on execution. Handlers cover
  approved knowledge search, transaction status, support-case read/create, human
  handoff, and ending the interaction.
- **Handoff** (`apps/routing/services.py`): records a `handoff_requested` outbox
  event and reports whether an eligible human is queued. It never claims a
  transfer has occurred — only the telephony/voice layer can confirm that.

### Data plane (`voice_worker/`)

`voice_worker/` is a **separate deployable** with its own `pyproject.toml`. It
is not installed by the API project and is not part of the Django test run; the
API project only lints it. It contains:

- A config-driven LiveKit agent builder (`builders/`) for LLM/STT/TTS pipelines,
  turn handling, custom providers and `raw_audio` plugins for languages not
  served by hosted models (e.g. Yoruba, Hausa, Igbo), an Agent class builder and
  instructions.
- `kora_client.py`, an async client for the internal `/api/v1/internal/voice/`
  endpoints (session init/end, knowledge search, transaction status, support
  cases, handoff, event recording).
- `graph/`, a LangGraph supervisor (intent classification + short-term
  summarisation) and a RAG graph (query generation → retrieval → relevance
  grading → answer/rewrite).
- `runtime.py` / `agent_server.py`, the LiveKit job entrypoint with
  session-end persistence and observability handlers.

See `voice_worker/.env.example` for its configuration. Because its dependencies
(notably `livekit-agents`, which requires Python 3.12) are not installed here,
worker code is lint-verified only.

## Background work

Celery tasks live in `workers/` and are routed per queue (`config/settings/base.py`):
`voice-events`, `ai-enrichment`, `integrations`, `outbox`. `workers/outbox_tasks.py`
dispatches the transactional outbox. `workers/ai_tasks.py` and
`workers/integration_tasks.py` currently define only the task/queue **boundary**
for their milestones — they are intentionally no-ops until those milestones are
implemented.

## Local development

Prerequisites: Python 3.14, [`uv`](https://docs.astral.sh/uv/), and PostgreSQL.
Redis and a Celery broker are only needed for the full async runtime; the test
suite replaces them with in-memory/eager equivalents.

```bash
# 1. Dependencies
uv sync

# 2. PostgreSQL (Homebrew example)
brew services start postgresql@16
createuser -s kora            # or: psql postgres -c "CREATE ROLE kora LOGIN PASSWORD 'kora' CREATEDB;"
createdb -O kora kora

# 3. Environment
cp .env.example .env          # then edit secrets

# 4. Migrate and run
uv run python manage.py migrate
uv run python manage.py runserver
```

Run the async runtime when you need it:

```bash
redis-server
celery -A config worker -l info
```

## Testing and checks

The test suite requires a real PostgreSQL instance (the domain depends on real
constraints and row locking); Redis is not required.

```bash
uv run pytest                                   # full suite
uv run pytest -m unit                          # fast unit tests
uv run pytest tests/integration                # DB-constraint tests
uv run ruff check .                            # lint
uv run ruff format --check .                   # formatting
uv run python manage.py check                  # Django system checks
uv run python manage.py makemigrations --check --dry-run
```

`pyproject.toml` is authoritative for lint rules (line length 88, `E/F/I/UP/B`,
migrations excluded) and for pytest markers (`unit`, `integration`, `contract`,
`security`).

## Configuration

Environment variables are documented in `.env.example` and read via
`django-environ` in `config/settings/base.py`. Settings modules:
`development` (default for `manage.py`/Celery entrypoints), `test`, and
`production`. Key variables include `DATABASE_URL`, `REDIS_URL`,
`CELERY_BROKER_URL`, `TELEPHONY_PROVIDER`, `TELEPHONY_WEBHOOK_SECRET`,
`VOICE_WORKER_TOKEN`, `VOICE_ENGINE_PROVIDER`, `AI_PROVIDER`, and
`AI_MODEL`.

## Project layout

```
config/            Django project: settings, urls, asgi/wsgi, celery, ninja API
apps/              Domain apps (see table above)
workers/           Celery tasks and queue boundaries
tests/             pytest suite: unit, integration, contract, security
voice_worker/      Separate LiveKit voice-agent deployable (own pyproject.toml)
```

## Status

The domain foundation and the voice layer (control plane + worker) are
implemented with a green test suite. Areas intentionally left as boundaries:
AI enrichment/transcription/summarisation workers, external integrations,
real telephony providers (mock only), and real human-facing authentication.
