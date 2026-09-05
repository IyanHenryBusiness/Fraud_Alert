import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { generateInvestigation, getAlert, updateAlertStatus } from "../api/fraudApi"
import { ErrorMessage, LoadingState } from "../components/Feedback"
import { InvestigationResult } from "../components/InvestigationResult"
import { RuleEvidenceList } from "../components/RuleEvidenceList"
import { SeverityBadge } from "../components/SeverityBadge"
import { StatusBadge } from "../components/StatusBadge"
import type { AlertDetail, AlertStatus, InvestigationResponse } from "../types/api"

const statuses: AlertStatus[] = ["OPEN", "ACKNOWLEDGED", "RESOLVED", "DISMISSED"]

export function AlertDetailPage() {
  const { alertId } = useParams()
  const parsedId = alertId && /^\d+$/.test(alertId) ? Number(alertId) : null
  const [alert, setAlert] = useState<AlertDetail | null>(null)
  const [investigation, setInvestigation] = useState<InvestigationResponse | null>(null)
  const [status, setStatus] = useState<AlertStatus>("OPEN")
  const [notes, setNotes] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function loadAlert() {
    if (parsedId === null) { setLoading(false); setError("The alert ID in this URL is invalid."); return }
    setLoading(true); setError(null)
    try { const loaded = await getAlert(parsedId); setAlert(loaded); setStatus(loaded.alert_status); setNotes(loaded.notes ?? "") } catch (caught: unknown) { setError(caught instanceof Error ? caught.message : "Unable to load this alert.") } finally { setLoading(false) }
  }

  useEffect(() => { void loadAlert() }, [parsedId])

  async function handleStatusSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!alert) return
    setSaving(true); setMessage(null); setError(null)
    try { const updated = await updateAlertStatus(alert.alert_id, { alert_status: status, notes: notes || undefined }); setAlert(updated); setStatus(updated.alert_status); setNotes(updated.notes ?? ""); setMessage("Alert status and notes updated.") } catch (caught: unknown) { setError(caught instanceof Error ? caught.message : "The alert could not be updated.") } finally { setSaving(false) }
  }

  async function handleInvestigation() {
    if (!alert) return
    setGenerating(true); setMessage(null); setError(null)
    try { setInvestigation(await generateInvestigation(alert.alert_id)); setMessage("Investigation generated for analyst review.") } catch (caught: unknown) { setError(caught instanceof Error ? caught.message : "The investigation could not be generated.") } finally { setGenerating(false) }
  }

  if (loading) return <LoadingState label="Loading alert detail" />
  if (!alert) return <><ErrorMessage message={error ?? "This alert is unavailable."} onRetry={() => void loadAlert()} /><Link className="back-link" to="/alerts">&lt;- Back to alerts</Link></>

  return <><div className="detail-top"><Link className="back-link" to="/alerts">&lt;- Back to alerts</Link><div className="page-heading"><div><span className="eyebrow accent">Alert #{alert.alert_id}</span><h1>{alert.alert_type.replaceAll("_", " ")}</h1><p>Analysis key {alert.analysis_key}</p></div><div className="badge-stack"><SeverityBadge severity={alert.severity} /><StatusBadge status={alert.alert_status} /></div></div></div>{error ? <ErrorMessage message={error} /> : null}{message ? <div className="success-banner" role="status">{message}</div> : null}<div className="detail-grid"><section className="panel detail-panel"><div className="panel-heading"><div><span className="eyebrow">Alert record</span><h2>Signal details</h2></div><strong className="detail-score">{alert.risk_score}<small>/100 risk</small></strong></div><dl className="detail-list"><div><dt>Alert ID</dt><dd>#{alert.alert_id}</dd></div><div><dt>Transaction ID</dt><dd>{alert.transaction_id}</dd></div><div><dt>Customer ID</dt><dd>{alert.customer_id}</dd></div><div><dt>Analysis key</dt><dd>{alert.analysis_key}</dd></div><div><dt>Severity</dt><dd><SeverityBadge severity={alert.severity} /></dd></div><div><dt>Created</dt><dd>{new Date(alert.created_at).toLocaleString()}</dd></div><div><dt>Last updated</dt><dd>{new Date(alert.updated_at).toLocaleString()}</dd></div></dl></section><section className="panel status-panel"><div className="panel-heading"><div><span className="eyebrow">Analyst control</span><h2>Update status</h2></div></div><form onSubmit={(event) => void handleStatusSubmit(event)}><label>Status<select value={status} onChange={(event) => setStatus(event.target.value as AlertStatus)}>{statuses.map((option) => <option key={option} value={option}>{option}</option>)}</select></label><label>Notes <span className="field-hint">{notes.length}/500</span><textarea maxLength={500} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Add context for the next analyst..." /></label><button className="button primary full-button" disabled={saving}>{saving ? "Saving update..." : "Save status update"}</button></form></section></div><section className="panel evidence-panel"><div className="panel-heading"><div><span className="eyebrow">Explainability</span><h2>Triggered rules</h2></div><span className="panel-kicker">{alert.triggered_rules.length} rules</span></div><RuleEvidenceList rules={alert.triggered_rules} /></section><section className="panel investigation-panel"><div className="panel-heading"><div><span className="eyebrow">Human-in-the-loop support</span><h2>AI-Assisted Investigation</h2></div><button className="button primary" onClick={() => void handleInvestigation()} disabled={generating}>{generating ? "Analyzing constrained evidence..." : "Generate AI Investigation"}</button></div><p className="investigation-note">The configured FastAPI provider analyzes only the selected alert's constrained evidence. The result is for analyst review and is not a fraud determination.</p>{investigation ? <InvestigationResult result={investigation} /> : <p className="muted">No investigation has been generated in this session.</p>}</section></>
}
