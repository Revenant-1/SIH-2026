"""
Detects a spoken "I want to file a complaint" request, files it
against the backend, and builds:

  - a reply that's MOSTLY pre-built (a fixed acknowledgment phrase,
    synthesized once and cached, read consistently every time) with
    just the dynamic ticket number stitched on freshly
  - the text to show on the OLED via the TEXT protocol

Matching is loose keyword matching, not an exact phrase — so
several ways of phrasing "I want to file a complaint in my
cooperative" will still trigger it, not just the one exact sentence.
"""

import backend_client
import tts

GRIEVANCE_KEYWORDS = ("shikayat", "complaint", "grievance")
FILING_KEYWORDS = ("darj", "file", "raise", "register", "lodge")

ACK_TEXT = "Aapki shikayat darj ki ja rahi hai."
TICKET_LEAD_IN_TEXT = "Aapka ticket number hai"
TICKET_TRAILER_TEXT = "Is number ka upyog tracking ke liye karein."


def is_grievance_request(text):
    """
    True if `text` looks like a request to file a grievance/
    complaint — needs a "topic" word (shikayat/complaint/grievance)
    AND an "action" word (darj/file/raise/register/lodge), so a
    passing mention of "complaint" alone in some other sentence
    doesn't false-trigger this.
    """
    lowered = text.lower()
    has_topic = any(k in lowered for k in GRIEVANCE_KEYWORDS)
    has_action = any(k in lowered for k in FILING_KEYWORDS)
    return has_topic and has_action


def file_grievance(text, output_wav="grievance_reply.wav"):
    """
    Files the grievance and builds the spoken reply + display text.

    Returns (wav_path, display_text) on success, or (None, error_text)
    if filing failed (most commonly: still logged in as a guest —
    see backend_client.file_grievance's docstring).
    """
    try:
        ticket_id = backend_client.file_grievance(text)
    except Exception as e:
        error_text = f"Maaf kijiye, shikayat darj nahi ho paayi. ({e})"
        return None, error_text

    ack_path = tts.create_tts_cached("grievance_ack", ACK_TEXT)
    lead_in_path = tts.create_tts_cached("grievance_lead_in", TICKET_LEAD_IN_TEXT)
    trailer_path = tts.create_tts_cached("grievance_trailer", TICKET_TRAILER_TEXT)

    # Only the ticket number itself is synthesized fresh each time.
    number_path = tts.create_tts(str(ticket_id), output_file="grievance_number.wav")
    if not number_path:
        error_text = "Shikayat darj ho gayi, lekin ticket number bolne mein samasya hui."
        return None, error_text

    wav_path = tts.concat_wavs(
        [ack_path, lead_in_path, number_path, trailer_path],
        output_wav,
    )

    display_text = (
        f"Shikayat darj ho gayi.\nTicket: {ticket_id}\n"
        f"Tracking ke liye is number ka upyog karein."
    )

    return wav_path, display_text
