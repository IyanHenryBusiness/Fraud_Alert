import { Navigate, Route, Routes } from "react-router-dom"
import { AppLayout } from "./components/AppLayout"
import { AlertDetailPage } from "./pages/AlertDetailPage"
import { AlertsPage } from "./pages/AlertsPage"
import { AnalyticsPage } from "./pages/AnalyticsPage"
import { NotFoundPage } from "./pages/NotFoundPage"
import { OverviewPage } from "./pages/OverviewPage"

function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="alerts/:alertId" element={<AlertDetailPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="not-found" element={<NotFoundPage />} />
        <Route path="*" element={<Navigate to="/not-found" replace />} />
      </Route>
    </Routes>
  )
}

export default App
