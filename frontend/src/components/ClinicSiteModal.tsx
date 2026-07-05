import { useEffect, useRef, useState } from "react";
import {
  Activity,
  Clock,
  MapPin,
  Mic,
  Package,
  Square,
  UserRoundPlus,
  Users,
} from "lucide-react";
import queueImage from "../assets/clinic-queue.png";
import type {
  AgentRecommendation,
  Clinic,
  ClinicUpdate,
  ResupplyOption,
  Transfer,
  VoiceUpdateResponse,
} from "../types";
import { AgentReasoningPanel } from "./AgentReasoningPanel";
import { ClinicUpdateForm } from "./ClinicUpdateForm";

type ClinicSiteModalProps = {
  clinic: Clinic | null;
  recommendation: AgentRecommendation | null;
  transfers: Transfer[];
  loading: boolean;
  loadingAgent: boolean;
  validatingSourceId: string | null;
  actionMessage: string | null;
  onClinicUpdate: (update: ClinicUpdate) => Promise<void>;
  onVoiceUpdate: (file: File) => Promise<VoiceUpdateResponse>;
  onValidateTransfer: (option: ResupplyOption) => Promise<void>;
  onRejectTransfer: () => void;
};

function formatHours(value: number | null) {
  return value === null ? "n/a" : `${value.toFixed(2)} h`;
}

