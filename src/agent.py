"""
RFP Analysis Agent — powered by Claude Opus 4.6.

Uses adaptive thinking + structured output to produce a rich, scored analysis
of an RFP response against the original requirements document.
"""

from __future__ import annotations

import copy
import json
import logging

import anthropic

from src.models import AnalyzeRFPRequest, RFPAnalysisResult

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-6"

SYSTEM_PROMPT = """\
You are a senior RFP (Request for Proposal) evaluation specialist with 20+ years of \
experience across government procurement, defence, healthcare, IT services, and \
commercial sectors. You have reviewed thousands of bids and know exactly what \
evaluators look for.

Your evaluation methodology:

SCORING SCALE (0–100)
• 90–100  Outstanding  — Exceeds all requirements; significant added value
• 75–89   Good         — Meets all requirements; only minor weaknesses
• 60–74   Acceptable   — Meets most requirements; some notable gaps
• 40–59   Marginal     — Partially meets requirements; significant gaps
• 0–39    Unacceptable — Fails to meet key requirements

KEY EVALUATION DIMENSIONS (adapt weights to any custom criteria provided)
1. Technical Approach / Solution — clarity, innovation, feasibility, alignment
2. Past Performance / Experience — relevant examples, client references, team CVs
3. Management Plan — project management methodology, risk mitigation, governance
4. Pricing / Commercial — competitiveness, cost realism, value for money, transparency
5. Timeline / Schedule — realism, milestones, critical path, dependencies
6. Compliance — completeness, format adherence, mandatory requirements met

ANALYSIS PRINCIPLES
• Ground every score in specific evidence quoted or paraphrased from the documents
• Be objective and constructive — identify what is good as well as what is missing
• Prioritise action items by impact on win probability, not difficulty
• Distinguish compliance gaps (disqualifiers) from improvement opportunities
• Give a candid win-probability assessment based on the response quality
"""


def _schema_for_structured_output(model_class) -> dict:
    """
    Build a JSON Schema from a Pydantic model that satisfies Claude's
    structured-output requirements:
    - Every object node gets `additionalProperties: false`
    - Unsupported numeric/string constraints are stripped
    """
    schema = copy.deepcopy(model_class.model_json_schema())

    def _patch(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                node.setdefault("additionalProperties", False)
            # Strip constraints the API doesn't support
            for key in ("minimum", "maximum", "minLength", "maxLength", "multipleOf"):
                node.pop(key, None)
            for child in node.values():
                _patch(child)
        elif isinstance(node, list):
            for item in node:
                _patch(item)

    _patch(schema)
    return schema


def _build_prompt(request: AnalyzeRFPRequest) -> str:
    parts: list[str] = [
        "## ORIGINAL RFP / TENDER DOCUMENT\n",
        request.rfp_document,
        "\n\n## SUBMITTED BID / RESPONSE DOCUMENT\n",
        request.response_document,
    ]

    if request.evaluation_criteria:
        parts += [
            "\n\n## CUSTOM EVALUATION CRITERIA (weights must be respected)\n",
            json.dumps(request.evaluation_criteria, indent=2),
        ]

    if request.additional_context:
        parts += ["\n\n## ADDITIONAL CONTEXT\n", request.additional_context]

    parts.append(
        "\n\nPlease perform a thorough evaluation and return your analysis in the "
        "required JSON structure. Every field must be populated with substantive content."
    )

    return "".join(parts)


async def analyze_rfp(request: AnalyzeRFPRequest) -> RFPAnalysisResult:
    """
    Run the RFP analysis agent and return a structured result.

    Uses Claude Opus 4.6 with adaptive thinking and structured output.
    Streaming is used internally so long analyses don't time out.
    """
    client = anthropic.AsyncAnthropic()
    schema = _schema_for_structured_output(RFPAnalysisResult)
    prompt = _build_prompt(request)

    logger.info("Starting RFP analysis (rfp_chars=%d, response_chars=%d)",
                len(request.rfp_document), len(request.response_document))

    async with client.messages.stream(
        model=MODEL,
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": schema,
            }
        },
    ) as stream:
        final_message = await stream.get_final_message()

    # Extract the structured JSON text block
    text_block = next(
        (b for b in final_message.content if b.type == "text"), None
    )
    if not text_block:
        raise ValueError("Claude returned no text content — cannot parse analysis.")

    logger.info(
        "Analysis complete (stop_reason=%s, output_tokens=%s)",
        final_message.stop_reason,
        final_message.usage.output_tokens,
    )

    return RFPAnalysisResult.model_validate_json(text_block.text)
