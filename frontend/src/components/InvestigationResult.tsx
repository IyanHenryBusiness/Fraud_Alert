import type { InvestigationResponse } from "../types/api"

type InvestigationResultProps = { result: InvestigationResponse }

const providerLabels: Record<InvestigationResponse["provider"], string> = {
  gemini: "Generated with Google Gemini",
  mock: "Deterministic Mock Result",
  copilot_studio: "Generated with Copilot Studio",
}

export function InvestigationResult({ result }: InvestigationResultProps) {
  const actions = [...result.recommended_actions].sort((left, right) => left.priority - right.priority)
  return (
    <div className="investigation-result">
      <div className="result-meta"><span>Investigation #{result.investigation_id}</span><span>{providerLabels[result.provider]}</span><span>{new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(result.created_at))}</span></div>
      <p className="result-summary">{result.summary}</p>
      <div className="result-columns"><section><h3>Risk factors</h3>{result.risk_factors.length ? <ul>{result.risk_factors.map((factor) => <li key={factor}>{factor}</li>)}</ul> : <p className="muted">No specific risk factors returned.</p>}</section><section><h3>Missing information</h3>{result.missing_information.length ? <ul>{result.missing_information.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">No missing information identified.</p>}</section></div>
      <section><h3>Recommended actions</h3><ol className="action-list">{actions.map((item) => <li key={item.priority}><strong>{item.action}</strong><span>{item.reason}</span></li>)}</ol></section>
      <p className="disclaimer">{result.disclaimer}</p>
    </div>
  )
}
