import { PropsWithChildren } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../app/auth";
import { CostiqoBrand } from "./CostiqoBrand";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";

type RequireAuthProps = PropsWithChildren<{
  requireAdmin?: boolean;
}>;

export function RequireAuth({ children, requireAdmin = false }: RequireAuthProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { hasToken, isAuthenticated, isLoading, user } = useAuth();

  if (hasToken && isLoading) {
    return <LoadingState message="Checking session..." />;
  }

  if (!isAuthenticated) {
    const next = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }

  if (requireAdmin && user?.role !== "admin") {
    return (
      <main className="proto-page">
        <header className="proto-topbar" role="banner">
          <div className="proto-topbar__inner">
            <CostiqoBrand />
          </div>
        </header>
        <div style={{ maxWidth: "600px", margin: "4rem auto", padding: "0 1.5rem" }}>
          <ErrorState
            message="Admin access required for this page."
            detail="Your current account is authenticated as a shopper. The procurement operations portal is restricted to administrator accounts."
            actionLabel="Return to homepage"
            onAction={() => navigate("/")}
          />
        </div>
      </main>
    );
  }

  return <>{children}</>;
}
