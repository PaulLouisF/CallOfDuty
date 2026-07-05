from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.config import Settings, get_settings
from app.schemas import AgentRecommendation, Alert, Clinic, ClinicUpdate, ResupplyOption
from app.schemas import VoiceUpdateResponse
from app.infrastructure.neo4j.client import Neo4jClient, get_neo4j_client
from app.infrastructure.gradium.client import GradiumClient, GradiumError
from app.api.routers.observations import get_observation_service
from app.services.observation_service import ObservationService
from app.services.recommendation_service import (
    get_agent_recommendation,
    get_resupply_options,
)
from app.services.risk_service import compute_clinic_metrics, utc_now_iso
from app.services.voice_graph_agent import (
    decide_voice_graph_action,
    retrieve_neo4j_schema,
)

router = APIRouter(tags=["clinics"])
logger = logging.getLogger(__name__)


def _clinic_or_404(clinic: dict[str, Any] | None) -> dict[str, Any]:
    if clinic is None:
        raise HTTPException(status_code=404, detail="Clinic not found")
    return clinic


def get_gradium_client(settings: Settings = Depends(get_settings)) -> GradiumClient:
    if not settings.gradium_api_key:
        raise HTTPException(status_code=503, detail="Gradium STT is not configured.")
    return GradiumClient(settings)


@router.get("/clinics", response_model=list[Clinic])
def list_clinics(client: Neo4jClient = Depends(get_neo4j_client)):
    def work(tx):
        result = tx.run("MATCH (c:Clinic) RETURN c ORDER BY c.name")
        return [dict(record["c"]) for record in result]

    return client.read(work)


@router.get("/clinics/{clinic_id}", response_model=Clinic)
def get_clinic(
    clinic_id: str, client: Neo4jClient = Depends(get_neo4j_client)
):
    def work(tx):
        record = tx.run(
            "MATCH (c:Clinic {id: $clinic_id}) RETURN c", clinic_id=clinic_id
        ).single()
        return dict(record["c"]) if record else None

    return _clinic_or_404(client.read(work))


@router.patch("/clinics/{clinic_id}", response_model=Clinic)
def update_clinic(
    clinic_id: str,
    update: ClinicUpdate,
    client: Neo4jClient = Depends(get_neo4j_client),
):
    updates = update.model_dump(exclude_unset=True)

    def work(tx):
        record = tx.run(
            "MATCH (c:Clinic {id: $clinic_id}) RETURN c", clinic_id=clinic_id
        ).single()
        if record is None:
            return None
        current = dict(record["c"])
        raw = {**current, **updates}
        props = {
            **updates,
            **compute_clinic_metrics(raw),
            "last_updated_at": utc_now_iso(),
        }
        updated = tx.run(
            """
            MATCH (c:Clinic {id: $clinic_id})
            SET c += $props
            RETURN c
            """,
            clinic_id=clinic_id,
            props=props,
        ).single()
        return dict(updated["c"])

    return _clinic_or_404(client.write(work))


