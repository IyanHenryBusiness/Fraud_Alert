import { Link } from "react-router-dom"

export function NotFoundPage() {
  return <div className="not-found"><span className="eyebrow accent">404 / route unavailable</span><h1>That view is not in the workspace.</h1><p>Return to the risk command center to continue reviewing alerts.</p><Link className="button primary" to="/">Back to overview</Link></div>
}
