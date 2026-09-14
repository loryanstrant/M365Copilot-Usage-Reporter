import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { useAuth } from "./auth/AuthContext";
import { FiltersProvider } from "./filters/FiltersContext";
import { useSetupStatus } from "./hooks/useSetupStatus";
import AboutPage from "./pages/AboutPage";
import BackfillPage from "./pages/BackfillPage";
import BriefingPage from "./pages/BriefingPage";
import CoachingPage from "./pages/CoachingPage";
import LaggardsPage from "./pages/LaggardsPage";
import LeaderboardsPage from "./pages/LeaderboardsPage";
import LicensesPage from "./pages/LicensesPage";
import LocationsPage from "./pages/LocationsPage";
import LoginPage from "./pages/LoginPage";
import OverviewPage from "./pages/OverviewPage";
import SettingsPage from "./pages/SettingsPage";
import SetupGuidePage from "./pages/SetupGuidePage";
import UsagePage from "./pages/UsagePage";

export default function App() {
  const { user, loading } = useAuth();
  const { configured, checked } = useSetupStatus(Boolean(user));

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-slate-500">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  // First run: send admins straight to Settings (where the wizard opens itself)
  // until a connection is configured. Non-admins carry on to the dashboards and
  // see the usual empty states.
  const needsSetup = checked && !configured && user.role === "admin";

  return (
    <FiltersProvider>
      <Layout>
        <Routes>
          <Route
            path="/"
            element={needsSetup ? <Navigate to="/settings" replace /> : <OverviewPage />}
          />
          <Route path="/briefing" element={<BriefingPage />} />
          <Route path="/usage" element={<UsagePage />} />
          <Route path="/locations" element={<LocationsPage />} />
          <Route path="/leaderboards" element={<LeaderboardsPage />} />
          <Route path="/laggards" element={<LaggardsPage />} />
          <Route path="/coaching" element={<CoachingPage />} />
          <Route path="/licenses" element={<LicensesPage />} />
          <Route path="/help" element={<SetupGuidePage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route
            path="/settings"
            element={user.role === "admin" ? <SettingsPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/backfill"
            element={user.role === "admin" ? <BackfillPage /> : <Navigate to="/" replace />}
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </FiltersProvider>
  );
}
