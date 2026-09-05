import { TableauViz } from "../components/TableauViz"

const TABLEAU_URL_PREFIX = "https://public.tableau.com/views/"

function isValidTableauVizUrl(url: string | undefined): url is string {
  return typeof url === "string" && url.startsWith(TABLEAU_URL_PREFIX)
}

export function AnalyticsPage() {
  const vizUrl = import.meta.env.VITE_TABLEAU_VIZ_URL
  const hasValidVizUrl = isValidTableauVizUrl(vizUrl)

  return (
    <div className="analytics-page">
      <span className="eyebrow accent">Reporting studio</span>
      <h1>Fraud Analytics</h1>
      <p className="intro-copy">
        This aggregate Tableau report summarizes fraud-risk trends and operational metrics across alerts, giving teams
        a wider lens beyond individual investigations.
      </p>
      {hasValidVizUrl ? (
        <section className="tableau-embed tableau-embed-full" aria-label="Tableau Public fraud analytics visualization">
          <TableauViz src={vizUrl} minHeight={720} />
          <a className="tableau-open-link" href={vizUrl} target="_blank" rel="noopener noreferrer">
            Open in Tableau Public
          </a>
        </section>
      ) : (
        <section className="tableau-placeholder" aria-label="Tableau visualization placeholder">
          <div className="placeholder-grid" />
          <div className="placeholder-copy">
            <span className="placeholder-icon">+</span>
            <h2>Tableau Public visualization</h2>
            <p>
              Set the <code>VITE_TABLEAU_VIZ_URL</code> environment variable to a published Tableau Public view URL
              (starting with <code>{TABLEAU_URL_PREFIX}</code>) to display the live dashboard here.
            </p>
          </div>
        </section>
      )}
    </div>
  )
}
