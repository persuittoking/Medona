import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { isAdmin } from "./api/types";
import { ErrorBoundary, Skeleton } from "./components/ui";
import "./index.css";
import { AuthProvider, useAuth } from "./lib/auth";
import { ToastProvider } from "./lib/toast";
import Alerts from "./pages/Alerts";
import ChildCard from "./pages/ChildCard";
import Dashboard from "./pages/Dashboard";
import ExternalVisit from "./pages/ExternalVisit";
import GeoDrilldown from "./pages/GeoDrilldown";
import PolyclinicMap from "./pages/PolyclinicMap";
import Login from "./pages/Login";
import { About, Analytics, Audit } from "./pages/Misc";
import Quality from "./pages/Quality";
import NewChildCheck from "./pages/NewChildCheck";
import NewVisit from "./pages/NewVisit";
import PatientCard from "./pages/PatientCard";
import Patients from "./pages/Patients";

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-6"><Skeleton className="h-40" /></div>;
  return user ? <>{children}</> : <Navigate to="/login" replace />;
}

function Home() {
  const { user } = useAuth();
  return <Navigate to={isAdmin(user?.role) ? "/geo" : user?.role === "nurse" ? "/map" : "/dashboard"} replace />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={qc}>
        <AuthProvider>
          <ToastProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route element={<Protected><AppShell /></Protected>}>
                  <Route path="/" element={<Home />} />
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/map" element={<PolyclinicMap />} />
                  <Route path="/geo" element={<GeoDrilldown />} />
                  <Route path="/geo/:level/:id" element={<GeoDrilldown />} />
                  <Route path="/patients" element={<Patients />} />
                  <Route path="/patients/:id" element={<PatientCard />} />
                  <Route path="/visits/new" element={<NewVisit />} />
                  <Route path="/external-visit" element={<ExternalVisit />} />
                  <Route path="/children/:id" element={<ChildCard />} />
                  <Route path="/children/:id/checks/new" element={<NewChildCheck />} />
                  <Route path="/alerts" element={<Alerts />} />
                  <Route path="/analytics" element={<Analytics />} />
                  <Route path="/audit" element={<Audit />} />
                  <Route path="/quality" element={<Quality />} />
                  <Route path="/about" element={<About />} />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </BrowserRouter>
          </ToastProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
);
