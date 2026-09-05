export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"

export type AlertStatus =
  | "OPEN"
  | "ACKNOWLEDGED"
  | "RESOLVED"
  | "DISMISSED"

export type InvestigationProvider = "mock" | "copilot_studio" | "gemini"

export type JsonPrimitive = string | number | boolean | null
export type JsonValue =
  | JsonPrimitive
  | JsonValue[]
  | { [key: string]: JsonValue }

export type TriggeredRule = {
  rule: string
  explanation: string
  points: number
  evidence: Record<string, JsonValue>
}

export type AlertListItem = {
  alert_id: number
  transaction_id: number
  customer_id: number
  analysis_key: string
  alert_type: string
  risk_score: number
  severity: Severity
  alert_status: AlertStatus
  created_at: string
  updated_at: string
}

export type AlertDetail = AlertListItem & {
  triggered_rules: TriggeredRule[]
  notes: string | null
}

export type AlertStatusUpdate = {
  alert_status: AlertStatus
  notes?: string
}

export type RecommendedAction = {
  priority: number
  action: string
  reason: string
}

export type InvestigationResponse = {
  investigation_id: number
  alert_id: number
  provider: InvestigationProvider
  summary: string
  risk_factors: string[]
  missing_information: string[]
  recommended_actions: RecommendedAction[]
  disclaimer: string
  created_at: string
}

export type SeverityTotals = Record<Severity, number>

export type AnalysisRunResponse = {
  ruleset_version: string
  transactions_analyzed: number
  alerts_created: number
  alerts_updated: number
  transactions_without_alerts: number
  quality_issues_found: number
  severity_totals: SeverityTotals
}
