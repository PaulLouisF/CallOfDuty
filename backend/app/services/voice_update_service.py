from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from app.schemas import ObservationCandidate, validate_observation_candidate


NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
}

NUMBER_PATTERN = r"\d+|(?:a|an|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?"

FIELD_LABELS = {
    "people_waiting": "people waiting",
    "test_kits_available": "test kits available",
    "nurses_available": "nurses available",
}

PATTERNS = [
    (
        "QUEUE_COUNT_UPDATED",
        "people_waiting",
        [
            rf"(?:add|adds|adding|added|send|sending|sent)\s+(?P<value>{NUMBER_PATTERN})\s+(?:more\s+|additional\s+|extra\s+|new\s+)?(?:people|patients|persons)",
            rf"(?:increase|increased|raise|raised)\s+(?:the\s+)?(?:waiting\s+)?(?:people|patients|persons|queue|line)\s+(?:by\s+)?(?P<value>{NUMBER_PATTERN})",
            rf"(?P<value>{NUMBER_PATTERN})\s+(?:more\s+|additional\s+|extra\s+)(?:people|patients|persons)",
        ],
        [
            rf"(?:set|make|update|change)\s+(?:the\s+)?(?:waiting\s+)?(?:people|patients|persons|queue|line)\s+(?:to\s+)?(?P<value>{NUMBER_PATTERN})",
            rf"(?P<value>{NUMBER_PATTERN})\s+(?:people|patients|persons)\s+(?:are\s+)?(?:waiting|in\s+queue|queued)",
            rf"(?:waiting|queue|line)\s+(?:is|at|has|now)?\s*(?P<value>{NUMBER_PATTERN})",
        ],
    ),
    (
        "TEST_KITS_UPDATED",
        "test_kits_available",
        [
            rf"(?:add|adds|adding|added|deliver|delivering|delivered|bring|bringing|brought)\s+(?P<value>{NUMBER_PATTERN})\s+(?:more\s+|additional\s+|extra\s+|new\s+)?(?:test\s+)?kits?",
            rf"(?:increase|increased|raise|raised)\s+(?:the\s+)?(?:test\s+)?kits?\s+(?:by\s+)?(?P<value>{NUMBER_PATTERN})",
            rf"(?P<value>{NUMBER_PATTERN})\s+(?:more\s+|additional\s+|extra\s+)(?:test\s+)?kits?",
        ],
        [
            rf"(?:set|make|update|change)\s+(?:the\s+)?(?:test\s+)?kits?\s+(?:to\s+)?(?P<value>{NUMBER_PATTERN})",
            rf"(?P<value>{NUMBER_PATTERN})\s+(?:test\s+)?kits?",
            rf"(?:kits?|test\s+kits?)\s+(?:is|are|at|left|remaining|available)?\s*(?P<value>{NUMBER_PATTERN})",
        ],
    ),
    (
        "NURSES_AVAILABLE_UPDATED",
        "nurses_available",
        [
            rf"(?:add|adds|adding|added|assign|assigning|assigned|send|sending|sent)\s+(?P<value>{NUMBER_PATTERN})\s+(?:more\s+|additional\s+|extra\s+|new\s+)?nurses?",
            rf"(?:increase|increased|raise|raised)\s+(?:the\s+)?(?:number\s+of\s+)?nurses?\s+(?:by\s+)?(?P<value>{NUMBER_PATTERN})",
            rf"(?P<value>{NUMBER_PATTERN})\s+(?:more\s+|additional\s+|extra\s+)nurses?",
        ],
        [
            rf"(?:set|make|update|change)\s+(?:the\s+)?(?:number\s+of\s+)?nurses?\s+(?:to\s+)?(?P<value>{NUMBER_PATTERN})",
            rf"(?P<value>{NUMBER_PATTERN})\s+nurses?",
            rf"nurses?\s+(?:is|are|at|available)?\s*(?P<value>{NUMBER_PATTERN})",
        ],
    ),
]


@dataclass(frozen=True)
class VoiceUpdateAnalysis:
    language: str
    action: str
    reasoning: list[str]
    events: list[ObservationCandidate]


def analyze_voice_update(
    clinic_id: str,
    transcript: str,
    *,
    model_id: str = "gradium-stt+voice-command-agent",
    confidence: float = 0.95,
    current_values: Mapping[str, int] | None = None,
    language: str = "en",
) -> VoiceUpdateAnalysis:
    events = parse_voice_update(
        clinic_id,
        transcript,
        model_id=model_id,
        confidence=confidence,
        current_values=current_values,
    )
    if not events:
        return VoiceUpdateAnalysis(
            language=language,
            action="No graph update",
            reasoning=[
                "Gradium produced an English transcript, but the agent found no supported numeric clinic update.",
                "Supported updates are people waiting, test kits available, and nurses available.",
            ],
            events=[],
        )

    event_names = ", ".join(FIELD_LABELS[field] for event in events for field in _event_fields(event))
    return VoiceUpdateAnalysis(
        language=language,
        action=f"Apply {len(events)} clinic graph update(s): {event_names}.",
        reasoning=[
            "Gradium speech-to-text was requested in English.",
            "The voice-command agent interpreted the transcript for the selected clinic only.",
            "The generated observation event(s) will be applied through the existing Neo4j observation workflow.",
        ],
        events=events,
    )


def parse_voice_update(
    clinic_id: str,
    transcript: str,
    *,
    model_id: str = "gradium-stt",
    confidence: float = 0.95,
    current_values: Mapping[str, int] | None = None,
) -> list[ObservationCandidate]:
    normalized = transcript.strip().lower()
    observed_at = datetime.now(timezone.utc)
    events = []

    for event_type, field, additive_patterns, absolute_patterns in PATTERNS:
        parsed = _match_value(additive_patterns, normalized)
        if parsed is not None and current_values is not None:
            delta = parsed
            current = int(current_values.get(field, 0))
            value = max(0, current + delta)
            summary = (
                f"Voice call reported adding {delta} {FIELD_LABELS[field]}, "
                f"moving {field} from {current} to {value}."
            )
        else:
            value = _match_value(absolute_patterns, normalized)
            if value is None:
                continue
            summary = f"Voice call reported {field} as {value}."

        events.append(
            validate_observation_candidate(
                {
                    "event_type": event_type,
                    "clinic_id": clinic_id,
                    "source_type": "audio",
                    "confidence": confidence,
                    "observed_at": observed_at.isoformat(),
                    "raw_text": transcript,
                    "transcript": transcript,
                    "evidence_summary": summary,
                    "model_id": model_id,
                    field: value,
                }
            )
        )

    return events


def _event_fields(event: ObservationCandidate) -> list[str]:
    if event.event_type == "QUEUE_COUNT_UPDATED":
        return ["people_waiting"]
    if event.event_type == "TEST_KITS_UPDATED":
        return ["test_kits_available"]
    if event.event_type == "NURSES_AVAILABLE_UPDATED":
        return ["nurses_available"]
    return []


def _match_value(patterns: list[str], normalized: str) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        value = _number(match.group("value"))
        if value is None:
            continue
        return value
    return None


def _number(value: str) -> int | None:
    if value.isdigit():
        return int(value)

    parts = re.split(r"[-\s]+", value)
    total = 0
    for part in parts:
        current = NUMBER_WORDS.get(part)
        if current is None:
            return None
        if current == 100 and total:
            total *= current
        else:
            total += current
    return total
