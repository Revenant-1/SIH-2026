# Nayak Hardware Voice Pipeline

This directory contains the Python bridge that connects the Nayak voice
assistant to an ESP32 device. The bridge receives microphone audio over USB
serial, transcribes it locally, sends the recognized text to the Nayak
backend, converts the backend response to speech, and streams the result back
to the ESP32 speaker.

The pipeline does **not** call Gemini directly. General questions and
conversation go through `backend_client.py` and the backend's
`POST /api/command` endpoint. The backend remains responsible for the
assistant/LLM behavior, authentication, retrieval, and conversation state.

## Architecture

```text
ESP32 microphone
      │ USB serial: AUD0 / CHNK / AUD1
      ▼
pipeline.py
      │
      ├── recorder.py       Receive raw int32 PCM
      ├── recorder.py       Convert to 16 kHz, 16-bit WAV
      ├── stt.py            Local faster-whisper transcription
      ├── backend_client.py POST /api/command for normal questions
      │                     POST /api/grievances for complaint tickets
      ├── tts.py            Local Piper Hindi/English speech synthesis
      └── speaker.py        USB serial: TEXT + streamed PCM audio
                              │
                              ▼
                         ESP32 speaker/OLED
```

The only cloud/backend request made for a normal question is the request to
the Nayak backend. There is no `gemini_client` import in the running pipeline
and no `GEMINI_API_KEY` requirement for this folder.

## Files

| File | Responsibility |
| --- | --- |
| `pipeline.py` | Main long-running loop and configuration entry point. |
| `backend_client.py` | Authenticates with the backend, sends `/api/command` requests, preserves the backend session ID, and files grievances. |
| `grievance.py` | Detects complaint-filing requests and builds the spoken ticket response. |
| `recorder.py` | Parses ESP32 recording packets and converts raw microphone samples to WAV. |
| `stt.py` | Offline speech-to-text using faster-whisper. The model is downloaded on first use. |
| `tts.py` | Local Piper text-to-speech with Hindi/English voice selection and WAV caching. |
| `speaker.py` | Sends OLED text and flow-controlled audio to the ESP32. |
| `gemini_client.py` | Legacy standalone Gemini client. It is not imported by `pipeline.py` and is not required to run the hardware pipeline. |
| `voices/` | Piper voice models and metadata. |
| `Esp32.ino` | Placeholder for the device firmware in this checkout; use the firmware that implements the protocol below. |

## Requirements

### Python packages

Install the packages in the Python environment used to run the pipeline:

```bash
python -m pip install pyserial requests faster-whisper
```

The `piper` command must also be installed and available on `PATH`. The exact
installation method depends on the operating system and Piper package you use.
Verify it with:

```bash
piper --help
```

The first transcription run may download the configured faster-whisper model
(`small` by default). Later transcription runs use the local model cache.

### Backend

Start the Nayak backend separately. By default the hardware client sends
requests to:

```text
http://127.0.0.1:8000
```

The backend must provide these endpoints:

- `POST /api/auth/guest-login` → JSON containing `token`
- `POST /api/auth/login` → JSON containing `token`
- `POST /api/command` → JSON containing `response` and optionally `session_id`
- `POST /api/grievances` → JSON containing `id` (requires a registered user)

If the backend runs on another host or port, edit `BASE_URL` in
`backend_client.py` before starting the pipeline, or adapt that constant to
your deployment configuration.

## Configuration

Edit the constants at the top of `pipeline.py`:

```python
PORT = "/dev/ttyUSB0"  # Linux example
BAUD = 921600
LOGIN_ON_START = False
USERNAME = ""
PASSWORD = ""
```

Common serial-port examples:

- Linux: `/dev/ttyUSB0` or `/dev/ttyACM0`
- macOS: `/dev/cu.usbserial-*` or `/dev/cu.SLAB_USBtoUART`
- Windows: `COM3`, `COM4`, etc.

Use `LOGIN_ON_START = True` with a real registered backend account when the
device must file grievances. Guest authentication is sufficient for normal
`/api/command` questions, but the backend rejects guest users from creating
grievance records.

The current audio settings are:

- microphone input: 16 kHz, mono, raw signed int32 PCM from the ESP32;
- speech-to-text output: text plus detected language;
- speech output: 16 kHz, mono, signed 16-bit PCM WAV;
- speaker chunks: 1024 frames, paced using ESP32 `FREE:<bytes>` reports.

## Running the pipeline

Run it from this directory so the relative voice and cache paths resolve
correctly:

```bash
cd Hardware
python pipeline.py
```

The normal startup sequence is:

