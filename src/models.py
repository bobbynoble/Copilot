from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ── Request models ────────────────────────────────────────────────────────────

class AnalyzeRFPRequest(BaseModel):
    """Input payload for the RFP analysis endpoint."""

    rfp_document: str = Field(
        ...,
        description=(
            "The original RFP / tender document content — requirements, "
            "evaluation criteria, instructions to bidders, statement of work, etc."
        ),
        min_length=50,
        examples=["This Request for Proposal (RFP) seeks vendors to provide..."],
    )
    response_document: str = Field(
        ...,
        description=(
            "The submitted RFP response / bid document to evaluate — "
            "the vendor's technical approach, pricing, team, timeline, etc."
        ),
        min_length=50,
        examples=["Our company, Acme Corp, proposes the following solution..."],
    )
    evaluation_criteria: Optional[Dict[str, float]] = Field(
        None,
        description=(
            "Optional custom evaluation criteria with percentage weights that must sum to 100. "
            "E.g. {\"Technical Approach\": 40, \"Price\": 30, \"Past Performance\": 30}"
        ),
        examples=[{"Technical Approach": 40, "Price": 30, "Past Performance": 30}],
    )
    additional_context: Optional[str] = Field(
        None,
        description=(
            "Optional background to improve analysis quality — industry sector, "
            "competitive landscape, client priorities, budget constraints, etc."
        ),
    )


# ── Inner result models (returned by Claude) ─────────────────────────────────

class SectionScore(BaseModel):
    """Score and narrative for one evaluated section."""

    section: str = Field(..., description="Name of the evaluated section or criterion")
    score: float = Field(..., ge=0, le=100, description="Score from 0 (fail) to 100 (outstanding)")
    rationale: str = Field(..., description="Concise explanation with evidence from the documents")
    strengths: List[str] = Field(..., description="Specific strengths found in this section")
    weaknesses: List[str] = Field(..., description="Specific gaps or weaknesses found in this section")


class ActionItem(BaseModel):
    """A prioritised action the bidder should take."""

    priority: str = Field(
        ...,
        description="Urgency level: 'critical', 'high', 'medium', or 'low'",
    )
    area: str = Field(..., description="Section or topic this action targets")
    action: str = Field(..., description="Clear, specific action to take")
    expected_impact: str = Field(..., description="How this action improves the bid's chances")


class RFPAnalysisResult(BaseModel):
    """Full structured analysis of an RFP response."""

    overall_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Weighted overall score from 0 to 100",
    )
    win_probability: str = Field(
        ...,
        description="Estimated probability of winning: 'Very High', 'High', 'Medium', 'Low', or 'Very Low'",
    )
    executive_summary: str = Field(
        ...,
        description="2-4 sentence summary of the bid's overall strength and position",
    )
    competitive_position: str = Field(
        ...,
        description="Assessment of where this bid sits relative to likely competitors",
    )
    high_scoring_areas: List[str] = Field(
        ...,
        description="Sections or themes where the bid excels and holds competitive advantage",
    )
    areas_needing_attention: List[str] = Field(
        ...,
        description="Sections or themes with significant gaps that must be addressed",
    )
    section_scores: List[SectionScore] = Field(
        ...,
        description="Detailed score and narrative for each evaluated section",
    )
    action_items: List[ActionItem] = Field(
        ...,
        description="Prioritised list of specific actions to strengthen the bid",
    )
    strategic_recommendations: List[str] = Field(
        ...,
        description="High-level strategic moves to maximise win probability",
    )
    risk_factors: List[str] = Field(
        ...,
        description="Key risks that could jeopardise the bid if left unaddressed",
    )
    compliance_gaps: List[str] = Field(
        ...,
        description="Any RFP requirements that are missing or insufficiently addressed",
    )


# ── Response envelope ─────────────────────────────────────────────────────────

class AnalyzeRFPResponse(BaseModel):
    """API response wrapper for the RFP analysis endpoint."""

    success: bool = Field(..., description="True when analysis completed without error")
    analysis: Optional[RFPAnalysisResult] = Field(
        None, description="Full analysis results (present when success=true)"
    )
    error_message: Optional[str] = Field(
        None, description="Human-readable error detail (present when success=false)"
    )


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    model: str = Field(..., examples=["claude-opus-4-6"])
