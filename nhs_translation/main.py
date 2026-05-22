"""
NHS Translation Bot — FastAPI application.

Endpoints
---------
GET  /                              — Web UI (index.html)
GET  /reception                     — Nurse / reception desk view
GET  /patient/{session_id}          — Patient phone view
GET  /health                        — Liveness check
GET  /api/languages                 — List supported languages
GET  /api/voices                    — List available camb.ai voices
GET  /api/network-url               — Local network URL for QR code generation
POST /api/session                   — Create a new consultation session
GET  /api/session/{session_id}      — Get session info / connection status
POST /api/translate/text            — Translate text + optional TTS
POST /api/translate/audio           — Start audio dubbing job
GET  /api/translate/audio/{task_id} — Poll dubbing job status
WS   /ws/{session_id}/{role}        — Real-time nurse ↔ patient channel
"""

from __future__ import annotations

import logging
import os
import socket
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
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
from nhs_translation.session_manager import session_manager

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


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")

@app.get("/reception", include_in_schema=False)
async def reception() -> FileResponse:
    return FileResponse(_STATIC / "reception.html")

@app.get("/patient/{session_id}", include_in_schema=False)
async def patient(session_id: str) -> FileResponse:
    return FileResponse(_STATIC / "patient.html")


# ── System ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")

@app.get("/api/network-url", tags=["System"], summary="Local network URL for QR code")
async def network_url(request: Request) -> dict:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"
    port = request.url.port or 8001
    return {"url": f"http://{local_ip}:{port}"}


# ── Session ───────────────────────────────────────────────────────────────────

@app.post("/api/session", tags=["Session"], summary="Create a new consultation session")
async def create_session(body: dict) -> dict:
    patient_lang = body.get("patient_lang", "AR_SA")
    session = session_manager.create(patient_lang)
    lang_name = LANG_CONFIG.get(patient_lang, (patient_lang,))[0]
    return {
        "session_id":       session.session_id,
        "patient_lang":     patient_lang,
        "patient_lang_name": lang_name,
    }

@app.get("/api/session/{session_id}", tags=["Session"], summary="Get session info")
async def get_session(session_id: str) -> dict:
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    lang_name = LANG_CONFIG.get(session.patient_lang, (session.patient_lang,))[0]
    return {
        "session_id":        session_id,
        "patient_lang":      session.patient_lang,
        "patient_lang_name": lang_name,
        "nurse_connected":   session.nurse_connected,
        "patient_connected": session.patient_connected,
    }


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/{session_id}/{role}")
async def ws_endpoint(websocket: WebSocket, session_id: str, role: str) -> None:
    if role not in ("nurse", "patient"):
        await websocket.close(code=4003)
        return

    session = session_manager.get(session_id)
    if not session:
        await websocket.close(code=4004)
        return

    await websocket.accept()

    if role == "nurse":
        session.nurse_ws = websocket
        await session.send_patient({"type": "status", "message": "nurse_connected"})
    else:
        session.patient_ws = websocket
        await session.send_nurse({"type": "status", "message": "patient_connected"})

    lang_name = LANG_CONFIG.get(session.patient_lang, (session.patient_lang,))[0]
    await websocket.send_json({
        "type":             "ready",
        "patient_lang":     session.patient_lang,
        "patient_lang_name": lang_name,
    })

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") != "speech":
                continue

            text        = data.get("text", "").strip()
            source_lang = data.get("source_lang", "EN_GB")
            target_lang = data.get("target_lang", session.patient_lang)

            if not text:
                continue

            await websocket.send_json({"type": "processing"})

            try:
                translated_list = await translate_texts([text], source_lang, target_lang)
                translated      = translated_list[0] if translated_list else ""
                audio_b64       = await generate_tts(translated, target_lang)
            except Exception as exc:
                logger.exception("WS translation failed")
                await websocket.send_json({"type": "error", "message": str(exc)})
                continue

            payload = {
                "type":        "translation",
                "original":    text,
                "translated":  translated,
                "audio_base64": audio_b64,
                "from_role":   role,
            }

            if role == "nurse":
                await session.send_patient(payload)
            else:
                await session.send_nurse(payload)

            # Confirm to sender (no audio — they already heard themselves)
            await websocket.send_json({
                "type":       "sent",
                "original":   text,
                "translated": translated,
            })

    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if role == "nurse":
            session.nurse_ws = None
            await session.send_patient({"type": "status", "message": "nurse_disconnected"})
        else:
            session.patient_ws = None
            await session.send_nurse({"type": "status", "message": "patient_disconnected"})
        logger.info("WS disconnected: session=%s role=%s", session_id, role)


# ── Translation ───────────────────────────────────────────────────────────────

@app.get("/api/languages", response_model=list[LanguageOption], tags=["Translation"])
async def list_languages() -> list[LanguageOption]:
    return [LanguageOption(code=code, name=name) for code, (name, _) in LANG_CONFIG.items()]

@app.get("/api/voices", tags=["Translation"])
async def list_voices() -> list[dict]:
    voices = await get_voices()
    return [{"id": v["id"], "name": v.get("voice_name", str(v["id"]))} for v in voices]

@app.post("/api/translate/text", response_model=TextTranslationResponse, tags=["Translation"])
async def translate_text(body: TextTranslationRequest) -> TextTranslationResponse:
    try:
        source = body.source_language
        if not source:
            source = await detect_language(body.text)
        detected_name = LANG_CONFIG.get(source, (source,))[0]
        translated_list = await translate_texts([body.text], source, body.target_language)
        translated = translated_list[0] if translated_list else ""
        audio_b64  = await generate_tts(translated, body.target_language)
        return TextTranslationResponse(
            success=True, detected_language=detected_name,
            translated_text=translated, audio_base64=audio_b64,
        )
    except Exception as exc:
        logger.exception("Text translation failed")
        return TextTranslationResponse(success=False, error_message=str(exc))

@app.post("/api/translate/audio", response_model=DubbingStartResponse, tags=["Dubbing"])
async def dub_audio(body: AudioDubbingRequest) -> DubbingStartResponse:
    try:
        task_id = await start_dubbing(body.audio_url, body.source_language, body.target_language)
        return DubbingStartResponse(success=True, task_id=task_id)
    except Exception as exc:
        logger.exception("Failed to start dubbing job")
        return DubbingStartResponse(success=False, error_message=str(exc))

@app.get("/api/translate/audio/{task_id}", response_model=DubbingStatusResponse, tags=["Dubbing"])
async def dubbing_status(task_id: str) -> DubbingStatusResponse:
    try:
        result = await get_dubbing_status(task_id)
        return DubbingStatusResponse(success=True, status=result["status"], audio_url=result.get("audio_url"))
    except Exception as exc:
        logger.exception("Failed to fetch dubbing status for %s", task_id)
        return DubbingStatusResponse(success=False, status="ERROR", error_message=str(exc))
