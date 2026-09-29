# Nayak Frontend

The `frontend/` directory contains the React + Vite web client for Nayak. It
is a dark, voice-first interface for legal and government-scheme questions,
conversation history, authentication, and grievance submission.

## Features

- registered login, registration, and guest login;
- chat sessions and per-session history;
- text input fallback;
- browser microphone recording with `MediaRecorder`;
- upload to backend `/api/transcribe`;
- command dispatch to `/api/command`;
- browser `SpeechSynthesis` playback;
- animated assistant orb and recording state;
- grievance form and authenticated grievance creation.

The browser does not contain Gemini, Groq, database, or JWT-secret credentials.
It sends authenticated requests to the Nayak backend, which owns AI provider
selection and persistence.

## Requirements

- Node.js 18+
- npm
- a running Nayak backend at `http://127.0.0.1:8000`
- Chrome or Edge for microphone recording and best speech API support

## Development

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite development server proxies `/api/*`
to `http://127.0.0.1:8000`.

Build and preview a production bundle:

```bash
npm run build
npm run preview
```

To call a separately hosted backend, create `frontend/.env`:

```env
VITE_API_BASE_URL=https://api.example.com
```

When this variable is set, requests use that base URL instead of the Vite
development proxy.

## Browser request flow

```text
Microphone or text input
          │
          ▼
useNayak.jsx
          │
          ├── audio → POST /api/transcribe → transcript
          └── text  → POST /api/command   → response + session_id
                                      │
                                      ▼
                         browser SpeechSynthesis + transcript UI
```

`src/lib/api.js` adds `Authorization: Bearer <token>` from the
`auth_token` local-storage entry to every request. Login and guest-login
responses must be stored by the corresponding UI flow before protected calls
are made.

## Source structure

```text
src/
├── components/
│   ├── Login.jsx             # login and registration UI
│   ├── Sidebar.jsx           # navigation, history, sessions
│   ├── ChatView.jsx          # conversation transcript
│   ├── InputBar.jsx          # text command input
│   ├── voiceinput.jsx        # microphone control
│   ├── SiriOrb.jsx           # animated recording/response visual
│   ├── Grievance.jsx         # grievance submission UI
│   └── Profile.jsx           # user/profile UI
├── hooks/useNayak.jsx        # recording, transcription, command, browser TTS
├── lib/api.js                # authenticated REST wrapper
├── App.jsx                   # application state and routes
├── main.jsx                  # React entry point
└── index.css                 # Tailwind/global styling
```

## Backend contract used by the frontend

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/login` | Sign in |
| `POST` | `/api/auth/register` | Create account |
| `POST` | `/api/auth/guest-login` | Start temporary guest session |
| `GET` | `/api/auth/verify?token=...` | Verify token |
| `POST` | `/api/session` | Create chat session |
| `GET` | `/api/history?session_id=...` | Load session messages |
| `POST` | `/api/command` | Send text and receive answer |
| `POST` | `/api/new-chat` | Start a new conversation |
| `POST` | `/api/transcribe` | Transcribe uploaded browser audio |
| `POST` | `/api/grievances` | Create a grievance |
| `GET` | `/api/grievances` | List grievances |

The command body is:

```json
{
  "text": "What documents are needed?",
  "session_id": "optional-session-id"
}
```

The backend returns:

```json
{
  "response": "Assistant answer",
  "session_id": "session-id"
}
```

The frontend must reuse the returned session ID when it wants continuity.

## Voice behavior

1. The user starts recording from the microphone control.
2. The browser creates an audio `Blob` using `MediaRecorder`.
3. The blob is uploaded as multipart form data to `/api/transcribe`.
4. The returned transcript is sent to `/api/command`.
5. The response is rendered and spoken through browser `SpeechSynthesis`.
6. The orb changes state while recording, processing, and speaking.

Text input skips steps 1–3 but uses the same command and response path.
Microphone access normally requires localhost or HTTPS and explicit browser
permission.

## Troubleshooting

- **Backend offline:** start the backend or set `VITE_API_BASE_URL` correctly.
- **401 errors:** log in again; the token may be missing or expired.
- **CORS errors:** configure the backend `CORS_ORIGINS` with the frontend's
  exact origin.
- **Microphone unavailable:** use Chrome/Edge, allow microphone access, and
  use `localhost` or HTTPS.
- **No response speech:** check browser autoplay/audio permissions and select a
  supported speech-synthesis voice.
- **Build failure:** run `npm install` and retry `npm run build`.

## Integration reference

For the complete request/response contract and local startup sequence, read
[INTEGRATION.md](INTEGRATION.md). For the overall repository and hardware
pipeline, read [../README.md](../README.md) and [../Hardware/README.md](../Hardware/README.md).
