# Nayak

Nayak is a voice-first legal and government-scheme assistant for India. It
combines a FastAPI backend, a React web application, and an ESP32-connected
hardware client. Users can ask questions, search the curated knowledge base,
review conversation history, and submit grievances from an authenticated
account.

The system has two voice interfaces:

- **Web:** the browser records audio, sends it to the backend for
  transcription, submits the transcript, and reads the response with browser
  speech synthesis.
- **Hardware:** the ESP32 sends raw microphone audio to the local Python
  hardware pipeline. Speech-to-text and text-to-speech run locally there;
  assistant responses and grievance persistence go through the Nayak backend.

## System architecture

```text
                         ┌──────────────────────┐
                         │ FastAPI backend       │
                         │ auth, sessions, RAG,  │
                         │ AI fallback, DB       │
                         └──────────┬───────────┘
                                    │ REST /api/*
                 ┌──────────────────┴──────────────────┐
                 │                                     │
       ┌─────────▼─────────┐                 ┌─────────▼─────────┐
       │ React + Vite web   │                 │ Hardware pipeline   │
       │ browser mic/STT*   │                 │ local STT/TTS       │
       │ browser TTS        │                 │ ESP32 serial I/O    │
       └────────────────────┘                 └─────────┬─────────┘
                                                        │ USB serial
                                                ┌───────▼────────┐
                                                │ ESP32 + speaker │
                                                │ + microphone    │
                                                └────────────────┘

       * Web audio is uploaded to /api/transcribe; the backend uses Groq STT.
```

For normal questions, the hardware client calls `backend_client.ask()` and
then `POST /api/command`. It does not call Gemini directly. The backend may
use its configured local/cloud AI fallback chain internally.

## Repository layout

```text
Nayak/
├── backend/                    # FastAPI API, auth, AI, RAG, migrations
│   ├── src/app/
│   │   ├── api_server.py       # API routes and authentication dependencies
│   │   ├── Ai.py               # model cascade and chat persistence
│   │   ├── ProcessCommands.py  # RAG prompt construction and command routing
│   │   └── vector_db/          # Qdrant/fastembed ingestion and search
│   ├── pyproject.toml
│   ├── uv.lock
│   └── README.md
├── frontend/                   # React/Vite/Tailwind web client
│   ├── src/lib/api.js          # authenticated API wrapper
│   ├── src/hooks/useNayak.jsx  # recording, transcription, command, TTS
│   ├── src/components/
│   ├── package.json
│   ├── README.md
│   └── INTEGRATION.md
├── Hardware/                   # ESP32 serial voice pipeline
│   ├── pipeline.py
│   ├── backend_client.py       # backend-only assistant integration
│   ├── recorder.py / speaker.py
│   ├── stt.py / tts.py
│   └── README.md
└── README.md
```

## Prerequisites

| Tool | Version / requirement | Used by |
| --- | --- | --- |
| Python | 3.13 or newer | Backend |
| `uv` | Current release | Backend dependency management |
| Node.js | 18 or newer | Frontend |
| npm | Bundled with Node.js | Frontend dependencies |
| Chrome or Edge | Current version | Browser microphone and media APIs |
| Piper | Installed on `PATH` | Hardware text-to-speech |
| ESP32 | Firmware implementing the hardware protocol | Hardware voice interface |

## Quick start

### 1. Start the backend

```bash
cd backend
uv sync
uv run uvicorn app.api_server:app --reload
```

The API is available at `http://127.0.0.1:8000` and its OpenAPI page is at
`http://127.0.0.1:8000/docs`.

### 2. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api/*` requests to the backend
at `http://127.0.0.1:8000` during development.

### 3. Start the hardware pipeline (optional)

With the backend running and the ESP32 connected:

```bash
cd Hardware
python -m pip install pyserial requests faster-whisper
python pipeline.py
```

Configure the serial port, backend URL, Piper installation, and optional
registered login in `Hardware/pipeline.py` and `Hardware/backend_client.py`.
Read [Hardware/README.md](Hardware/README.md) before connecting the device.

## Backend

The backend provides:

