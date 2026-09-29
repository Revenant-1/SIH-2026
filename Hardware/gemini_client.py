"""
Talks directly to Gemini instead of going through the Nayak
backend's /api/command endpoint — no server round-trip for general
Q&A. Grievance filing still goes through backend_client.file_grievance()
since that needs the actual backend database to create a ticket.

Install:
    pip install google-genai

Get a key from https://aistudio.google.com/app/apikey, then either:
    export GEMINI_API_KEY="your-key-here"
or set GEMINI_API_KEY below directly.
"""

import os

from google import genai
from google.genai import types

MODEL = "gemini-3.5-flash"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

SYSTEM_INSTRUCTION = (
    "You are Nayak, a helpful voice assistant for a farming "
    "cooperative. Always answer in very simple language and keep "
    "your answers as short as possible — they will be read aloud "
    "over a speaker, not displayed as text."
)

_client = None
_chat = None


def _get_chat():
    global _client, _chat

    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Get one at "
                "https://aistudio.google.com/app/apikey and either "
                "export it as an environment variable or set it "
                "directly in gemini_client.py."
            )
        _client = genai.Client(api_key=GEMINI_API_KEY)

    if _chat is None:
        _chat = _client.chats.create(
            model=MODEL,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
            ),
        )

    return _chat


def ask(text):
    """
    Sends recognized text straight to Gemini and returns its answer.
    Keeps conversational context across calls via a persistent chat
    session — call reset_chat() to start a fresh conversation.
    """
    chat = _get_chat()
    response = chat.send_message(text.strip())
    return response.text


def reset_chat():
    """Starts a brand-new conversation (e.g. after a long idle gap)."""
    global _chat
    _chat = None
