import { FormEvent, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";

import { CostiqoBrand } from "../components/CostiqoBrand";
import { useAuth } from "../app/auth";
import { api } from "../services/api";

function getAuthErrorMessage(mode: "login" | "register") {
  return mode === "login"
    ? "We could not sign you in. Check your email and password."
    : "We could not create your account right now. Check the details and try again.";
}

export function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { isAuthenticated, setSession } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [status, setStatus] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const next = searchParams.get("next") || "/";

  if (isAuthenticated) {
    return <Navigate to={next} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const username = String(formData.get("username") ?? "");
    const email = String(formData.get("email") ?? "");
    const password = String(formData.get("password") ?? "");
    const name = String(formData.get("name") ?? "");

    setLoading(true);
    setStatus("");

    try {
      const response =
        mode === "login"
          ? await api.login({ username, password })
          : await api.register({ name, email, password });
      setSession(response);
      navigate(next, { replace: true });
    } catch {
      setStatus(getAuthErrorMessage(mode));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="proto-page proto-page--auth">
      <div className="login-backdrop-illustration" aria-hidden="true">
        <svg viewBox="0 0 800 600" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="400" cy="300" r="280" stroke="#EAE5E0" strokeWidth="1" strokeDasharray="8 8" />
          <circle cx="400" cy="300" r="180" stroke="#F0ECE8" strokeWidth="1" />
          <path
            d="M 100 300 C 250 150, 550 150, 700 300 C 550 450, 250 450, 100 300 Z"
            stroke="#38000A"
            strokeWidth="1.2"
            strokeOpacity="0.1"
          />
        </svg>
      </div>

      <section className="login-page">
        <div className="login-card">
          <div className="login-card__header">
            <CostiqoBrand size="lg" />
            <h1 className="login-title">
              {mode === "login" ? "Welcome back" : "Create your Costiqo account"}
            </h1>
            <p className="login-subtitle">
              {mode === "login"
                ? "Sign in to access saved bookmarks, personalized pincodes, and price tracking."
                : "Join Costiqo to monitor deals, save products, and compare prices across top sellers."}
            </p>
          </div>

          <div className="login-tabs" role="tablist" aria-label="Authentication mode">
            <button
              type="button"
              className={`login-tab ${mode === "login" ? "login-tab--active" : ""}`}
              role="tab"
              aria-selected={mode === "login"}
              onClick={() => {
                setMode("login");
                setStatus("");
              }}
            >
              Sign In
            </button>
            <button
              type="button"
              className={`login-tab ${mode === "register" ? "login-tab--active" : ""}`}
              role="tab"
              aria-selected={mode === "register"}
              onClick={() => {
                setMode("register");
                setStatus("");
              }}
            >
              Register
            </button>
          </div>

          {status && <div className="status-banner" role="alert">{status}</div>}

          <form className="login-form" onSubmit={handleSubmit}>
            {mode === "register" ? (
              <div className="form-field">
                <label htmlFor="auth-name">Full Name</label>
                <input
                  id="auth-name"
                  name="name"
                  placeholder="e.g. Alex Sharma"
                  required
                  autoComplete="name"
                />
              </div>
            ) : null}

            {mode === "login" ? (
              <div className="form-field">
                <label htmlFor="auth-username">Email Address or Username</label>
                <input
                  id="auth-username"
                  name="username"
                  placeholder="name@example.com"
                  required
                  autoComplete="username"
                />
              </div>
            ) : (
              <div className="form-field">
                <label htmlFor="auth-email">Email Address</label>
                <input
                  id="auth-email"
                  name="email"
                  type="email"
                  placeholder="name@example.com"
                  required
                  autoComplete="email"
                />
              </div>
            )}

            <div className="form-field">
              <label htmlFor="auth-password">Password</label>
              <input
                id="auth-password"
                name="password"
                type="password"
                placeholder="Enter your password"
                required
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </div>

            <button
              type="submit"
              className="proto-btn proto-btn--primary login-submit"
              disabled={loading}
            >
              {loading
                ? mode === "login"
                  ? "Signing in..."
                  : "Creating account..."
                : mode === "login"
                  ? "Sign In"
                  : "Create Account"}
            </button>
          </form>

          <div className="login-card__footer">
            <p className="caption">
              By proceeding, you agree to Costiqo&apos;s standard terms of use and transparent privacy policies.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
