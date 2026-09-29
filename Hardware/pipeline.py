"""
End-to-end voice assistant loop:

    ESP32 boots
        -> plays a cached welcome greeting

    ESP32 button press
        -> record (recorder.py)
        -> speech-to-text (stt.py, faster-whisper, offline)
        -> either:
             - a grievance-filing request -> file it (grievance.py)
               and read back the ticket number, or
             - anything else -> ask the backend (/api/command)
               and speak its answer (tts.py)
        -> stream reply back to ESP32 speaker (speaker.py)
        -> repeat

    ESP32 repeat-button press
        -> resend + replay the last reply, unchanged

Run:
    python pipeline.py
"""

import os
import time

import serial

import backend_client
import grievance
import recorder
import speaker
import stt
import tts

PORT = "/dev/ttyUSB0"       # change to your ESP32's serial port
BAUD = 921600

RECORDED_WAV = "recording.wav"
REPLY_WAV = "output.wav"

GREETING_TEXT = "Namaste. Nayak mein aapka swagat hai."

# If you want grievances to actually file (api_server.py blocks
# guest accounts from POST /api/grievances), fill these in and set
# LOGIN_ON_START = True. Otherwise grievance requests will fail
# gracefully with a spoken/displayed error instead of a ticket.
LOGIN_ON_START = False
USERNAME = ""
PASSWORD = ""


def main():
    print(f"Opening {PORT} at {BAUD} baud...")
    ser = serial.Serial(PORT, BAUD, timeout=0.2)

    # Clear anything left over from a previous connection, THEN wait
    # for the board to finish its own boot — do not flush again
    # after the sleep, or you'll wipe out the boot greeting trigger.
    ser.reset_input_buffer()
    time.sleep(2)

    if LOGIN_ON_START and USERNAME and PASSWORD:
        print("Logging in...")
        backend_client.login(USERNAME, PASSWORD)

    print("Connected. Waiting for triggers from the ESP32...")

    last_answer = None

    try:
        while True:
            trigger = recorder.wait_for_trigger(ser)

            # ----------------------------------------------------
            # Boot greeting
            # ----------------------------------------------------
            if trigger == "greet":
                print("[Greeting] Playing welcome message...")
                wav_path = tts.create_tts_cached("greeting", GREETING_TEXT)
                speaker.send_reply(ser, wav_path, GREETING_TEXT)
                last_answer = GREETING_TEXT
                continue

            # ----------------------------------------------------
            # Repeat button: resend the last reply, unchanged
            # ----------------------------------------------------
            if trigger == "repeat":
                print("[Repeat] Resending last reply...")
                if os.path.exists(REPLY_WAV) and last_answer:
                    speaker.send_reply(ser, REPLY_WAV, last_answer)
                else:
                    print("Nothing to repeat yet.")
                continue

            # ----------------------------------------------------
            # trigger == "record": a new question was recorded
            # ----------------------------------------------------
            print("\n[Recorder] Receiving...")
            raw_audio = recorder.receive_recording(ser)
            print(f"[Recorder] Received {len(raw_audio)} bytes.")

            recorder.raw_int32_to_wav(raw_audio, RECORDED_WAV)

            print("[STT] Transcribing...")
            text, lang = stt.transcribe(RECORDED_WAV)
            print(f"[STT] Heard ({lang}): {text!r}")

            if not text.strip():
                print("Nothing recognized — listening again.")
                continue

            # ------------------------------------------------
            # Grievance-filing intent -> file it, read back ticket
            # ------------------------------------------------
            if grievance.is_grievance_request(text):
                print("[Grievance] Filing...")
                wav_path, display_text = grievance.file_grievance(text)

                if wav_path is None:
                    # display_text holds the error message here
                    print("[Grievance] Failed:", display_text)
                    wav_path = tts.create_tts(display_text, output_file=REPLY_WAV)
                else:
                    print("[Grievance] Filed:", display_text)

                last_answer = display_text
                speaker.send_reply(ser, wav_path, display_text)
                continue

            # ------------------------------------------------
            # Everything else -> ask the backend, speak the answer
            # ------------------------------------------------
            print("[Nayak] Asking...")
            answer = backend_client.ask(text)
            print(f"[Nayak] Answer: {answer!r}")

            if not answer.strip():
                print("No answer — listening again.")
                continue

            reply_path = tts.create_tts(answer, output_file=REPLY_WAV)
            if not reply_path:
                print("TTS failed — listening again.")
                continue

            last_answer = answer
            speaker.send_reply(ser, reply_path, answer)

    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
