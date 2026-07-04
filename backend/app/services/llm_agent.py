from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.models import AgentRecommendation, ResupplyOption


class LLMExplanation(BaseModel):
    reasoning: list[str]
    recommendation: str


SYSTEM_PROMPT = """You are a logistics reasoning assistant for Ebola test kit resupply.
Use only the JSON data provided by the backend. Do not use outside knowledge,
do not invent stock numbers, clinics, warehouses, routes, delivery times, risk
levels, or transfer quantities. The backend has already calculated risk and
ranked options. Your job is only to explain the backend data clearly for a
human operator. Return valid JSON with keys reasoning and recommendation."""


def build_agent_payload(
    clinic: dict[str, Any], options: list[ResupplyOption]
) -> dict[str, Any]:
    return {
        "data_contract": (
            "All facts in this payload come from Neo4j clinic/warehouse nodes, "
            "Neo4j CAN_SUPPLY relationships, and deterministic backend metrics "
            "computed from those Neo4j values."
        ),
        "clinic": {
            key: clinic.get(key)
            for key in [
                "id",
                "name",
                "test_kits_available",
                "people_waiting",
                "nurses_available",
                "threshold_min_kits",
                "testing_capacity_per_hour",
                "queue_delay_hours",
                "operations_remaining_hours",
                "risk_level",
            ]
        },
        "ranked_options": [option.model_dump() for option in options],
        "instruction": (
            "Explain the status and recommendation using only this payload. "
            "If there is no good option, say that. Do not add facts."
        ),
    }


def generate_llm_explanation(
    clinic: dict[str, Any],
    options: list[ResupplyOption],
    fallback: AgentRecommendation,
) -> AgentRecommendation:
    settings = get_settings()
    if not settings.llm_api_key:
        return fallback

    payload = build_agent_payload(clinic, options)
    client = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )

    try:
        completion = client.chat.completions.create(
            model=settings.llm_model,
            response_format={"type": "json_object"},
            temperature=0.1,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(payload, separators=(",", ":")),
                },
            ],
        )
        content = completion.choices[0].message.content or "{}"
        parsed = LLMExplanation.model_validate_json(content)
    except (ValidationError, json.JSONDecodeError, Exception):
        return fallback

    return AgentRecommendation(
        clinic_id=fallback.clinic_id,
        clinic=fallback.clinic,
        status=fallback.status,
        reasoning=parsed.reasoning,
        recommendation=parsed.recommendation,
        options=fallback.options,
        llm_used=True,
        llm_provider="mistral-openai-compatible",
        llm_model=settings.llm_model,
        data_sources=fallback.data_sources,
    )
