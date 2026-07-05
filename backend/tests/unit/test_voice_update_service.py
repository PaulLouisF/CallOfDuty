from typing import Mapping

from app.services.voice_update_service import analyze_voice_update, parse_voice_update


def values(
    transcript: str,
    current_values: Mapping[str, int] | None = None,
) -> dict[str, int]:
    events = parse_voice_update(
        "clinic-b",
        transcript,
        current_values=current_values,
    )
    result = {}
    for event in events:
        if event.event_type == "QUEUE_COUNT_UPDATED":
            result["people_waiting"] = event.people_waiting
        if event.event_type == "TEST_KITS_UPDATED":
            result["test_kits_available"] = event.test_kits_available
        if event.event_type == "NURSES_AVAILABLE_UPDATED":
            result["nurses_available"] = event.nurses_available
    return result


def test_parse_voice_update_extracts_people_waiting():
    assert values("There are eighty two people waiting at the center.") == {
        "people_waiting": 82,
    }


def test_parse_voice_update_extracts_multiple_supported_fields():
    assert values("We have 20 test kits remaining and two nurses available.") == {
        "test_kits_available": 20,
        "nurses_available": 2,
    }


def test_parse_voice_update_adds_nurse_to_current_site_value():
    assert values(
        "I will add 1 nurse.",
        current_values={"nurses_available": 3},
    ) == {"nurses_available": 4}


def test_parse_voice_update_adds_nurse_from_want_phrase():
    assert values(
        "I want to add 1 nurse.",
        current_values={"nurses_available": 2},
    ) == {"nurses_available": 3}


def test_parse_voice_update_adds_nurse_from_spoken_words():
    assert values(
        "I want to add one new nurse.",
        current_values={"nurses_available": 2},
    ) == {"nurses_available": 3}


def test_parse_voice_update_adds_single_nurse_from_article():
    assert values(
        "Please add a nurse.",
        current_values={"nurses_available": 2},
    ) == {"nurses_available": 3}


def test_parse_voice_update_increases_nurses_from_spoken_words():
    assert values(
        "Increase the number of nurses by one.",
        current_values={"nurses_available": 2},
    ) == {"nurses_available": 3}


def test_parse_voice_update_sets_nurses_absolute_value():
    assert values("Set nurses to four.") == {"nurses_available": 4}


def test_analyze_voice_update_returns_agent_decision():
    analysis = analyze_voice_update(
        "clinic-b",
        "I want to add one nurse.",
        current_values={"nurses_available": 2},
        language="en",
    )

    assert analysis.language == "en"
    assert analysis.action == "Apply 1 clinic graph update(s): nurses available."
    assert [event.event_type for event in analysis.events] == [
        "NURSES_AVAILABLE_UPDATED",
    ]
    assert "Gradium speech-to-text was requested in English." in analysis.reasoning


def test_parse_voice_update_ignores_unrelated_transcript():
    assert values("The generator is noisy and the gate is closed.") == {}
