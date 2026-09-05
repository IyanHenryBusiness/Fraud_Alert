import type { JsonValue, TriggeredRule } from "../types/api"

type RuleEvidenceListProps = { rules: TriggeredRule[] }

function formatValue(value: JsonValue): string {
  if (value === null) return "Not recorded"
  if (typeof value === "object") return Array.isArray(value) ? value.map(formatValue).join(", ") : Object.entries(value).map(([key, item]) => `${key}: ${formatValue(item)}`).join("; ")
  return String(value)
}

export function RuleEvidenceList({ rules }: RuleEvidenceListProps) {
  if (rules.length === 0) return <p className="muted">No triggered rules were returned for this alert.</p>
  return <div className="rule-list">{rules.map((rule) => <article className="rule-item" key={rule.rule}><div className="rule-heading"><strong>{rule.rule}</strong><span className="points">+{rule.points} points</span></div><p>{rule.explanation}</p><dl className="evidence-list">{Object.entries(rule.evidence).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{formatValue(value)}</dd></div>)}</dl></article>)}</div>
}
