"""Data models for identity matching."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class MatchTier(str, Enum):
    NHS_NUMBER = "nhs_number"
    DEMOGRAPHIC = "demographic"


class MatchDecision(str, Enum):
    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"
    POTENTIAL_DUPLICATE = "POTENTIAL_DUPLICATE"


@dataclass
class PatientRecord:
    """
    Represents a single patient record from a PAS system.

    All string fields are normalised on creation (stripped, uppercased).
    nhs_number may include spaces/hyphens — they are removed automatically.
    """

    source_system: str
    local_id: str
    nhs_number: str = ""
    surname: str = ""
    forename: str = ""
    date_of_birth: Optional[date] = None
    sex: str = ""  # "M", "F", or "U"
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        self.nhs_number = re.sub(r"[\s\-]", "", self.nhs_number)
        self.surname = self.surname.strip().upper()
        self.forename = self.forename.strip().upper()
        self.sex = self.sex.strip().upper()


@dataclass
class MatchResult:
    record_a: PatientRecord
    record_b: PatientRecord
    decision: MatchDecision
    tier: Optional[MatchTier]
    matched_fields: list[str] = field(default_factory=list)
    notes: str = ""
