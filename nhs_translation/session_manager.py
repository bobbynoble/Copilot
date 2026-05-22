from __future__ import annotations

import uuid
from typing import Optional

from fastapi import WebSocket


class Session:
    def __init__(self, session_id: str, patient_lang: str):
        self.session_id  = session_id
        self.patient_lang = patient_lang
        self.nurse_ws:   Optional[WebSocket] = None
        self.patient_ws: Optional[WebSocket] = None

    @property
    def nurse_connected(self)   -> bool: return self.nurse_ws   is not None
    @property
    def patient_connected(self) -> bool: return self.patient_ws is not None

    async def send_nurse(self, data: dict) -> None:
        if self.nurse_ws:
            try:   await self.nurse_ws.send_json(data)
            except Exception: pass

    async def send_patient(self, data: dict) -> None:
        if self.patient_ws:
            try:   await self.patient_ws.send_json(data)
            except Exception: pass


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create(self, patient_lang: str) -> Session:
        sid     = uuid.uuid4().hex[:8]
        session = Session(sid, patient_lang)
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


session_manager = SessionManager()
