import { useEffect, useRef, useState } from "react"

const TABLEAU_EMBEDDING_SCRIPT_SRC = "https://public.tableau.com/javascripts/api/tableau.embedding.3.latest.min.js"
const TABLEAU_EMBEDDING_SCRIPT_ID = "tableau-embedding-api-v3"

type VizStatus = "loading" | "ready" | "error"

// Narrow surface of the tableau-viz custom element that this app relies on.
interface TableauVizElement extends HTMLElement {
  src: string
}

let embeddingApiPromise: Promise<void> | null = null

// Ensures the Tableau Embedding API v3 module script is only ever added once.
function loadTableauEmbeddingApi(): Promise<void> {
  if (embeddingApiPromise) return embeddingApiPromise

  embeddingApiPromise = new Promise((resolve, reject) => {
    const existing = document.getElementById(TABLEAU_EMBEDDING_SCRIPT_ID) as HTMLScriptElement | null
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true })
      existing.addEventListener("error", () => reject(new Error("Failed to load Tableau embedding API")), { once: true })
      return
    }

    const script = document.createElement("script")
    script.id = TABLEAU_EMBEDDING_SCRIPT_ID
    script.type = "module"
    script.src = TABLEAU_EMBEDDING_SCRIPT_SRC
    script.addEventListener("load", () => resolve(), { once: true })
    script.addEventListener("error", () => reject(new Error("Failed to load Tableau embedding API")), { once: true })
    document.head.appendChild(script)
  })

  return embeddingApiPromise
}

interface TableauVizProps {
  src: string
  minHeight?: number
}

export function TableauViz({ src, minHeight = 440 }: TableauVizProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<VizStatus>("loading")

  useEffect(() => {
    let cancelled = false
    let vizElement: TableauVizElement | null = null

    setStatus("loading")

    loadTableauEmbeddingApi()
      .then(() => {
        if (cancelled || !containerRef.current) return

        vizElement = document.createElement("tableau-viz") as TableauVizElement
        vizElement.src = src
        vizElement.setAttribute("toolbar", "bottom")
        vizElement.setAttribute("hide-tabs", "")
        // Only constrain width; letting height stay auto keeps the workbook's own aspect ratio
        // instead of Tableau shrinking width down to fit a forced host height.
        vizElement.style.width = "100%"
        vizElement.style.display = "block"
        vizElement.addEventListener("firstinteractive", () => {
          if (!cancelled) setStatus("ready")
        })

        containerRef.current.replaceChildren(vizElement)
      })
      .catch(() => {
        if (!cancelled) setStatus("error")
      })

    return () => {
      cancelled = true
      vizElement?.remove()
    }
  }, [src, minHeight])

  return (
    <div className="tableau-viz-wrapper">
      {status === "loading" && (
        <div className="tableau-viz-status feedback loading-state" role="status">
          <span className="spinner" aria-hidden="true" />
          <span>Loading Tableau visualization…</span>
        </div>
      )}
      {status === "error" && (
        <div className="tableau-viz-status feedback error-state" role="alert">
          <strong>Unable to load visualization</strong>
          <span>The Tableau Public visualization could not be initialized. Check your connection and try again later.</span>
        </div>
      )}
      <div
        ref={containerRef}
        className="tableau-viz-container"
        style={{ minHeight, display: status === "error" ? "none" : undefined }}
        aria-hidden={status !== "ready"}
      />
    </div>
  )
}
