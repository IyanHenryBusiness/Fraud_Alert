import { useEffect, useState } from "react"
import { AlertTable } from "../components/AlertTable"
import { ErrorMessage, LoadingState } from "../components/Feedback"
import { getAlerts } from "../api/fraudApi"
import type { AlertListItem, AlertStatus, Severity } from "../types/api"

const severityOptions: Array<Severity | "ALL"> = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"]
const statusOptions: Array<AlertStatus | "ALL"> = ["ALL", "OPEN", "ACKNOWLEDGED", "RESOLVED", "DISMISSED"]

type SortDirection = "high" | "low"

export function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertListItem[]>([])
  const [query, setQuery] = useState("")
  const [severity, setSeverity] = useState<Severity | "ALL">("ALL")
  const [status, setStatus] = useState<AlertStatus | "ALL">("ALL")
  const [sort, setSort] = useState<SortDirection>("high")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function loadAlerts() {
    setLoading(true); setError(null)
    try { setAlerts(await getAlerts({ severity: severity === "ALL" ? undefined : severity, alert_status: status === "ALL" ? undefined : status, limit: 500 })) } catch (caught: unknown) { setError(caught instanceof Error ? caught.message : "Unable to load alerts.") } finally { setLoading(false) }
  }

  useEffect(() => { void loadAlerts() }, [severity, status])

  const visibleAlerts = alerts.filter((alert) => { const searchable = `${alert.alert_id} ${alert.transaction_id} ${alert.customer_id} ${alert.alert_type} ${alert.analysis_key}`.toLowerCase(); return searchable.includes(query.toLowerCase()) }).sort((left, right) => sort === "high" ? right.risk_score - left.risk_score : left.risk_score - right.risk_score)

  function clearFilters() { setQuery(""); setSeverity("ALL"); setStatus("ALL"); setSort("high") }

  return <><div className="page-heading"><div><span className="eyebrow accent">Alert queue</span><h1>Alerts</h1><p>Search and triage risk signals returned by the analysis service.</p></div><span className="result-count">{visibleAlerts.length} visible</span></div><section className="panel filter-panel"><div className="filter-grid"><label>Search<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ID, type, or analysis key" /></label><label>Severity<select value={severity} onChange={(event) => setSeverity(event.target.value as Severity | "ALL")}>{severityOptions.map((option) => <option key={option} value={option}>{option === "ALL" ? "All severities" : option}</option>)}</select></label><label>Status<select value={status} onChange={(event) => setStatus(event.target.value as AlertStatus | "ALL")}>{statusOptions.map((option) => <option key={option} value={option}>{option === "ALL" ? "All statuses" : option}</option>)}</select></label><label>Risk score<select value={sort} onChange={(event) => setSort(event.target.value as SortDirection)}><option value="high">Highest first</option><option value="low">Lowest first</option></select></label><button className="button secondary clear-button" onClick={clearFilters}>Clear filters</button></div></section>{error ? <ErrorMessage message={error} onRetry={() => void loadAlerts()} /> : null}{loading ? <LoadingState label="Loading alert queue" /> : <section className="panel table-panel">{visibleAlerts.length ? <AlertTable alerts={visibleAlerts} /> : <div className="empty-state"><strong>No matching alerts</strong><span>Adjust the search or filters and try again.</span></div>}</section>}</>
}
