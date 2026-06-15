from __future__ import annotations

import base64
import json
import logging
import os
from typing import Optional

import anthropic
import httpx

logger = logging.getLogger(__name__)

ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
ELEVENLABS_TTS_MODEL = "eleven_multilingual_v2"

# NHS-relevant languages. Display names are used as the translation target
# in Claude prompts; codes ending in languages not covered by ElevenLabs'
# multilingual model will still be attempted but may sound less natural.
LANG_CONFIG: dict[str, str] = {
    "EN_GB": "English (UK)",
    "AR_SA": "Arabic (العربية)",
    "BN_BD": "Bengali (বাংলা)",
    "ZH_CN": "Chinese Mandarin (普通话)",
    "CY_GB": "Welsh (Cymraeg)",
    "FR_FR": "French (Français)",
    "GU_IN": "Gujarati (ગુજરાતી)",
    "HI_IN": "Hindi (हिन्दी)",
    "PL_PL": "Polish (Polski)",
    "PT_BR": "Portuguese (Português)",
    "PA_IN": "Punjabi (ਪੰਜਾਬੀ)",
    "RO_RO": "Romanian (Română)",
    "SO_SO": "Somali (Soomaali)",
    "ES_ES": "Spanish (Español)",
    "TA_IN": "Tamil (தமிழ்)",
    "TR_TR": "Turkish (Türkçe)",
    "UR_PK": "Urdu (اردو)",
}

# ISO 639-1 codes expected by the ElevenLabs dubbing API
ELEVENLABS_LANG_CODE: dict[str, str] = {
    "EN_GB": "en", "AR_SA": "ar", "BN_BD": "bn", "ZH_CN": "zh",
    "CY_GB": "cy", "FR_FR": "fr", "GU_IN": "gu", "HI_IN": "hi",
    "PL_PL": "pl", "PT_BR": "pt", "PA_IN": "pa", "RO_RO": "ro",
    "SO_SO": "so", "ES_ES": "es", "TA_IN": "ta", "TR_TR": "tr",
    "UR_PK": "ur",
}

_anthropic_client: Optional[anthropic.AsyncAnthropic] = None
_voices_cache: Optional[list] = None


def _get_anthropic() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic()
    return _anthropic_client


def _elevenlabs_headers() -> dict:
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY environment variable is not set.")
    return {"xi-api-key": key}


async def get_voices() -> list:
    global _voices_cache
    if _voices_cache is None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{ELEVENLABS_API_BASE}/voices", headers=_elevenlabs_headers())
            resp.raise_for_status()
            _voices_cache = resp.json().get("voices", [])
    return _voices_cache or []


async def _default_voice_id() -> Optional[str]:
    voices = await get_voices()
    return voices[0]["voice_id"] if voices else None


async def detect_language(text: str) -> str:
    """Use Claude to detect the language of text, returning a LANG_CONFIG key."""
    client = _get_anthropic()
    lang_list = "\n".join(f"{code}: {name}" for code, name in LANG_CONFIG.items())

    msg = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=20,
        messages=[{
            "role": "user",
            "content": (
                f"Detect the language of the text below. "
                f"Respond with ONLY the code from this list that best matches:\n\n"
                f"{lang_list}\n\n"
                f"Text: {text[:500]}\n\n"
                f"Code:"
            ),
        }],
    )

    detected = msg.content[0].text.strip().upper().split()[0]
    return detected if detected in LANG_CONFIG else "EN_GB"


async def translate_texts(texts: list[str], source_lang: str, target_lang: str) -> list[str]:
    """Translate a list of strings to the target language using Claude."""
    if source_lang == target_lang:
        return texts

    client = _get_anthropic()
    source_name = LANG_CONFIG.get(source_lang, source_lang)
    target_name = LANG_CONFIG.get(target_lang, target_lang)
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))

    msg = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                f"Translate the following numbered lines from {source_name} to {target_name}. "
                f"Respond with ONLY the translations, one per line, in the same numbered format "
                f"(e.g. \"1. ...\"). Do not add any other commentary.\n\n{numbered}"
            ),
        }],
    )

    translations = []
    for line in msg.content[0].text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(". ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            translations.append(parts[1])
        else:
            translations.append(line)

    if len(translations) != len(texts):
        logger.warning("Translation count mismatch (%d != %d) — returning originals", len(translations), len(texts))
        return texts
    return translations


async def generate_tts(text: str, target_lang: str) -> Optional[str]:
    """Convert text to speech via ElevenLabs TTS. Returns base64-encoded MP3 or None."""
    try:
        voice_id = await _default_voice_id()
        if voice_id is None:
            logger.warning("No ElevenLabs voices available — skipping TTS")
            return None

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{ELEVENLABS_API_BASE}/text-to-speech/{voice_id}",
                headers={**_elevenlabs_headers(), "Content-Type": "application/json"},
                json={
                    "text": text,
                    "model_id": ELEVENLABS_TTS_MODEL,
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                },
            )
            resp.raise_for_status()
            return base64.b64encode(resp.content).decode()

    except Exception:
        logger.exception("ElevenLabs TTS generation failed for language %s", target_lang)
        return None


