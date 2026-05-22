from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
from typing import Optional

import anthropic
from camb.client import CambAI, save_stream_to_file
from camb.types.language_enums import Languages
from camb.types.stream_tts_output_configuration import StreamTtsOutputConfiguration

logger = logging.getLogger(__name__)

# NHS-relevant languages supported by camb.ai
# key = Languages enum name, value = (display_name, tts_language_code)
LANG_CONFIG: dict[str, tuple[str, str]] = {
    "EN_GB": ("English (UK)", "en-us"),       # mars-flash uses en-us not en-gb
    "AR_SA": ("Arabic (العربية)", "ar-sa"),
    "BN_BD": ("Bengali (বাংলা)", "bn-bd"),
    "ZH_CN": ("Chinese Mandarin (普通话)", "zh-cn"),
    "CY_GB": ("Welsh (Cymraeg)", "en-us"),    # not supported by TTS, falls back to en-us
    "FR_FR": ("French (Français)", "fr-fr"),
    "GU_IN": ("Gujarati (ગુજરાતી)", "hi-in"), # not supported, closest is hi-in
    "HI_IN": ("Hindi (हिन्दी)", "hi-in"),
    "PL_PL": ("Polish (Polski)", "pl-pl"),
    "PT_BR": ("Portuguese (Português)", "pt-br"),
    "PA_IN": ("Punjabi (ਪੰਜਾਬੀ)", "pa-in"),
    "RO_RO": ("Romanian (Română)", "en-us"),  # not supported by TTS
    "SO_SO": ("Somali (Soomaali)", "en-us"),  # not supported by TTS
    "ES_ES": ("Spanish (Español)", "es-es"),
    "TA_IN": ("Tamil (தமிழ்)", "ta-in"),
    "TR_TR": ("Turkish (Türkçe)", "tr-tr"),
    "UR_PK": ("Urdu (اردو)", "hi-in"),        # not supported, closest is hi-in
}

_camb_client: Optional[CambAI] = None
_anthropic_client: Optional[anthropic.AsyncAnthropic] = None
_voices_cache: Optional[list] = None


def _get_camb() -> CambAI:
    global _camb_client
    if _camb_client is None:
        key = os.getenv("CAMB_API_KEY")
        if not key:
            raise RuntimeError("CAMB_API_KEY environment variable is not set.")
        _camb_client = CambAI(api_key=key)
    return _camb_client


def _get_anthropic() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic()
    return _anthropic_client


async def get_voices() -> list:
    global _voices_cache
    if _voices_cache is None:
        client = _get_camb()
        _voices_cache = await asyncio.to_thread(client.voice_cloning.list_voices)
    return _voices_cache or []


async def _default_voice_id() -> Optional[int]:
    voices = await get_voices()
    return voices[0]["id"] if voices else None


async def detect_language(text: str) -> str:
    """Use Claude to detect the language of text, returning a LANG_CONFIG key."""
    client = _get_anthropic()
    lang_list = "\n".join(f"{code}: {name}" for code, (name, _) in LANG_CONFIG.items())

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
    if detected in LANG_CONFIG:
        return detected
    # Validate it at least exists in the Languages enum; fall back to EN_GB
    try:
        getattr(Languages, detected)
        return detected
    except AttributeError:
        return "EN_GB"


async def translate_texts(texts: list[str], source_lang: str, target_lang: str) -> list[str]:
    """Translate a list of strings via camb.ai translation API (polls until done)."""
    client = _get_camb()
    src = getattr(Languages, source_lang)
    tgt = getattr(Languages, target_lang)

    def _create() -> str:
        resp = client.translation.create_translation(
            texts=texts,
            source_language=src,
            target_language=tgt,
        )
        return resp["task_id"]

    task_id = await asyncio.to_thread(_create)

    for _ in range(60):
        await asyncio.sleep(1)

        def _poll():
            return client.translation.get_translation_task_status(task_id)

        status = await asyncio.to_thread(_poll)

        if status.status == "SUCCESS":
            run_id = status.run_id

            def _fetch():
                return client.translation.get_translation_result(run_id=run_id)

            result = await asyncio.to_thread(_fetch)
            return result.texts
        if status.status == "ERROR":
            raise RuntimeError("camb.ai translation job failed.")

    raise TimeoutError("Translation timed out after 60 seconds.")


async def generate_tts(text: str, target_lang: str) -> Optional[str]:
    """Convert text to speech via camb.ai TTS. Returns base64-encoded MP3 or None."""
    try:
        client = _get_camb()
        voice_id = await _default_voice_id()
        if voice_id is None:
            logger.warning("No voices available — skipping TTS")
            return None

        tts_code = LANG_CONFIG.get(target_lang, ("", "en-gb"))[1]

        def _sync_tts() -> str:
            stream = client.text_to_speech.tts(
                text=text,
                language=tts_code,
                speech_model="mars-flash",
                voice_id=voice_id,
                output_configuration=StreamTtsOutputConfiguration(format="mp3"),
            )
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                path = tmp.name
            save_stream_to_file(stream, path)
            with open(path, "rb") as f:
                data = f.read()
            os.unlink(path)
            return base64.b64encode(data).decode()

        return await asyncio.to_thread(_sync_tts)

    except Exception:
        logger.exception("TTS generation failed for language %s", target_lang)
        return None


async def start_dubbing(audio_url: str, source_lang: str, target_lang: str) -> str:
    """Submit an audio dubbing job to camb.ai. Returns the task_id."""
    client = _get_camb()
    src = getattr(Languages, source_lang)
    tgt = getattr(Languages, target_lang)

    def _start() -> str:
        result = client.dub.create_dub(
            video_url=audio_url,
            source_language=src,
            target_language=tgt,
        )
        return result.task_id

    return await asyncio.to_thread(_start)


async def get_dubbing_status(task_id: str) -> dict:
    """Poll camb.ai for dubbing job status. Returns dict with status and audio_url."""
    client = _get_camb()

    def _poll():
        return client.dub.get_dubbing_status(task_id=task_id)

    status = await asyncio.to_thread(_poll)

    if status.status == "SUCCESS":
        run_id = status.run_id

        def _info():
            return client.dub.get_dubbed_run_info(run_id)

        info = await asyncio.to_thread(_info)

        # Single-target dub returns DubbingResult; multi returns Dict[str, DubbingResult]
        if isinstance(info, dict):
            first = next(iter(info.values()))
            audio_url = first.audio_url
        else:
            audio_url = info.audio_url

        return {"status": "SUCCESS", "audio_url": audio_url}

    if status.status == "ERROR":
        return {"status": "ERROR", "audio_url": None}

    return {"status": "PENDING", "audio_url": None}
