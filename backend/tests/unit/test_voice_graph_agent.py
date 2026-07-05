from app.services.voice_graph_agent import (
    Neo4jSchemaSummary,
    decide_voice_graph_action,
)


SCHEMA = Neo4jSchemaSummary(
    labels=["Clinic", "Observation"],
    relationship_types=["OBSERVED_AT"],
    clinic_properties=[
        "id",
        "name",
        "nurses_available",
        "people_waiting",
        "test_kits_available",
    ],
    observation_properties=["id", "event_type"],
)


def test_voice_graph_agent_uses_schema_and_emits_parameterized_cypher():
    decision = decide_voice_graph_action(
        clinic_id="clinic-b",
        transcript="I want to add one nurse.",
        current_values={
            "nurses_available": 2,
            "people_waiting": 80,
            "test_kits_available": 30,
        },
        schema=SCHEMA,
        language="en",
        confidence=0.95,
    )

    assert decision.schema.clinic_properties == SCHEMA.clinic_properties
    assert decision.cypher_action is not None
    assert decision.cypher_action.cypher == (
        "MATCH (c:Clinic {id: $clinic_id}) "
        "SET c.nurses_available = $nurses_available RETURN c"
    )
    assert decision.cypher_action.parameters == {
        "clinic_id": "clinic-b",
        "nurses_available": 3,
    }
    assert decision.analysis.events[0].event_type == "NURSES_AVAILABLE_UPDATED"


def test_voice_graph_agent_refuses_property_missing_from_schema():
    schema = Neo4jSchemaSummary(
        labels=["Clinic"],
        relationship_types=[],
        clinic_properties=["id", "name"],
        observation_properties=[],
    )

    decision = decide_voice_graph_action(
        clinic_id="clinic-b",
        transcript="I want to add one nurse.",
        current_values={
            "nurses_available": 2,
            "people_waiting": 80,
            "test_kits_available": 30,
        },
        schema=schema,
        language="en",
        confidence=0.95,
    )

    assert decision.analysis.events == []
    assert decision.cypher_action is None
    assert decision.analysis.action == "No graph update"
