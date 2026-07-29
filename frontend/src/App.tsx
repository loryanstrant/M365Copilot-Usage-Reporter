import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { useAuth } from "./auth/AuthContext";
import { FiltersProvider } from "./filters/FiltersContext";
import AboutPage from "./pages/AboutPage";
import BackfillPage from "./pages/BackfillPage";
import LaggardsPage from "./pages/LaggardsPage";
import LeaderboardsPage from "./pages/LeaderboardsPage";
import LicensesPage from "./pages/LicensesPage";
import LocationsPage from "./pages/LocationsPage";
import LoginPage from "./pages/LoginPage";
import OverviewPage from "./pages/OverviewPage";
import SettingsPage from "./pages/SettingsPage";
import UsagePage from "./pages/UsagePage";

export default function App() {
  const { user, loading } = useAuth();

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

  return (
    <FiltersProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/usage" element={<UsagePage />} />
          <Route path="/locations" element={<LocationsPage />} />
          <Route path="/leaderboards" element={<LeaderboardsPage />} />
          <Route path="/laggards" element={<LaggardsPage />} />
          <Route path="/licenses" element={<LicensesPage />} />
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