export function ClinicSiteModal({
  clinic,
  recommendation,
  transfers,
  loading,
  loadingAgent,
  validatingSourceId,
  actionMessage,
  onClinicUpdate,
  onVoiceUpdate,
  onValidateTransfer,
  onRejectTransfer,
}: ClinicSiteModalProps) {
  const [recording, setRecording] = useState(false);
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState<string | null>(null);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [voiceResult, setVoiceResult] = useState<string | null>(null);
  const [voiceCypher, setVoiceCypher] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const unmountedRef = useRef(false);

  useEffect(() => {
    unmountedRef.current = false;
    return () => {
      unmountedRef.current = true;
      if (recorderRef.current?.state === "recording") {
        recorderRef.current.stop();
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  if (loading) {
    return <div className="panel-muted">Loading selected clinic...</div>;
  }

  if (!clinic) {
    return <div className="panel-muted">Select a clinic marker on the map.</div>;
  }

  const clinicTransfers = transfers.filter(
    (transfer) => transfer.target_clinic_id === clinic.id,
  );
  const ongoingTransfer = clinicTransfers[0] ?? null;

  async function startVoiceUpdate() {
    if (!clinic) {
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setVoiceError("Microphone recording is not available in this browser.");
      return;
    }

    setVoiceError(null);
    setVoiceTranscript(null);
    setVoiceResult(null);
    setVoiceCypher(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferredTypes = [
        "audio/webm;codecs=opus",
        "audio/ogg;codecs=opus",
        "audio/webm",
      ];
      const mimeType = preferredTypes.find((type) =>
        MediaRecorder.isTypeSupported(type),
      );
      const recorder = new MediaRecorder(
        stream,
        mimeType ? { mimeType } : undefined,
      );
      chunksRef.current = [];
      streamRef.current = stream;
      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        if (unmountedRef.current) {
          return;
        }
        setRecording(false);

        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        chunksRef.current = [];
        recorderRef.current = null;
        if (!blob.size) {
          setVoiceError("No audio was recorded.");
          return;
        }

        setVoiceLoading(true);
        try {
          const file = new File([blob], `site-call-${clinic.id}.webm`, {
            type: blob.type || "audio/webm",
          });
          const response = await onVoiceUpdate(file);
          setVoiceTranscript(response.transcript);
          setVoiceCypher(response.agent_decision.cypher);
          setVoiceResult(
            `${response.agent_decision.action} Applied ${
              response.observations.length
            } update${
              response.observations.length === 1 ? "" : "s"
            } to ${response.clinic.name}.`,
          );
        } catch (err) {
          setVoiceError(
            err instanceof Error ? err.message : "Unable to apply voice update.",
          );
        } finally {
          setVoiceLoading(false);
        }
      };

      recorder.onerror = () => {
        setRecording(false);
        setVoiceError("Microphone recording failed.");
        stream.getTracks().forEach((track) => track.stop());
      };

      recorder.start(250);
      setRecording(true);
    } catch (err) {
      setVoiceError(
        err instanceof Error ? err.message : "Unable to access the microphone.",
      );
    }
  }

  function stopVoiceUpdate() {
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.requestData();
      recorderRef.current.stop();
      return;
    }
    setRecording(false);
  }

  return (
    <div className="clinic-site-layout">
      <section className="clinic-site-left">
        <figure className="clinic-queue-figure">
          <img src={queueImage} alt="People waiting in line outside a clinic" />
        </figure>

        <div className="clinic-indicator-header">
          <div>
            <p className="eyebrow">Indicators</p>
            <h3>{clinic.name}</h3>
          </div>
          <span className={`risk-pill risk-${clinic.risk_level}`}>
            {clinic.risk_level}
          </span>
        </div>

        <dl className="metric-grid">
          <div>
            <dt>
              <Users size={15} /> Waiting
            </dt>
            <dd>{clinic.people_waiting}</dd>
          </div>
          <div>
            <dt>
              <Package size={15} /> Kits
            </dt>
            <dd>{clinic.test_kits_available}</dd>
          </div>
          <div>
            <dt>
              <Activity size={15} /> Capacity
            </dt>
            <dd>{clinic.testing_capacity_per_hour}/h</dd>
          </div>
          <div>
            <dt>
              <UserRoundPlus size={15} /> Nurses
            </dt>
            <dd>{clinic.nurses_available}</dd>
          </div>
          <div>
            <dt>
              <Clock size={15} /> Queue
            </dt>
            <dd>{formatHours(clinic.queue_delay_hours)}</dd>
          </div>
          <div>
            <dt>
              <Clock size={15} /> Operations
            </dt>
            <dd>{formatHours(clinic.operations_remaining_hours)}</dd>
          </div>
          <div>
            <dt>
              <MapPin size={15} /> Coordinates
            </dt>
            <dd>
              {clinic.latitude.toFixed(4)}, {clinic.longitude.toFixed(4)}
            </dd>
          </div>
        </dl>

        <section className="voice-update-panel">
          <div className="voice-update-header">
            <div>
              <p className="eyebrow">Voice update</p>
              <h3>Gradium STT</h3>
            </div>
            <span className={recording ? "voice-status recording" : "voice-status"}>
              {recording ? "Recording" : "Ready"}
            </span>
          </div>
          <button
            aria-pressed={recording}
            className={recording ? "voice-update-button recording" : "voice-update-button"}
            disabled={voiceLoading}
            onClick={recording ? stopVoiceUpdate : startVoiceUpdate}
            type="button"
          >
            {recording ? <Square size={16} /> : <Mic size={16} />}
            {voiceLoading
              ? "Transcribing..."
              : recording
                ? "Stop and analyze"
                : "Start voice update"}
          </button>
          {recording && (
            <p className="voice-hint">
              Recording this clinic. Click stop when your update is complete.
            </p>
          )}
          {voiceTranscript && (
            <p className="voice-transcript">"{voiceTranscript}"</p>
          )}
          {voiceResult && <p className="voice-result">{voiceResult}</p>}
          {voiceCypher && <pre className="voice-cypher">{voiceCypher}</pre>}
          {voiceError && <p className="voice-error">{voiceError}</p>}
        </section>

        <ClinicUpdateForm clinic={clinic} onSubmit={onClinicUpdate} />
      </section>

      <section className="clinic-site-right">
        <div className="site-situation-card">
          <p className="eyebrow">What is happening</p>
          <h3>
            {recommendation?.recommendation ??
              `${clinic.name} is currently ${clinic.risk_level} risk.`}
          </h3>
          <p>
            {clinic.people_waiting} people are waiting, with{" "}
            {formatHours(clinic.queue_delay_hours)} queue delay and{" "}
            {formatHours(clinic.operations_remaining_hours)} of operations
            remaining.
          </p>
          {ongoingTransfer && (
            <div className="ongoing-transfer-banner">
              <span className="transfer-status">{ongoingTransfer.status}</span>
              <p>
                {ongoingTransfer.quantity} kits are reserved from{" "}
                {ongoingTransfer.source_name}; ETA{" "}
                {ongoingTransfer.delivery_time_minutes} minutes on a{" "}
                {ongoingTransfer.road_status} route.
              </p>
            </div>
          )}
        </div>

        <AgentReasoningPanel
          recommendation={recommendation}
          transfers={clinicTransfers}
          loading={loadingAgent}
          validatingSourceId={validatingSourceId}
          actionMessage={actionMessage}
          onValidateTransfer={onValidateTransfer}
          onRejectTransfer={onRejectTransfer}
        />
      </section>
    </div>
  );
}
