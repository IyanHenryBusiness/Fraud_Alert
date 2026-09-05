import type {
  AlertDetail,
  AlertListItem,
  AlertStatus,
  AlertStatusUpdate,
  AnalysisRunResponse,
  InvestigationResponse,
  Severity,
} from "../types/api"

const API_ORIGIN = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"

export class FraudApiError extends Error {
  readonly status: number | null

  constructor(message: string, status: number | null = null) {
    super(message)
    this.name = "FraudApiError"
    this.status = status
  }
}

type AlertQuery = {
  severity?: Severity
  alert_status?: AlertStatus
  limit?: number
  offset?: number
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const response = await fetch(`${API_ORIGIN}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    })

    if (!response.ok) {
      if (response.status === 404) {
        throw new FraudApiError("The requested alert could not be found.", response.status)
      }
      if (response.status === 422) {
        throw new FraudApiError("The request was invalid.", response.status)
      }
      if (response.status === 500) {
        throw new FraudApiError("The server could not complete the request.", response.status)
      }
      if (response.status === 502) {
        throw new FraudApiError("The AI provider could not complete the investigation.", response.status)
      }
      if (response.status === 503) {
        throw new FraudApiError("The AI provider is not configured.", response.status)
      }
      if (response.status === 504) {
        throw new FraudApiError("The AI provider timed out.", response.status)
      }
      throw new FraudApiError("The server could not complete the request.", response.status)
    }

    const text = await response.text()
    if (!text) {
      return undefined as T
    }

    try {
      return JSON.parse(text) as T
    } catch {
      throw new FraudApiError("The server returned an invalid response.", response.status)
    }
  } catch (error: unknown) {
    if (error instanceof FraudApiError) {
      throw error
    }
    throw new FraudApiError("The FastAPI server could not be reached.")
  }
}

export function getAlerts(query: AlertQuery = {}): Promise<AlertListItem[]> {
  const params = new URLSearchParams()
  if (query.severity) params.set("severity", query.severity)
  if (query.alert_status) params.set("alert_status", query.alert_status)
  if (query.limit !== undefined) params.set("limit", String(query.limit))
  if (query.offset !== undefined) params.set("offset", String(query.offset))
  const suffix = params.toString() ? `?${params.toString()}` : ""
  return request<AlertListItem[]>(`/api/alerts${suffix}`)
}

export function getAlert(alertId: number): Promise<AlertDetail> {
  return request<AlertDetail>(`/api/alerts/${alertId}`)
}

export function updateAlertStatus(
  alertId: number,
  update: AlertStatusUpdate,
): Promise<AlertDetail> {
  return request<AlertDetail>(`/api/alerts/${alertId}/status`, {
    method: "PATCH",
    body: JSON.stringify(update),
  })
}

export function generateInvestigation(alertId: number): Promise<InvestigationResponse> {
  return request<InvestigationResponse>("/api/investigations/generate", {
    method: "POST",
    body: JSON.stringify({ alert_id: alertId }),
  })
}

export function runAnalysis(): Promise<AnalysisRunResponse> {
  return request<AnalysisRunResponse>("/api/analysis/run", { method: "POST" })
}
