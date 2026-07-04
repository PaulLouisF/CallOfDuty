import { AlertTriangle, Route } from "lucide-react";
import type { AgentRecommendation, ResupplyOption, Transfer } from "../types";

type AgentReasoningPanelProps = {
  recommendation: AgentRecommendation | null;
  transfers: Transfer[];
  loading: boolean;
  validatingSourceId: string | null;
  onValidateTransfer: (sourceId: string) => Promise<void>;
};

export function AgentReasoningPanel({
  recommendation,
  transfers,
  loading,
  validatingSourceId,
  onValidateTransfer,
}: AgentReasoningPanelProps) {
  if (loading) {
    return <div className="panel-muted">Loading recommendation...</div>;
  }

  if (!recommendation) {
    return <div className="panel-muted">Clinic recommendations appear here.</div>;
  }

  const alternatives = recommendation.options.slice(1, 4);
  const primaryOption = recommendation.options[0] ?? null;

  function TransferAction({ option }: { option: ResupplyOption }) {
    const disabled =
      option.source_type !== "warehouse" ||
      option.recommended_transfer_quantity <= 0 ||
      validatingSourceId !== null;

    return (
      <button
        className="primary-button transfer-button"
        disabled={disabled}
        onClick={() => onValidateTransfer(option.source_id)}
        type="button"
      >
        {validatingSourceId === option.source_id ? "Validating" : "Validate transfer"}
      </button>
    );
  }

  return (
    <section className="panel-section">
      <div className="flex items-start gap-3">
        <span className={`risk-icon risk-${recommendation.status}`}>
          <AlertTriangle size={18} />
        </span>
        <div>
          <p className="eyebrow">Agent reasoning</p>
          <h2 className="panel-title">{recommendation.recommendation}</h2>
        </div>
      </div>

      <div className="agent-source">
        {recommendation.llm_used
          ? `LLM: ${recommendation.llm_provider} (${recommendation.llm_model})`
          : "Deterministic backend explanation"}
      </div>

      <ul className="reason-list">
        {recommendation.reasoning.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>

      {primaryOption && recommendation.status !== "normal" && (
        <article className="approval-card">
          <div>
            <p className="eyebrow">Validation</p>
            <h3>
              {primaryOption.source_name} • {primaryOption.recommended_transfer_quantity} kits
            </h3>
            <p>
              {primaryOption.delivery_time_minutes} min • {primaryOption.road_status} route
            </p>
          </div>
          <TransferAction option={primaryOption} />
        </article>
      )}

      {recommendation.llm_agent && (
        <section className="llm-agent-panel">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="eyebrow">LLM agent</p>
              <h3>{recommendation.llm_agent.proposed_action}</h3>
            </div>
            <span
              className={`agent-status ${
                recommendation.llm_agent.available ? "agent-on" : "agent-off"
              }`}
            >
              {recommendation.llm_agent.available ? "Active" : "Needs key"}
            </span>
          </div>
          <div className="agent-source">
            {recommendation.llm_agent.provider}
            {recommendation.llm_agent.model
              ? ` (${recommendation.llm_agent.model})`
              : ""}
          </div>
          {recommendation.llm_agent.reasoning_summary.length > 0 && (
            <ul className="reason-list">
              {recommendation.llm_agent.reasoning_summary.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {alternatives.length > 0 && (
        <div className="space-y-2">
          <p className="eyebrow">Alternatives</p>
          {alternatives.map((option) => (
            <article className="option-card" key={option.source_id}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3>{option.source_name}</h3>
                  <p>
                    {option.source_type} • {option.road_status} route •{" "}
                    {option.delivery_time_minutes} min
                  </p>
                </div>
                <span className="rank-badge">#{option.rank}</span>
              </div>
              <div className="option-footer">
                <span>
                  <Route size={14} /> {option.recommended_transfer_quantity} kits
                </span>
                <span>{option.reason}</span>
              </div>
              <TransferAction option={option} />
            </article>
          ))}
        </div>
      )}

      {transfers.length > 0 && (
        <div className="space-y-2">
          <p className="eyebrow">Transfers ongoing</p>
          {transfers.map((transfer) => (
            <article className="transfer-card" key={transfer.id}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3>{transfer.quantity} kits to {transfer.target_clinic_name}</h3>
                  <p>
                    {transfer.source_name} • {transfer.delivery_time_minutes} min •{" "}
                    {transfer.road_status} route
                  </p>
                </div>
                <span className="transfer-status">{transfer.status}</span>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