- JWT authentication for registered and temporary guest users;
- chat sessions and persisted message history;
- retrieval-augmented answers using the knowledge base and vector search;
- local legal-model inference with configured cloud fallbacks;
- grievance creation and listing for registered users;
- audio transcription through the `/api/transcribe` endpoint.

See [backend/README.md](backend/README.md) for environment variables,
database setup, API details, migrations, and model configuration.

## Frontend

The frontend provides login/register/guest access, chat sessions, history,
voice recording, text fallback input, response playback, grievance forms, and
the animated assistant interface. Its API wrapper automatically adds the JWT
stored in `localStorage` as a bearer token.

See [frontend/README.md](frontend/README.md) for development commands and
[frontend/INTEGRATION.md](frontend/INTEGRATION.md) for the frontend/backend
contract.

## Hardware

The hardware pipeline is deliberately independent of the browser. It:

1. receives ESP32 audio packets over USB serial;
2. converts raw int32 microphone audio to WAV;
3. transcribes locally with faster-whisper;
4. sends recognized text to the backend through `backend_client.py`;
5. synthesizes the backend response locally with Piper; and
6. streams display text and PCM audio back to the ESP32.

Complaint requests use the backend grievance endpoint so tickets are persisted.
Normal questions use the backend `/api/command` endpoint and retain a backend
`session_id` for conversational context. See [Hardware/README.md](Hardware/README.md)
for packet formats, setup, authentication, and troubleshooting.

## Environment variables

Create `backend/.env`; do not commit it:

```env
AUTH_JWT_SECRET=replace-with-a-long-random-secret
AUTH_JWT_EXPIRY_HOURS=24
AUTH_GUEST_EXPIRY_HOURS=2
AUTH_BCRYPT_ROUNDS=12
CORS_ORIGINS=http://localhost:5173

# At least one backend AI provider is needed unless a local model is available.
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
DATABASE_URL=your_database_url
```

The frontend can use `frontend/.env` with:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Leave `VITE_API_BASE_URL` unset for the Vite development proxy. Backend cloud
keys are used by the backend only; the browser and hardware client do not need
to contain those provider keys.

## API overview

All protected routes require `Authorization: Bearer <token>`.

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/login` | Login with username and password |
| `POST` | `/api/auth/register` | Create a registered user |
| `POST` | `/api/auth/guest-login` | Create a temporary guest user |
| `GET` | `/api/auth/verify?token=...` | Validate a token |
| `POST` | `/api/session` | Create a chat session |
| `GET` | `/api/history?session_id=...` | Read session history |
| `POST` | `/api/command` | Process text with optional `session_id` |
| `POST` | `/api/new-chat` | Create a fresh chat session |
| `POST` | `/api/transcribe` | Transcribe uploaded audio |
| `POST` | `/api/grievances` | Create a grievance; registered users only |
| `GET` | `/api/grievances` | List the current user's grievances |

The command response is shaped as:

```json
{
  "response": "Assistant answer",
  "session_id": "session-id"
}
```

## Development and verification

Backend:

```bash
cd backend
uv run pytest
uv run alembic upgrade head
```

Frontend:

```bash
cd frontend
npm run build
```

Hardware syntax check:

```bash
python -m compileall Hardware
```

When changing database models, generate and inspect an Alembic migration
before applying it. When changing an API response or serial packet, update the
corresponding client and documentation together.

## Troubleshooting

- **401/403 responses:** verify the bearer token; guest users cannot create
  grievances.
- **Frontend backend-offline error:** start the backend on port 8000 or set
  `VITE_API_BASE_URL` to the correct URL.
- **CORS errors:** set `CORS_ORIGINS` to the exact frontend origin.
- **No browser recording:** use HTTPS or localhost and grant microphone access
  in Chrome/Edge.
- **Hardware cannot connect:** check the serial port, ESP32 firmware protocol,
  baud rate, and Piper voice files. See the hardware README.
- **No AI answer:** check the backend `.env`, local model paths, provider keys,
  and backend startup logs.

## License

See [LICENSE](LICENSE) and the component license files.
