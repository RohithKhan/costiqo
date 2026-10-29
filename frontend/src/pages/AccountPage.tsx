import { useQuery } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../app/auth";
import { CostiqoBrand } from "../components/CostiqoBrand";
import { LoadingState } from "../components/LoadingState";
import { SiteFooter } from "../components/SiteFooter";
import { api } from "../services/api";

type ProfileTab = "products" | "settings";

function formatDate(value: string) {
  return new Date(value).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function getInitials(name: string | undefined) {
  if (!name) {
    return "U";
  }
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "U";
}

function getHostLabel(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "Saved link";
  }
}

export function AccountPage() {
  const { isAuthenticated, signOut, user } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<ProfileTab>("products");
  const [status, setStatus] = useState("");
  const [passwordStatus, setPasswordStatus] = useState("");
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const savedProductsQuery = useQuery({
    queryKey: ["saved-products"],
    queryFn: api.fetchSavedProducts,
    enabled: isAuthenticated,
    refetchOnMount: "always",
    staleTime: 0,
  });

  async function handleRemoveSavedProduct(savedProductId: number) {
    setBusyKey(`saved-product-${savedProductId}`);
    setStatus("");
    try {
      await api.removeSavedProduct(savedProductId);
      await savedProductsQuery.refetch();
      setStatus("Bookmark removed from your account.");
    } catch {
      setStatus("Could not remove bookmark right now. Please retry.");
    } finally {
      setBusyKey(null);
    }
  }

  async function handleChangePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const currentPassword = String(formData.get("current_password") ?? "");
    const newPassword = String(formData.get("new_password") ?? "");
    const confirmPassword = String(formData.get("confirm_password") ?? "");

    if (newPassword !== confirmPassword) {
      setPasswordStatus("New passwords do not match.");
      return;
    }

    if (newPassword.length < 8) {
      setPasswordStatus("Password must be at least 8 characters.");
      return;
    }

    setBusyKey("password");
    setPasswordStatus("");
    try {
      await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordStatus("Password updated successfully.");
      setPasswordDialogOpen(false);
    } catch {
      setPasswordStatus("Current password incorrect or update failed.");
    } finally {
      setBusyKey(null);
    }
  }

  async function handleDeleteAccount() {
    if (!window.confirm("Are you sure you want to permanently delete your Costiqo account?")) {
      return;
    }

    setBusyKey("delete-account");
    try {
      await api.deleteAccount();
      signOut();
      navigate("/");
    } catch {
      setStatus("Account deletion failed. Try again.");
      setBusyKey(null);
    }
  }

  if (savedProductsQuery.isLoading) {
    return <LoadingState message="Loading your bookmarks..." />;
  }

  const savedProducts = savedProductsQuery.data ?? [];
  const bookmarkUnavailable = savedProductsQuery.isError;

  return (
    <main className="proto-page account-page">
      {/* Top Header */}
      <header className="proto-topbar" role="banner">
        <div className="proto-topbar__inner">
          <CostiqoBrand />

          <nav className="proto-nav" aria-label="Navigation">
            <Link className="proto-nav__link" to="/">
              Home
            </Link>
            <Link className="proto-nav__link" to="/search">
              Search
            </Link>
            {user?.role === "admin" && (
              <Link className="proto-nav__link" to="/admin">
                Admin
              </Link>
            )}
          </nav>

          <div className="proto-topbar__actions">
            <button
              type="button"
              className="proto-btn proto-btn--ghost proto-btn--sm"
              onClick={() => {
                signOut();
                navigate("/");
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <div className="page account-shell">
        {/* Profile Card Header */}
        <section className="profile-hero-card">
          <div className="profile-hero-card__avatar">{getInitials(user?.name)}</div>
          <div className="profile-hero-card__meta">
            <h1>{user?.name ?? "Your Account"}</h1>
            <p className="profile-email">{user?.email}</p>
            <span className="profile-badge">{user?.role === "admin" ? "Administrator" : "Standard Account"}</span>
          </div>
        </section>

        {/* Tab Controls */}
        <div className="profile-tabs" role="tablist" aria-label="Profile navigation">
          <button
            type="button"
            className={`profile-tab ${activeTab === "products" ? "active" : ""}`}
            onClick={() => setActiveTab("products")}
          >
            Saved Bookmarks ({savedProducts.length})
          </button>
          <button
            type="button"
            className={`profile-tab ${activeTab === "settings" ? "active" : ""}`}
            onClick={() => setActiveTab("settings")}
          >
            Account Settings
          </button>
        </div>

        {status ? <div className="status-banner" role="status">{status}</div> : null}

        {/* Tab Content */}
        <section className="profile-content">
          {activeTab === "products" ? (
            <div className="profile-section">
              {bookmarkUnavailable ? (
                <div className="account-empty">
                  <p>Bookmarks are temporarily unavailable.</p>
                  <span className="small-copy">Your profile is still active. Please refresh after a moment.</span>
                </div>
              ) : savedProducts.length ? (
                <div className="saved-items-grid">
                  {savedProducts.map((item) => (
                    <article className="saved-item-card" key={item.id}>
                      <div className="saved-item-card__header">
                        <span className="saved-item-card__host">{getHostLabel(item.product_url)}</span>
                        <span className="saved-item-card__date">Saved {formatDate(item.created_at)}</span>
                      </div>
                      <h3 className="saved-item-card__title">{item.product_name}</h3>
                      <div className="saved-item-card__actions">
                        <a
                          className="proto-btn proto-btn--soft proto-btn--sm"
                          href={item.product_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Open Store Link ↗
                        </a>
                        <button
                          type="button"
                          className="proto-btn proto-btn--ghost proto-btn--sm"
                          disabled={busyKey === `saved-product-${item.id}`}
                          onClick={() => handleRemoveSavedProduct(item.id)}
                        >
                          Remove
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="account-empty">
                  <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M19 21 12 17 5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
                  </svg>
                  <p>No saved product bookmarks yet.</p>
                  <span className="small-copy">Search products and click &quot;Save&quot; to bookmark deals for tracking.</span>
                  <Link to="/" className="proto-btn proto-btn--primary proto-btn--sm" style={{ marginTop: "12px" }}>
                    Explore Products
                  </Link>
                </div>
              )}
            </div>
          ) : (
            <div className="profile-section">
              <div className="settings-cards-list">
                <article className="settings-card">
                  <div className="settings-card__info">
                    <strong>Change Password</strong>
                    <span className="caption">Ensure your account uses a secure password of at least 8 characters.</span>
                  </div>
                  <button
                    type="button"
                    className="proto-btn proto-btn--outline proto-btn--sm"
                    onClick={() => {
                      setPasswordStatus("");
                      setPasswordDialogOpen(true);
                    }}
                  >
                    Change Password
                  </button>
                </article>

                <article className="settings-card settings-card--danger">
                  <div className="settings-card__info">
                    <strong className="danger-text">Delete Account</strong>
                    <span className="caption">Permanently delete your profile, preferences, and saved bookmarks.</span>
                  </div>
                  <button
                    type="button"
                    className="proto-btn proto-btn--outline proto-btn--sm danger-button"
                    disabled={busyKey === "delete-account"}
                    onClick={handleDeleteAccount}
                  >
                    Delete Account
                  </button>
                </article>
              </div>

              {/* Password Modal */}
              {passwordDialogOpen && (
                <div className="pincode-dropdown-backdrop" onClick={() => setPasswordDialogOpen(false)}>
                  <div className="password-modal-card" onClick={(e) => e.stopPropagation()}>
                    <div className="modal-header">
                      <h3>Change Password</h3>
                      <button
                        type="button"
                        className="modal-close-btn"
                        onClick={() => setPasswordDialogOpen(false)}
                      >
                        ✕
                      </button>
                    </div>
                    {passwordStatus && <div className="status-banner" style={{ marginBottom: "12px" }}>{passwordStatus}</div>}
                    <form onSubmit={handleChangePassword}>
                      <div className="form-field">
                        <label htmlFor="current_password">Current Password</label>
                        <input id="current_password" name="current_password" type="password" required />
                      </div>
                      <div className="form-field">
                        <label htmlFor="new_password">New Password (8+ characters)</label>
                        <input id="new_password" name="new_password" type="password" minLength={8} required />
                      </div>
                      <div className="form-field">
                        <label htmlFor="confirm_password">Confirm New Password</label>
                        <input id="confirm_password" name="confirm_password" type="password" minLength={8} required />
                      </div>
                      <div className="modal-actions">
                        <button
                          type="button"
                          className="proto-btn proto-btn--ghost proto-btn--sm"
                          onClick={() => setPasswordDialogOpen(false)}
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="proto-btn proto-btn--primary proto-btn--sm"
                          disabled={busyKey === "password"}
                        >
                          {busyKey === "password" ? "Saving..." : "Update Password"}
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      <SiteFooter />
    </main>
  );
}