@router.post("/clinics/{clinic_id}/voice-update", response_model=VoiceUpdateResponse)
async def voice_update_clinic(
    clinic_id: str,
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    client: Neo4jClient = Depends(get_neo4j_client),
    gradium: GradiumClient = Depends(get_gradium_client),
    observations: ObservationService = Depends(get_observation_service),
):
    if not observations.store.clinic_exists(clinic_id):
        raise HTTPException(status_code=404, detail="Clinic not found")

    data = await file.read(settings.max_audio_upload_bytes + 1)
    if len(data) > settings.max_audio_upload_bytes:
        raise HTTPException(status_code=413, detail="Uploaded audio exceeds the size limit.")
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded audio is empty.")
    logger.info(
        "Voice update received for clinic %s: %s bytes, content_type=%s",
        clinic_id,
        len(data),
        file.content_type,
    )

    try:
        transcript = await gradium.transcribe(
            data,
            file.content_type or "audio/webm",
            language=settings.gradium_stt_language,
        )
    except GradiumError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.info("Voice update transcript for clinic %s: %s", clinic_id, transcript)

    current_clinic = get_clinic(clinic_id, client)
    schema = retrieve_neo4j_schema(client)
    decision = decide_voice_graph_action(
        clinic_id=clinic_id,
        transcript=transcript,
        current_values={
            "people_waiting": int(current_clinic["people_waiting"]),
            "test_kits_available": int(current_clinic["test_kits_available"]),
            "nurses_available": int(current_clinic["nurses_available"]),
        },
        schema=schema,
        language=settings.gradium_stt_language,
        confidence=settings.observation_auto_apply_confidence,
    )
    analysis = decision.analysis
    logger.info(
        "Voice update analyzer for clinic %s used schema %s, decided %s, cypher=%s, events=%s",
        clinic_id,
        schema.as_dict(),
        analysis.action,
        decision.cypher_action.cypher if decision.cypher_action else None,
        [event.event_type for event in analysis.events],
    )
    if not analysis.events:
        raise HTTPException(
            status_code=400,
            detail=(
                "No supported clinic update was found in the transcript. "
                "Try reporting people waiting, test kits, or nurses available."
            ),
        )

    applied = [observations.process(event) for event in analysis.events]
    clinic = get_clinic(clinic_id, client)
    recommendation = get_agent_recommendation(client, clinic_id)
    return VoiceUpdateResponse(
        transcript=transcript,
        agent_decision={
            "language": analysis.language,
            "action": analysis.action,
            "reasoning": analysis.reasoning,
            "neo4j_schema": decision.schema.as_dict(),
            "cypher": decision.cypher_action.cypher if decision.cypher_action else None,
            "parameters": (
                decision.cypher_action.parameters if decision.cypher_action else None
            ),
        },
        observations=applied,
        clinic=Clinic.model_validate(clinic),
        recommendation=recommendation,
    )


@router.get(
    "/clinics/{clinic_id}/resupply-options", response_model=list[ResupplyOption]
)
def resupply_options(
    clinic_id: str, client: Neo4jClient = Depends(get_neo4j_client)
):
    try:
        return get_resupply_options(client, clinic_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/clinics/{clinic_id}/agent-recommendation",
    response_model=AgentRecommendation,
)
def agent_recommendation(
    clinic_id: str, client: Neo4jClient = Depends(get_neo4j_client)
):
    try:
        return get_agent_recommendation(client, clinic_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/alerts", response_model=list[Alert])
def list_alerts(client: Neo4jClient = Depends(get_neo4j_client)):
    def work(tx):
        result = tx.run(
            """
            MATCH (c:Clinic)
            WHERE c.risk_level IN ['critical', 'high']
               OR c.operations_remaining_hours < 2
               OR c.test_kits_available < c.threshold_min_kits
            RETURN c
            ORDER BY
              CASE c.risk_level
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                ELSE 3
              END,
              c.operations_remaining_hours ASC
            """
        )
        alerts = []
        for record in result:
            clinic = dict(record["c"])
            reasons = []
            if clinic["risk_level"] in {"critical", "high"}:
                reasons.append(f"{clinic['risk_level']} risk")
            if (
                clinic["operations_remaining_hours"] is not None
                and clinic["operations_remaining_hours"] < 2
            ):
                reasons.append("less than 2 hours of operations remaining")
            if clinic["test_kits_available"] < clinic["threshold_min_kits"]:
                reasons.append("stock below minimum threshold")
            alerts.append(
                {
                    "clinic_id": clinic["id"],
                    "clinic": clinic["name"],
                    "risk_level": clinic["risk_level"],
                    "operations_remaining_hours": clinic[
                        "operations_remaining_hours"
                    ],
                    "queue_delay_hours": clinic["queue_delay_hours"],
                    "reason": ", ".join(reasons),
                }
            )
        return alerts

    return client.read(work)
