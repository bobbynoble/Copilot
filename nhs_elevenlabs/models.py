from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel


class LanguageOption(BaseModel):
    code: str   # Languages enum name, e.g. "EN_GB"
    name: str   # Display name, e.g. "English (UK)"


class TextTranslationRequest(BaseModel):
    text: str
    target_language: str            # Languages enum name
    source_language: Optional[str] = None   # None = auto-detect via Claude


class TextTranslationResponse(BaseModel):
    success: bool
    detected_language: Optional[str] = None     # human-readable
    translated_text: Optional[str] = None
    audio_base64: Optional[str] = None          # base64 MP3
    error_message: Optional[str] = None


class AudioDubbingRequest(BaseModel):
    audio_url: str
    source_language: str    # Languages enum name
    target_language: str    # Languages enum name


class DubbingStartResponse(BaseModel):
    success: bool
    task_id: Optional[str] = None
    error_message: Optional[str] = None


class DubbingStatusResponse(BaseModel):
    success: bool
    status: str                         # "PENDING" | "SUCCESS" | "ERROR"
    audio_url: Optional[str] = None
    error_message: Optional[str] = None


class ImageTranslationRequest(BaseModel):
    image_base64: str               # base64-encoded image data
    image_media_type: str = "image/jpeg"   # image/jpeg | image/png | image/webp
    target_language: str            # Languages enum name


class ImageTranslationResponse(BaseModel):
    success: bool
    original_text: Optional[str] = None    # text read from the sign
    translated_text: Optional[str] = None  # translated into target language
    audio_base64: Optional[str] = None     # spoken translation
    error_message: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
