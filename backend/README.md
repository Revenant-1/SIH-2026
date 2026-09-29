# Nayak Backend

The `backend/` directory contains the FastAPI service for Nayak. It handles
authentication, chat sessions, conversation history, retrieval-augmented legal
answers, audio transcription, and grievance persistence for both the web app
and the hardware client.

## Responsibilities

- expose the REST API under `/api/*`;
- authenticate registered and guest users with JWTs;
- create and validate chat sessions;
- retrieve relevant documents from the knowledge base;
- generate answers through the configured AI cascade;
- persist user and assistant messages;
- accept browser audio for transcription;
- create and list grievances for registered users.

The hardware client does not call a model provider directly. It authenticates
with this service and sends normal questions to `POST /api/command`.

## Requirements

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/)
- a configured database and vector-search service for the deployment;
- at least one available AI provider or a local legal model;
- `AUTH_JWT_SECRET` set before importing the application.

Install and synchronize dependencies:

```bash
cd backend
uv sync
```

`pyproject.toml` and `uv.lock` are the dependency sources. `requirements.txt`
is also kept for environments that do not use `uv`.

## Environment configuration

Create `backend/.env`:

```env
AUTH_JWT_SECRET=use-a-long-random-secret
AUTH_JWT_EXPIRY_HOURS=24
AUTH_GUEST_EXPIRY_HOURS=2
AUTH_BCRYPT_ROUNDS=12
CORS_ORIGINS=http://localhost:5173

GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key
DATABASE_URL=your_database_url
```

`AUTH_JWT_SECRET` is mandatory. Use a different strong value per environment
and keep `.env` out of version control. `CORS_ORIGINS` is a comma-separated
allowlist; include the exact origin used by the frontend.

The AI module currently supports these providers:

1. local Indian legal Llama, when its GGUF model is present under `backend/models/`;
2. optional general local Llama fallback;
3. Gemini, when `GEMINI_API_KEY` is configured;
4. Groq, when `GROQ_API_KEY` is configured.

The cascade skips unavailable providers. The backend is the owner of this
model selection; clients only send text to `/api/command`.

## Run the API

From `backend/`:

```bash
uv run uvicorn app.api_server:app --reload
```

The development server listens at `http://127.0.0.1:8000`.

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

The same app can be started from Python:

```bash
uv run python -m app.api_server
```

## API contract

Protected routes require:

```http
Authorization: Bearer <token>
```

### Authentication

| Method | Route | Body | Result |
| --- | --- | --- | --- |
| `POST` | `/api/auth/login` | `{ "username", "password" }` | JWT, user ID, user type, expiry |
| `POST` | `/api/auth/register` | `{ "username", "password", "email" }` | New registered user and JWT |
| `POST` | `/api/auth/guest-login` | none | Temporary guest user and JWT |
| `GET` | `/api/auth/verify?token=...` | none | Token validity and user ID |

### Sessions and commands

Create a session:

```http
POST /api/session
Authorization: Bearer <token>
```

Send a command:

```json
{
  "text": "What is PMFBY?",
  "session_id": "optional-existing-session-id"
}
```

Response:

```json
{
  "response": "Assistant answer",
  "session_id": "session-id"
}
```

`session_id` is optional for the first request. The backend creates one when
it is omitted and clients should reuse the returned value for conversation
context. `GET /api/history?session_id=...` returns messages for that user's
session. `POST /api/new-chat` creates a new session response.

### Audio transcription

`POST /api/transcribe` accepts multipart form data:

- `audio`: an audio file;
- `language`: optional two-letter language code.

The response is:

```json
{
  "text": "recognized text",
  "language": "en"
}
```

The browser uses this endpoint. The hardware pipeline performs STT locally and
does not upload its microphone audio here.

### Grievances

`POST /api/grievances` requires a registered account, not a guest token:

```json
{
  "title": "Water supply issue",
  "category": "General",
  "description": "At least ten characters describing the issue.",
  "location": "Optional location"
}
```

The response includes the grievance `id`, status, timestamp, and a Markdown
submission script. `GET /api/grievances` lists the current registered user's
records.

## Project structure

```text
backend/
├── src/app/
│   ├── api_server.py              # FastAPI app and routes
│   ├── Ai.py                      # AI cascade and chat persistence
│   ├── ProcessCommands.py         # RAG retrieval and prompt construction
│   ├── services/auth/             # password, guest, and JWT operations
│   ├── models/                    # SQLAlchemy models and DB session
│   └── vector_db/                 # ingest, embeddings, Qdrant search
├── alembic/                       # database migrations
├── pyproject.toml
├── requirements.txt
├── uv.lock
└── README.md
```

Knowledge-base documents live under
`src/app/vector_db/Data/knowledge_base/`. The vector database utilities and
their ingestion notes are documented in `src/app/vector_db/README.md`.

## Database migrations

After changing SQLAlchemy models, create and inspect a migration:

```bash
uv run alembic revision --autogenerate -m "describe the schema change"
uv run alembic upgrade head
```

Do not use `Base.metadata.create_all()` to update an existing deployment.

## Testing and diagnostics

```bash
uv run pytest
```

For a provider-specific diagnostic, `Ai.py` supports the model names `legal`,
`local`, `gemini`, and `groq` in its development prompt loop. Normal API calls
use the automatic cascade.

## Security notes

- Never commit `.env`, API keys, database credentials, or JWT secrets.
- Use HTTPS and a restricted `CORS_ORIGINS` list outside local development.
- Guest accounts are intended for temporary chat access and cannot create
  grievances.
- Keep the backend responsible for provider keys; do not expose them to the
  frontend or ESP32 client.
