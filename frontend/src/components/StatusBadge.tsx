import type { AlertStatus } from "../types/api"

type StatusBadgeProps = { status: AlertStatus }

export function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={`badge status-${status.toLowerCase()}`}>{status}</span>
}
