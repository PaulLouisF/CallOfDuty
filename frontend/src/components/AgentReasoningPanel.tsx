import { AlertTriangle, Route } from "lucide-react";
import type { AgentRecommendation } from "../types";

type AgentReasoningPanelProps = {
  recommendation: AgentRecommendation | null;
  loading: boolean;
};

export function AgentReasoningPanel({
  recommendation,
  loading,
}: AgentReasoningPanelProps) {
  if (loading) {
    return <div className="panel-muted">Loading recommendation...</div>;
  }

  if (!recommendation) {
    return <div className="panel-muted">Clinic recommendations appear here.</div>;
  }

  const alternatives = recommendation.options.slice(1, 4);

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
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