1. The script opens the ESP32 serial port at 921600 baud.
2. The ESP32 sends `GRT0`; the pipeline synthesizes or reuses the greeting.
3. A record-button press sends `AUD0` and audio packets.
4. The local Whisper model transcribes the recording.
5. A normal request is sent to `backend_client.ask()`, which calls
   `/api/command` and keeps the returned `session_id` for later requests.
6. A complaint request is sent to `backend_client.file_grievance()` and the
   returned ticket ID is spoken back.
7. Piper creates the reply WAV and `speaker.py` sends display text followed by
   the audio stream.
8. The repeat button sends `RPT0`; the last reply is replayed without calling
   the backend again.

Stop the process with `Ctrl+C`.

## ESP32 serial protocol

The Python side expects the following binary markers:

### Device to host

- `GRT0`: request the boot greeting.
- `AUD0`: start a new recording. The host consumes this marker before calling
  `receive_recording()`.
- `CHNK` + little-endian `uint16` length + audio bytes: one recording chunk.
- `AUD1` + little-endian `uint32` total byte count: end of recording.
- `RPT0`: replay the most recent reply.
- `FREE:<bytes>\n`: available speaker ring-buffer capacity. The host uses this
  for flow control.

The audio bytes inside `CHNK` packets must be raw little-endian signed int32,
16 kHz, mono samples. The final `AUD1` count must equal the sum of all chunk
payload lengths.

### Host to device

For each reply, the host sends:

1. `TEXT` + little-endian `uint16` UTF-8 length + UTF-8 display text;
2. raw little-endian signed int16, 16 kHz, mono PCM bytes from the WAV file.

The display text is capped at 240 bytes so it fits the firmware's OLED text
buffer. The device should render the text, accept the audio stream, and use
the `FREE:<bytes>` status messages to let the host continue sending safely.

## Authentication and session behavior

`backend_client.py` lazily obtains a guest token on the first request. It
stores the token in memory only and refreshes it once if the backend returns
HTTP 401. The conversation's `session_id` is also held in memory and is sent
with subsequent `/api/command` requests. Restarting the Python process starts
a new client session.

For grievance filing, call `backend_client.login(username, password)` at
startup by enabling the login settings in `pipeline.py`. A failed grievance
request is converted into a spoken error instead of terminating the main loop.

Do not commit real usernames, passwords, API tokens, or backend secrets to
this directory. Prefer environment variables or a protected deployment
configuration if the pipeline is moved beyond local testing.

## Caches and generated files

The pipeline creates local runtime files such as:

- `recording.wav` — latest recording received from the ESP32;
- `output.wav` — latest normal assistant reply;
- `grievance_reply.wav` and `grievance_number.wav` — grievance response audio;
- `piper_temp.wav` — temporary Piper output;
- `tts_cache/` — cached fixed phrases such as the greeting;

These files are generated locally and can be removed when no longer needed.
If a cached phrase changes, delete its corresponding file in `tts_cache/` so
it is synthesized again.

## Troubleshooting

### `ModuleNotFoundError`

Install the Python requirements in the active environment and confirm that
the same interpreter runs the script:

```bash
python -m pip install pyserial requests faster-whisper
python -c "import serial, requests, faster_whisper"
```

### Serial port cannot be opened

Check the port name, disconnect other serial monitors, verify USB permissions,
and make sure the ESP32 is powered. On Linux, the user may need access to the
`dialout` group.

### Backend connection or authentication errors

Confirm that the backend is running, `BASE_URL` is correct, and the endpoint
paths and JSON response fields match the API contract above. Test the backend
independently before debugging audio.

### No speech is produced

Verify that `piper` is on `PATH`, both `.onnx` voice files exist under
`voices/`, and the process is being run from `Hardware/` (or that the voice
paths have been made absolute).

### The ESP32 reports a serial timeout or audio mismatch

Check that firmware and host use the same baud rate, packet headers, byte
order, sample format, and `AUD1` total length. Do not send an `AUD0` marker a
second time after `wait_for_trigger()` has already consumed it.

### The first response is slow

The first run may load faster-whisper, authenticate with the backend, and
generate uncached Piper audio. Subsequent requests reuse the loaded model and
cached fixed phrases.

## Development notes

The separation between local audio processing and backend conversation is
intentional:

- `stt.py` and `tts.py` keep device audio work local;
- `backend_client.py` is the sole integration point for assistant responses;
- `pipeline.py` coordinates the stages but contains no model/API logic;
- grievance creation remains a backend operation because the ticket must be
  persisted by the backend.

If the backend API changes, update `backend_client.py` and this README
together. If the ESP32 packet format changes, update `recorder.py`,
`speaker.py`, and the firmware as one change.

## License

See [`LICENSE`](LICENSE).
