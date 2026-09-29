# Frontend–Backend Integration

This document describes how the React client communicates with the FastAPI
service. The backend must be running before the frontend can log in, load
history, transcribe audio, or send commands.

## Local services

Start the backend:

```bash
cd backend
uv sync
uv run uvicorn app.api_server:app --reload
```

Start the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Use `http://localhost:5173`. In development, `frontend/vite.config.js`
proxies `/api` to `http://127.0.0.1:8000`, so browser requests can use relative
paths without a CORS preflight.

For a separately hosted API, set:

```env
VITE_API_BASE_URL=https://api.example.com
```

The backend must then allow the frontend origin through `CORS_ORIGINS`.

## Authentication

1. Call `POST /api/auth/login`, `/api/auth/register`, or
   `/api/auth/guest-login`.
2. Store the returned `token` as `auth_token`.
3. Add `Authorization: Bearer <token>` to protected requests.
4. Use `GET /api/auth/verify?token=<token>` when validating a stored token.

`src/lib/api.js` adds the bearer header automatically from local storage.
Guest tokens are temporary and are not allowed to create grievances.

Login response shape:

```json
{
  "token": "jwt",
  "user_id": "usr_xxx",
  "username": "farmer01",
  "user_type": "regular",
  "expires_in": 86400
}
```

## Session and command flow

Create a session with `POST /api/session`, or send the first command without a
session ID. The backend returns one automatically:

```http
POST /api/command
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "text": "How can I apply for PMFBY?",
  "session_id": "optional-session-id"
}
```

```json
{
  "response": "Assistant answer",
  "session_id": "session-id"
}
```

Persist the returned session ID in the active frontend session and send it on
later commands. Load its messages with:

```text
GET /api/history?session_id=session-id
```

Start another conversation with `POST /api/new-chat`; use the returned
`session_id` as the active session. A session ID belongs to its authenticated
user and cannot be used with another user's token.

## Browser audio flow

The frontend records audio with `MediaRecorder`, then sends multipart form data
to the backend:

```text
POST /api/transcribe
Content-Type: multipart/form-data

audio=<recording blob>
language=en
```

Response:

```json
{
  "text": "recognized text",
  "language": "en"
}
```

The frontend then sends `text` to `/api/command` and uses browser
`SpeechSynthesis` to read `response`. The hardware path is different: it uses
local faster-whisper and Piper, then sends only recognized text to the backend
through `Hardware/backend_client.py`.

## Grievances

The frontend submits a registered user's grievance with:

```http
POST /api/grievances
Authorization: Bearer <registered-user-token>
Content-Type: application/json
```

```json
{
  "title": "Water supply issue",
  "category": "General",
  "description": "Describe the issue in at least ten characters.",
  "location": "Optional location"
}
```

Guests receive `403 Forbidden` for this route. The response contains the
created grievance ID, status, timestamp, and generated Markdown script.

## Error handling

The backend returns JSON errors with a `detail` field. The frontend request
wrapper converts that field into a JavaScript `Error`:

| Status | Meaning |
| --- | --- |
| `400` | Invalid or empty request |
| `401` | Missing, invalid, or expired token |
| `403` | Authenticated but not allowed, commonly guest grievance access |
| `404` | Session or resource does not belong to the user |
| `413` | Audio upload too large |
| `415` | Unsupported audio content type |
| `502` | Upstream transcription failure |
| `503` | Required backend provider is unavailable |

## Contract checklist

When changing the backend API, update all of these together:

- Pydantic request/response models and route handlers;
- `frontend/src/lib/api.js`;
- session/auth state in `App.jsx` and `useNayak.jsx`;
- this integration document;
- the root and backend READMEs when setup or deployment changes.

The ESP32 pipeline also consumes `/api/command` and `/api/grievances`; review
`Hardware/backend_client.py` and [../Hardware/README.md](../Hardware/README.md)
for its contract.
