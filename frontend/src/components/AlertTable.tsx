import { Link } from "react-router-dom"
import { SeverityBadge } from "./SeverityBadge"
import { StatusBadge } from "./StatusBadge"
import type { AlertListItem } from "../types/api"

type AlertTableProps = { alerts: AlertListItem[] }

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
}

export function AlertTable({ alerts }: AlertTableProps) {
  return (
    <div className="table-wrap">
      <table className="alert-table">
        <caption className="sr-only">Fraud risk alerts</caption>
        <thead><tr><th scope="col">Alert</th><th scope="col">Transaction</th><th scope="col">Customer</th><th scope="col">Type</th><th scope="col">Risk</th><th scope="col">Severity</th><th scope="col">Status</th><th scope="col">Updated</th><th scope="col"><span className="sr-only">Action</span></th></tr></thead>
        <tbody>
          {alerts.map((alert) => (
            <tr key={alert.alert_id}>
              <td><Link className="table-link" to={`/alerts/${alert.alert_id}`}>#{alert.alert_id}</Link></td>
              <td>{alert.transaction_id}</td><td>{alert.customer_id}</td><td>{alert.alert_type}</td>
              <td><strong>{alert.risk_score}</strong><span className="score-denom">/100</span></td>
              <td><SeverityBadge severity={alert.severity} /></td><td><StatusBadge status={alert.alert_status} /></td>
              <td className="date-cell">{formatDate(alert.updated_at)}</td>
              <td><Link className="view-link" to={`/alerts/${alert.alert_id}`}>View <span aria-hidden="true">-&gt;</span></Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
