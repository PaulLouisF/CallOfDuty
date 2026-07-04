from __future__ import annotations

from typing import Any

from app.models import AgentRecommendation, ResupplyOption
from app.neo4j_client import Neo4jClient
from app.services.llm_agent import generate_llm_explanation
from app.services.risk_engine import (
    calculate_operations_remaining_hours,
    calculate_risk_level,
    recommended_transfer_quantity,
)


SAFE_ROAD_STATUSES = {"open", "slow"}


def _load_clinic(tx, clinic_id: str) -> dict[str, Any] | None:
    record = tx.run(
        "MATCH (c:Clinic {id: $clinic_id}) RETURN c", clinic_id=clinic_id
    ).single()
    return dict(record["c"]) if record else None


def get_resupply_options(
    client: Neo4jClient, clinic_id: str
) -> list[ResupplyOption]:
    def work(tx):
        target = _load_clinic(tx, clinic_id)
        if target is None:
            return None

        needed = recommended_transfer_quantity(target)
        result = tx.run(
            """
            MATCH (source)-[route:CAN_SUPPLY]->(target:Clinic {id: $clinic_id})
            WHERE route.road_status IN $road_statuses
            RETURN labels(source) AS labels, source, route
            """,
            clinic_id=clinic_id,
            road_statuses=sorted(SAFE_ROAD_STATUSES),
        )
        options = []
        for record in result:
            source = dict(record["source"])
            route = dict(record["route"])
            labels = set(record["labels"])
            source_type = "warehouse" if "Warehouse" in labels else "clinic"
            available_stock = (
                source["test_kits_stock"]
                if source_type == "warehouse"
                else source["test_kits_available"]
            )
            route_limit = route.get("max_transfer_kits")
            route_cap = available_stock
            if route_limit is not None:
                route_cap = min(route_cap, route_limit)

            transfer = min(needed, route_cap) if needed > 0 else 0
            remaining_stock = available_stock - transfer
            supplier_ops_after = None
            is_safe_for_supplier = True
            if source_type == "clinic":
                supplier_ops_after = calculate_operations_remaining_hours(
                    remaining_stock, source["nurses_available"]
                )
                supplier_risk = calculate_risk_level(
                    test_kits_available=remaining_stock,
                    people_waiting=source["people_waiting"],
                    nurses_available=source["nurses_available"],
                    threshold_min_kits=source["threshold_min_kits"],
                    operations_remaining_hours=supplier_ops_after,
                    queue_delay_hours=source["queue_delay_hours"],
                )
                is_safe_for_supplier = supplier_risk not in {"high", "critical"}

            can_fully_supply = needed == 0 or transfer >= needed
            reason_parts = []
            if needed == 0:
                reason_parts.append("No immediate transfer is required.")
            elif can_fully_supply:
                reason_parts.append("Can restore the clinic to four hours of operations.")
            else:
                reason_parts.append("Can provide only a partial transfer.")
            if route["road_status"] == "slow":
                reason_parts.append("Route is slow but usable.")
            if source_type == "clinic" and not is_safe_for_supplier:
                reason_parts.append("Transfer would weaken the supplying clinic.")
            if source_type == "warehouse":
                reason_parts.append("Warehouse supply avoids reducing another clinic's stock.")

            options.append(
                {
                    "source_id": source["id"],
                    "source_name": source["name"],
                    "source_type": source_type,
                    "available_stock": available_stock,
                    "delivery_time_minutes": route["delivery_time_minutes"],
                    "road_status": route["road_status"],
                    "recommended_transfer_quantity": transfer,
                    "supplier_remaining_stock_after_transfer": remaining_stock,
                    "supplier_operations_remaining_after_transfer": supplier_ops_after,
                    "is_safe_for_supplier": is_safe_for_supplier,
                    "can_fully_supply": can_fully_supply,
                    "reason": " ".join(reason_parts),
                }
            )

        options.sort(
            key=lambda option: (
                not option["can_fully_supply"],
                not option["is_safe_for_supplier"],
                option["delivery_time_minutes"],
                0 if option["source_type"] == "warehouse" else 1,
                option["available_stock"] * -1,
            )
        )
        return [
            ResupplyOption(**{**option, "rank": index + 1})
            for index, option in enumerate(options)
        ]

    options = client.read(work)
    if options is None:
        raise ValueError("Clinic not found")
    return options


def get_agent_recommendation(
    client: Neo4jClient, clinic_id: str
) -> AgentRecommendation:
    def load_target(tx):
        return _load_clinic(tx, clinic_id)

    clinic = client.read(load_target)
    if clinic is None:
        raise ValueError("Clinic not found")

    options = get_resupply_options(client, clinic_id)
    best = options[0] if options else None
    reasoning = [
        f"{clinic['name']} is {clinic['risk_level']} risk.",
        (
            f"It has {clinic['test_kits_available']} test kits, "
            f"{clinic['people_waiting']} people waiting, and "
            f"{clinic['nurses_available']} nurses available."
        ),
        (
            f"Current capacity is {clinic['testing_capacity_per_hour']} tests/hour, "
            f"with {clinic['operations_remaining_hours']} hours of operations remaining "
            f"and a {clinic['queue_delay_hours']} hour queue delay."
        ),
    ]
    if clinic["test_kits_available"] < clinic["threshold_min_kits"]:
        reasoning.append("Current stock is below the clinic's minimum threshold.")
    if best:
        reasoning.append(
            f"{best.source_name} is ranked first: {best.reason}"
        )
        recommendation = (
            f"Resupply {clinic['name']} from {best.source_name} with "
            f"{best.recommended_transfer_quantity} test kits. Estimated delivery time: "
            f"{best.delivery_time_minutes} minutes."
        )
    else:
        recommendation = (
            f"No open or slow supply route is available for {clinic['name']}."
        )

    fallback = AgentRecommendation(
        clinic_id=clinic["id"],
        clinic=clinic["name"],
        status=clinic["risk_level"],
        reasoning=reasoning,
        recommendation=recommendation,
        options=options,
        llm_used=False,
        llm_provider="deterministic",
        data_sources=[
            "neo4j:Clinic",
            "neo4j:Warehouse",
            "neo4j:CAN_SUPPLY",
            "backend:risk_engine",
            "backend:recommendation_engine",
        ],
    )
    return generate_llm_explanation(clinic, options, fallback)
