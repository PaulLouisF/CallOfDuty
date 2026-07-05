from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.schemas import ObservationCandidate
from app.services.voice_update_service import VoiceUpdateAnalysis, analyze_voice_update


FIELD_TO_PARAMETER = {
    "people_waiting": "people_waiting",
    "test_kits_available": "test_kits_available",
    "nurses_available": "nurses_available",
}


@dataclass(frozen=True)
class Neo4jSchemaSummary:
    labels: list[str]
    relationship_types: list[str]
    clinic_properties: list[str]
    observation_properties: list[str]

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "labels": self.labels,
            "relationship_types": self.relationship_types,
            "clinic_properties": self.clinic_properties,
            "observation_properties": self.observation_properties,
        }


@dataclass(frozen=True)
class VoiceCypherAction:
    cypher: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class VoiceGraphDecision:
    analysis: VoiceUpdateAnalysis
    schema: Neo4jSchemaSummary
    cypher_action: VoiceCypherAction | None


def retrieve_neo4j_schema(client) -> Neo4jSchemaSummary:
    def work(tx):
        labels = [
            record["label"]
            for record in tx.run("CALL db.labels() YIELD label RETURN label ORDER BY label")
        ]
        relationship_types = [
            record["relationshipType"]
            for record in tx.run(
                """
                CALL db.relationshipTypes()
                YIELD relationshipType
                RETURN relationshipType ORDER BY relationshipType
                """
            )
        ]
        clinic_properties = _sample_properties(tx, "Clinic")
        observation_properties = _sample_properties(tx, "Observation")
        return Neo4jSchemaSummary(
            labels=labels,
            relationship_types=relationship_types,
            clinic_properties=clinic_properties,
            observation_properties=observation_properties,
        )

    return client.read(work)


def decide_voice_graph_action(
    *,
    clinic_id: str,
    transcript: str,
    current_values: Mapping[str, int],
    schema: Neo4jSchemaSummary,
    language: str,
    confidence: float,
) -> VoiceGraphDecision:
    analysis = analyze_voice_update(
        clinic_id,
        transcript,
        model_id="gradium-stt+neo4j-schema-agent",
        confidence=confidence,
        current_values=current_values,
        language=language,
    )
    supported_events = [
        event for event in analysis.events if _event_field(event) in schema.clinic_properties
    ]
    if len(supported_events) != len(analysis.events):
        analysis = VoiceUpdateAnalysis(
            language=analysis.language,
            action="No graph update",
            reasoning=[
                *analysis.reasoning,
                "The Neo4j schema does not expose the requested clinic property.",
            ],
            events=supported_events,
        )
    return VoiceGraphDecision(
        analysis=analysis,
        schema=schema,
        cypher_action=_build_cypher_action(clinic_id, supported_events),
    )


def _sample_properties(tx, label: str) -> list[str]:
    record = tx.run(
        f"MATCH (n:{label}) WITH n LIMIT 10 UNWIND keys(n) AS property "
        "RETURN collect(DISTINCT property) AS properties"
    ).single()
    if not record:
        return []
    return sorted(record["properties"])


def _event_field(event: ObservationCandidate) -> str | None:
    if event.event_type == "QUEUE_COUNT_UPDATED":
        return "people_waiting"
    if event.event_type == "TEST_KITS_UPDATED":
        return "test_kits_available"
    if event.event_type == "NURSES_AVAILABLE_UPDATED":
        return "nurses_available"
    return None


def _event_value(event: ObservationCandidate, field: str) -> int:
    return int(getattr(event, field))


def _build_cypher_action(
    clinic_id: str, events: list[ObservationCandidate]
) -> VoiceCypherAction | None:
    assignments = []
    parameters: dict[str, Any] = {"clinic_id": clinic_id}
    for event in events:
        field = _event_field(event)
        if not field:
            continue
        parameter = FIELD_TO_PARAMETER[field]
        assignments.append(f"c.{field} = ${parameter}")
        parameters[parameter] = _event_value(event, field)

    if not assignments:
        return None

    cypher = (
        "MATCH (c:Clinic {id: $clinic_id}) "
        f"SET {', '.join(assignments)} "
        "RETURN c"
    )
    return VoiceCypherAction(cypher=cypher, parameters=parameters)
