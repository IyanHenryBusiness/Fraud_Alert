type MetricCardProps = {
  label: string
  value: string | number
  detail: string
  tone?: "neutral" | "critical" | "high" | "positive"
}

export function MetricCard({ label, value, detail, tone = "neutral" }: MetricCardProps) {
  return (
    <article className={`metric-card metric-${tone}`}>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      <span className="metric-detail">{detail}</span>
    </article>
  )
}