async def translate_image_sign(image_base64: str, image_media_type: str, target_lang: str) -> dict:
    """Read text from a sign image via Claude vision, translate it, and generate TTS.

    Returns dict with: original_text, translated_text, audio_base64 (may be None).
    """
    client = _get_anthropic()
    target_name = LANG_CONFIG.get(target_lang, target_lang)

    msg = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": image_media_type, "data": image_base64},
                },
                {
                    "type": "text",
                    "text": (
                        f"This is a photo of a hospital sign or notice. "
                        f"1. Extract the main text from the sign exactly as written. "
                        f"2. Translate that text into {target_name}. "
                        f"Respond in JSON only, with keys \"original\" and \"translated\". "
                        f"If there is no readable text, set both to empty string."
                    ),
                },
            ],
        }],
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
        original_text   = parsed.get("original", "").strip()
        translated_text = parsed.get("translated", "").strip()
    except (json.JSONDecodeError, AttributeError):
        original_text   = raw
        translated_text = raw

    audio_b64 = None
    if translated_text:
        audio_b64 = await generate_tts(translated_text, target_lang)

    return {
        "original_text":   original_text,
        "translated_text": translated_text,
        "audio_base64":    audio_b64,
    }


async def moderate_content(text: str) -> dict:
    """Check message for abuse or safeguarding concerns before translation.

    Returns dict with:
      action: "allow" | "block" | "flag"
      reason: shown to sender if blocked (user-friendly)
      alert:  shown to nurse if flagged (safeguarding concern summary)
    """
    client = _get_anthropic()

    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": (
                "You are a content moderation assistant for an NHS hospital translation service.\n"
                "Classify the following message and respond with JSON only.\n\n"
                "Rules:\n"
                "- BLOCK if the message contains threats, severe abuse, hate speech, or is clearly attempting to misuse the service\n"
                "- FLAG if the message suggests the patient may be at risk: mentions of self-harm, suicidal thoughts, domestic abuse, child safeguarding concerns, or expressions of serious distress\n"
                "- ALLOW everything else (including mild frustration, complaints, and normal clinical conversation)\n\n"
                "Respond with JSON only, one of:\n"
                "{\"action\":\"allow\"}\n"
                "{\"action\":\"block\",\"reason\":\"<brief user-facing explanation>\"}\n"
                "{\"action\":\"flag\",\"alert\":\"<brief safeguarding summary for nurse>\"}\n\n"
                f"Message: {text[:1000]}"
            ),
        }],
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()

    try:
        result = json.loads(raw)
        action = result.get("action", "allow")
        if action not in ("allow", "block", "flag"):
            return {"action": "allow"}
        return result
    except (json.JSONDecodeError, AttributeError):
        return {"action": "allow"}


async def start_dubbing(audio_url: str, source_lang: str, target_lang: str) -> str:
    """Submit an audio dubbing job to ElevenLabs. Returns the dubbing_id."""
    target_code = ELEVENLABS_LANG_CODE.get(target_lang, "en")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{ELEVENLABS_API_BASE}/dubbing",
            headers=_elevenlabs_headers(),
            data={"source_url": audio_url, "target_lang": target_code},
        )
        resp.raise_for_status()
        return resp.json()["dubbing_id"]


async def get_dubbing_status(task_id: str, target_lang: str = "EN_GB") -> dict:
    """Poll ElevenLabs for dubbing job status. Returns dict with status and audio_url."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{ELEVENLABS_API_BASE}/dubbing/{task_id}", headers=_elevenlabs_headers())
        resp.raise_for_status()
        data = resp.json()

    status = data.get("status")
    if status == "dubbed":
        return {"status": "SUCCESS", "audio_url": f"/api/translate/audio/{task_id}/file?target_lang={target_lang}"}
    if status == "failed":
        return {"status": "ERROR", "audio_url": None}
    return {"status": "PENDING", "audio_url": None}


async def fetch_dubbed_audio(task_id: str, target_lang: str) -> bytes:
    """Download the finished dub for the given language from ElevenLabs."""
    target_code = ELEVENLABS_LANG_CODE.get(target_lang, "en")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            f"{ELEVENLABS_API_BASE}/dubbing/{task_id}/audio/{target_code}",
            headers=_elevenlabs_headers(),
        )
        resp.raise_for_status()
        return resp.content
