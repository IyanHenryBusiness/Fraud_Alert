import type { Severity } from "../types/api"

type SeverityBadgeProps = { severity: Severity }

export function SeverityBadge({ severity }: SeverityBadgeProps) {
  return <span className={`badge severity-${severity.toLowerCase()}`}>{severity}</span>
}
