import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { getAlerts, runAnalysis } from "../api/fraudApi"
import { AlertTable } from "../components/AlertTable"
import { ErrorMessage, LoadingState } from "../components/Feedback"
import { MetricCard } from "../components/MetricCard"
import { SeverityBadge } from "../components/SeverityBadge"
import type { AlertListItem, AnalysisRunResponse, Severity } from "../types/api"

const severities: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

export function OverviewPage() {
  const [alerts, setAlerts] = useState<AlertListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [analysisRunning, setAnalysisRunning] = useState(false)
  const [analysisResult, setAnalysisResult] = useState<AnalysisRunResponse | null>(null)

  async function loadAlerts() {
    setLoading(true); setError(null)
    try { setAlerts(await getAlerts({ limit: 500 })) } catch (caught: unknown) { setError(caught instanceof Error ? caught.message : "Unable to load alerts.") } finally { setLoading(false) }
  }

  useEffect(() => { void loadAlerts() }, [])

  async function handleAnalysis() {
    setAnalysisRunning(true); setAnalysisResult(null); setError(null)
    try { setAnalysisResult(await runAnalysis()); await loadAlerts() } catch (caught: unknown) { setError(caught instanceof Error ? caught.message : "Risk analysis could not be completed.") } finally { setAnalysisRunning(false) }
  }

  const openCount = alerts.filter((alert) => alert.alert_status === "OPEN").length
  const criticalCount = alerts.filter((alert) => alert.severity === "CRITICAL").length
  const highCount = alerts.filter((alert) => alert.severity === "HIGH").length
  const averageRisk = alerts.length ? Math.round(alerts.reduce((total, alert) => total + alert.risk_score, 0) / alerts.length) : 0
  const recentAlerts = [...alerts].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at)).slice(0, 5)

  return <>
    <div className="page-heading"><div><span className="eyebrow accent">Overview</span><h1>Risk command center</h1><p>Monitor alerts, prioritize review, and keep the evidence trail visible.</p></div><button className="button primary" onClick={() => void handleAnalysis()} disabled={analysisRunning}>{analysisRunning ? "Running risk analysis..." : "Run Risk Analysis"}</button></div>
    {error ? <ErrorMessage message={error} onRetry={() => void loadAlerts()} /> : null}
    {analysisResult ? <div className="success-banner" role="status">Analysis complete. {analysisResult.alerts_created} alerts created and {analysisResult.alerts_updated} alerts updated.</div> : null}
    {loading ? <LoadingState label="Loading overview metrics" /> : <>
      <div className="metric-grid"><MetricCard label="Total alerts" value={alerts.length} detail="Across the current alert set" /><MetricCard label="Open alerts" value={openCount} detail="Awaiting analyst review" tone="positive" /><MetricCard label="Critical alerts" value={criticalCount} detail="Highest review priority" tone="critical" /><MetricCard label="High severity" value={highCount} detail="Requires focused attention" tone="high" /><MetricCard label="Average risk score" value={`${averageRisk}/100`} detail="Across returned alerts" /></div>
      <div className="dashboard-grid"><section className="panel distribution-panel"><div className="panel-heading"><div><span className="eyebrow">Signal mix</span><h2>Severity distribution</h2></div><span className="panel-kicker">{alerts.length} alerts</span></div>{severities.map((severity) => { const count = alerts.filter((alert) => alert.severity === severity).length; const width = alerts.length ? `${Math.max((count / alerts.length) * 100, count ? 3 : 0)}%` : "0%"; return <div className="distribution-row" key={severity}><div><SeverityBadge severity={severity} /><strong>{count}</strong></div><div className="bar-track" aria-label={`${count} ${severity} alerts`}><span className={`bar-fill bar-${severity.toLowerCase()}`} style={{ width }} /></div></div> })}</section><section className="panel distribution-panel"><div className="panel-heading"><div><span className="eyebrow">Workflow</span><h2>Status distribution</h2></div></div>{["OPEN", "ACKNOWLEDGED", "RESOLVED", "DISMISSED"].map((status) => { const count = alerts.filter((alert) => alert.alert_status === status).length; return <div className="status-row" key={status}><span>{status}</span><strong>{count}</strong><span className="status-line" style={{ width: `${alerts.length ? Math.max((count / alerts.length) * 100, count ? 3 : 0) : 0}%` }} /></div> })}</section></div>
      <section className="panel recent-panel"><div className="panel-heading"><div><span className="eyebrow">Freshest activity</span><h2>Recently updated alerts</h2></div><Link className="view-link" to="/alerts">View all alerts -&gt;</Link></div>{recentAlerts.length ? <AlertTable alerts={recentAlerts} /> : <p className="empty-state">No alerts are currently available.</p>}</section>
    </>}
  </>
}
