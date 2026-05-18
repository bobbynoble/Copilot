"""
NHS Translation Bot — FastAPI application.

Endpoints
---------
GET  /                              — Web UI (index.html)
GET  /health                        — Liveness check
GET  /api/languages                 — List supported languages
GET  /api/voices                    — List available camb.ai voices
GET  /api/network-url               — Local network URL for QR code generation
POST /api/translate/text            — Translate text + optional TTS
POST /api/translate/audio           — Start audio dubbing job
GET  /api/translate/audio/{task_id} — Poll dubbing job status
"""

from __future__ import annotations

import logging
import os
import socket
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from nhs_translation.agent import (
    LANG_CONFIG,
    detect_language,
    generate_tts,
    get_dubbing_status,
    get_voices,
    start_dubbing,
    translate_texts,
)
from nhs_translation.models import (
    AudioDubbingRequest,
    DubbingStartResponse,
    DubbingStatusResponse,
    HealthResponse,
    LanguageOption,
    TextTranslationRequest,
    TextTranslationResponse,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

_STATIC = Path(__file__).parent / "static"

app = FastAPI(
    title="NHS Translation Bot",
    description=(
        "AI-powered translation and audio dubbing for NHS patient communication. "
        "Powered by camb.ai (translation + TTS/dubbing) and Claude (language detection)."
    ),
    version="1.0.0",
    contact={"name": "bobbynoble"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/network-url", tags=["System"], summary="Local network URL for QR code")
async def network_url(request: Request) -> dict:
    """Returns the URL other devices on the same network can use to reach this app."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"
    port = request.url.port or 8001
    return {"url": f"http://{local_ip}:{port}"}


@app.get(
    "/api/languages",
    response_model=list[LanguageOption],
    summary="List supported languages",
    tags=["Translation"],
)
async def list_languages() -> list[LanguageOption]:
    return [LanguageOption(code=code, name=name) for code, (name, _) in LANG_CONFIG.items()]


@app.get(
    "/api/voices",
    summary="List available camb.ai TTS voices",
    tags=["Translation"],
)
async def list_voices() -> list[dict]:
    voices = await get_voices()
    return [{"id": v["id"], "name": v.get("voice_name", str(v["id"]))} for v in voices]


@app.post(
    "/api/translate/text",
    response_model=TextTranslationResponse,
    summary="Translate text and generate spoken audio",
    tags=["Translation"],
    responses={
        200: {"description": "Translation and TTS completed"},
        422: {"description": "Validation error"},
        500: {"description": "Translation failed"},
    },
)
async def translate_text(body: TextTranslationRequest) -> TextTranslationResponse:
    try:
        source = body.source_language
        detected_name: str | None = None

        if not source:
            source = await detect_language(body.text)
            detected_name = LANG_CONFIG.get(source, (source,))[0]
        else:
            detected_name = LANG_CONFIG.get(source, (source,))[0]

        translated_list = await translate_texts(
            texts=[body.text],
            source_lang=source,
            target_lang=body.target_language,
        )
        translated = translated_list[0] if translated_list else ""

        audio_b64 = await generate_tts(translated, body.target_language)

        return TextTranslationResponse(
            success=True,
            detected_language=detected_name,
            translated_text=translated,
            audio_base64=audio_b64,
        )

    except Exception as exc:
        logger.exception("Text translation failed")
        return TextTranslationResponse(success=False, error_message=str(exc))


@app.post(
    "/api/translate/audio",
    response_model=DubbingStartResponse,
    summary="Start an audio dubbing job",
    tags=["Dubbing"],
    responses={
        200: {"description": "Dubbing job started — poll GET /api/translate/audio/{task_id}"},
        422: {"description": "Validation error"},
        500: {"description": "Failed to start dubbing job"},
    },
)
async def dub_audio(body: AudioDubbingRequest) -> DubbingStartResponse:
    try:
        task_id = await start_dubbing(
            audio_url=body.audio_url,
            source_lang=body.source_language,
            target_lang=body.target_language,
        )
        return DubbingStartResponse(success=True, task_id=task_id)
    except Exception as exc:
        logger.exception("Failed to start dubbing job")
        return DubbingStartResponse(success=False, error_message=str(exc))


@app.get(
    "/api/translate/audio/{task_id}",
    response_model=DubbingStatusResponse,
    summary="Poll the status of an audio dubbing job",
    tags=["Dubbing"],
)
async def dubbing_status(task_id: str) -> DubbingStatusResponse:
    try:
        result = await get_dubbing_status(task_id)
        return DubbingStatusResponse(
            success=True,
            status=result["status"],
            audio_url=result.get("audio_url"),
        )
    except Exception as exc:
        logger.exception("Failed to fetch dubbing status for %s", task_id)
        return DubbingStatusResponse(
            success=False,
            status="ERROR",
            error_message=str(exc),
        )
