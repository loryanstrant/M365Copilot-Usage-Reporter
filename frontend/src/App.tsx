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
import PersonalPage from "./pages/PersonalPage";
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

  // Anyone signed in with a work account lands on their own data. The password
  // admin has no Entra identity, so there is no "me" to show them — they go
  // straight to the organisation view.
  const landing = needsSetup ? (
    <Navigate to="/settings" replace />
  ) : user.has_personal_view ? (
    <PersonalPage />
  ) : (
    <OverviewPage />
  );

  // Organisation pages are gated. The API enforces this too — this only keeps
  // someone from landing on a page that would just error.
  const org = (element: JSX.Element) =>
    user.can_view_org ? element : <Navigate to="/" replace />;

  return (
    <FiltersProvider>
      <Layout>
        <Routes>
          <Route path="/" element={landing} />
          <Route path="/me" element={<PersonalPage />} />
          <Route path="/overview" element={org(<OverviewPage />)} />
          <Route path="/briefing" element={org(<BriefingPage />)} />
          <Route path="/usage" element={org(<UsagePage />)} />
          <Route path="/locations" element={org(<LocationsPage />)} />
          <Route path="/leaderboards" element={org(<LeaderboardsPage />)} />
          <Route path="/laggards" element={org(<LaggardsPage />)} />
          <Route path="/coaching" element={org(<CoachingPage />)} />
          <Route path="/licenses" element={org(<LicensesPage />)} />
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
