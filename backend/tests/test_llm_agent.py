from app.models import ResupplyOption
from app.services.llm_agent import build_agent_payload


def test_llm_payload_contains_only_backend_operational_data():
    clinic = {
        "id": "clinic-b",
        "name": "Lingwala Screening Center",
        "test_kits_available": 35,
        "people_waiting": 96,
        "nurses_available": 2,
        "threshold_min_kits": 50,
        "testing_capacity_per_hour": 24,
        "queue_delay_hours": 4.0,
        "operations_remaining_hours": 1.46,
        "risk_level": "high",
        "latitude": -4.3276,
        "longitude": 15.3136,
    }
    option = ResupplyOption(
        source_id="warehouse-w1",
        source_name="Central Medical Warehouse",
        source_type="warehouse",
        available_stock=1000,
        delivery_time_minutes=25,
        road_status="open",
        recommended_transfer_quantity=61,
        supplier_remaining_stock_after_transfer=939,
        supplier_operations_remaining_after_transfer=None,
        is_safe_for_supplier=True,
        can_fully_supply=True,
        rank=1,
        reason="Can restore the clinic to four hours of operations.",
    )

    payload = build_agent_payload(clinic, [option])

    assert "ranked_options" in payload
    assert payload["clinic"]["id"] == "clinic-b"
    assert payload["ranked_options"][0]["source_id"] == "warehouse-w1"
    assert "Neo4j" in payload["data_contract"]
    assert "latitude" not in payload["clinic"]
