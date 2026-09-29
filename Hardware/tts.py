"""
Text-to-speech using Piper.

Picks a Hindi or English voice based on the text (Devanagari script
=> Hindi), converts Piper's output to 16kHz/16-bit/mono, and writes
a WAV file. Does NOT send audio anywhere itself — the pipeline
decides when/how to send it (see speaker.py).
"""

import subprocess
import os
import re
import wave
import audioop

VOICE_DIR = "voices"

HINDI_VOICE = os.path.join(VOICE_DIR, "hi_IN-pratham-medium.onnx")
ENGLISH_VOICE = os.path.join(VOICE_DIR, "en_US-lessac-medium.onnx")

DEFAULT_OUTPUT_FILE = "output.wav"
CACHE_DIR = "tts_cache"

TARGET_RATE = 16000
TARGET_CHANNELS = 1
TARGET_WIDTH = 2  # 16-bit PCM


def is_hindi(text):
    """Detects Hindi by checking for Devanagari characters."""
    for char in text:
        if "\u0900" <= char <= "\u097F":
            return True
    return False


def clean_for_speech(text):
    """
    Strips markdown formatting and citation clutter from an LLM
    answer so Piper doesn't read out literal asterisks, headers,
    or "[Doc 1 | Source: ... | Section: ...]" blocks.
    """
    # Normalize odd unicode whitespace/punctuation the model likes to use.
    text = text.replace("\u202f", " ").replace("\u2011", "-")

    # Drop a trailing "**Sources**" section entirely — citation
    # blocks aren't meant to be spoken aloud.
    text = re.split(r"\*\*\s*Sources\s*\*\*", text, maxsplit=1, flags=re.IGNORECASE)[0]

    # Drop any remaining inline citation brackets, e.g.
    # "[Doc 1 | Source: ... | Section: Page 21]"
    text = re.sub(r"\[Doc[^\]]*\]", "", text, flags=re.IGNORECASE)

    # Bold / italic markers: **text** or *text* -> text
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)

    # Markdown headers: "## Heading" -> "Heading"
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)

    # Bullet markers at line start: "- " / "* " / "• " -> nothing
    text = re.sub(r"^\s*[\-\*\u2022]\s+", "", text, flags=re.MULTILINE)

    # Collapse newlines and repeated whitespace into speakable pauses.
    text = re.sub(r"\n+", ". ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


def create_tts(text, output_file=DEFAULT_OUTPUT_FILE):
    """
    Generates speech for `text` and writes it to `output_file` as a
    16kHz/16-bit/mono WAV.

    Returns the output file path on success, or None on failure.
    """
    text = clean_for_speech(text)
    if not text:
        print("[TTS] ERROR: Empty text.")
        return None

    if is_hindi(text):
        voice, language = HINDI_VOICE, "Hindi"
    else:
        voice, language = ENGLISH_VOICE, "English"

    print(f"[TTS] ({language}) {text!r} -> voice: {voice}")

    if not os.path.exists(voice):
        print("[TTS] ERROR: Voice model not found:", voice)
        return None

    temp_file = "piper_temp.wav"
    command = ["piper", "--model", voice, "--output_file", temp_file]

    try:
        subprocess.run(command, input=text, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print("[TTS] Piper failed:", e)
        return None
    except FileNotFoundError:
        print("[TTS] ERROR: 'piper' executable not found on PATH.")
        return None

    with wave.open(temp_file, "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())

    # Stereo -> mono
    if channels == 2:
        frames = audioop.tomono(frames, sample_width, 0.5, 0.5)
        channels = 1
    elif channels != 1:
        print("[TTS] ERROR: Unsupported channel count:", channels)
        return None

    # Resample -> 16 kHz
    if sample_rate != TARGET_RATE:
        frames, _ = audioop.ratecv(
            frames, sample_width, channels, sample_rate, TARGET_RATE, None
        )

    if sample_width != TARGET_WIDTH:
        print("[TTS] ERROR: Piper produced", sample_width * 8, "bit audio.")
        return None

    with wave.open(output_file, "wb") as wav:
        wav.setnchannels(TARGET_CHANNELS)
        wav.setsampwidth(TARGET_WIDTH)
        wav.setframerate(TARGET_RATE)
        wav.writeframes(frames)

    if os.path.exists(temp_file):
        os.remove(temp_file)

    print("[TTS] Wrote", output_file)
    return output_file


def create_tts_cached(key, text, cache_dir=CACHE_DIR):
    """
    Generates TTS for `text` once and reuses the cached WAV on every
    later call with the same `key` — for fixed phrases (greetings,
    canned acknowledgments) that don't need regenerating every time.

    Delete the file under cache_dir if you change the wording and
    want it regenerated.
    """
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{key}.wav")

    if os.path.exists(path):
        return path

    return create_tts(text, output_file=path)


def concat_wavs(paths, output_path):
    """
    Concatenates several 16kHz/16-bit/mono WAVs (e.g. a cached fixed
    phrase + a freshly synthesized dynamic value) into one file.
    """
    frames = []
    params = None

    for p in paths:
        with wave.open(p, "rb") as w:
            if params is None:
                params = w.getparams()
            frames.append(w.readframes(w.getnframes()))

    with wave.open(output_path, "wb") as out:
        out.setparams(params)
        for f in frames:
            out.writeframes(f)

    return output_path


if __name__ == "__main__":
    import sys

    text = " ".join(sys.argv[1:]) or "Hello, how are you?"
    create_tts(text)
