import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../app/auth";
import { addRecentSearch, readRecentSearches } from "../lib/recentSearches";
import { readPincodePreference, writePincodePreference } from "../lib/pincodePreference";
import { api } from "../services/api";
import { useSearchSuggestions } from "../hooks/useSearch";
import { formatProductLabel, formatVendorLabel } from "../lib/displayText";
import type { SearchSuggestion } from "../types/product";
import { CostiqoBrand } from "../components/CostiqoBrand";
import {
  HeroComparisonIllustration,
  PriceComparisonLineArt,
  MultiStoreLineArt,
  DeliveryTrustLineArt,
  VerifiedSavingsLineArt,
} from "../components/LineArtIllustrations";
import { SiteFooter } from "../components/SiteFooter";

function getGreeting() {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) {
    return "Good morning";
  }
  if (hour >= 12 && hour < 17) {
    return "Good afternoon";
  }
  return "Good evening";
}

function formatCurrency(value: number | null) {
  if (value === null) {
    return "Best price unavailable";
  }
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

const POPULAR_DISCOVERIES = [
  { label: "Raspberry Pi 4 Model B", query: "Raspberry Pi 4", tag: "Electronics" },
  { label: "Arduino Uno R3", query: "Arduino Uno", tag: "Microcontroller" },
  { label: "ESP32 Wi-Fi + BLE Dev Board", query: "ESP32", tag: "IoT & Dev" },
  { label: "12V 2A Power Adapter", query: "12V 2A Adapter", tag: "Power Supplies" },
  { label: "OLED Display 0.96 inch I2C", query: "OLED Display 0.96", tag: "Displays" },
  { label: "SG90 Micro Servo Motor", query: "SG90 Servo", tag: "Robotics" },
];

export function HomePage() {
  const { user, hasToken } = useAuth();
  const navigate = useNavigate();
  const savedPreference = readPincodePreference();
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [pincode, setPincode] = useState(savedPreference?.pincode ?? "600119");
  const [locationLabel, setLocationLabel] = useState(savedPreference?.location ?? "");
  const [recentSearches, setRecentSearches] = useState(() => readRecentSearches(user?.id));
  const [showPincodeEdit, setShowPincodeEdit] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [isSuggestionOpen, setIsSuggestionOpen] = useState(false);
  const searchWrapperRef = useRef<HTMLDivElement | null>(null);

  const firstName = useMemo(() => user?.name?.split(" ")[0] || "there", [user?.name]);

  useEffect(() => {
    void api.wakeBackend().catch(() => undefined);
  }, []);

  useEffect(() => {
    setRecentSearches(readRecentSearches(user?.id));
  }, [user?.id]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setDebouncedQuery(query);
    }, 180);
    return () => window.clearTimeout(timeout);
  }, [query]);

  const suggestionPincode = pincode.length === 6 ? pincode : "";
  const trimmedQuery = query.trim();
  const trimmedDebouncedQuery = debouncedQuery.trim();
  const queryIsAheadOfSuggestions =
    trimmedQuery.toLowerCase() !== trimmedDebouncedQuery.toLowerCase();

  const suggestionQuery = useSearchSuggestions(trimmedDebouncedQuery, {
    pincode: suggestionPincode || undefined,
    limit: 6,
  });
  const rawSuggestions = suggestionQuery.data?.results ?? [];
  const suggestions = queryIsAheadOfSuggestions ? [] : rawSuggestions;
  const showSuggestionPanel = isSuggestionOpen && trimmedQuery.length >= 2 && suggestions.length > 0;

  useEffect(() => {
    if (activeSuggestionIndex >= suggestions.length) {
      setActiveSuggestionIndex(-1);
    }
  }, [activeSuggestionIndex, suggestions.length]);

  function searchFor(nextQuery: string, pincodeOverride = pincode) {
    const trimmed = nextQuery.trim();
    if (!trimmed) {
      return;
    }
    setIsSuggestionOpen(false);
    setActiveSuggestionIndex(-1);
    const normalizedPincode = pincodeOverride.replace(/\D/g, "").slice(0, 6);
    setRecentSearches(
      addRecentSearch(user?.id, {
        query: trimmed,
        pincode: normalizedPincode,
      })
    );
    const params = new URLSearchParams({ q: trimmed });
    if (normalizedPincode.length === 6 && !normalizedPincode.startsWith("0")) {
      params.set("pincode", normalizedPincode);
    }
    navigate(`/search?${params.toString()}`);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (showSuggestionPanel && activeSuggestionIndex >= 0 && suggestions[activeSuggestionIndex]) {
      const selected = suggestions[activeSuggestionIndex].canonical_name;
      setQuery(selected);
      searchFor(selected);
      return;
    }
    searchFor(query);
  }

  function handleSuggestionSelect(suggestion: SearchSuggestion) {
    setQuery(suggestion.canonical_name);
    searchFor(suggestion.canonical_name);
  }

  function handleQueryKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!showSuggestionPanel || !suggestions.length) {
      if (event.key === "Escape") {
        setIsSuggestionOpen(false);
      }
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveSuggestionIndex((current) =>
        current >= suggestions.length - 1 ? 0 : current + 1
      );
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveSuggestionIndex((current) =>
        current <= 0 ? suggestions.length - 1 : current - 1
      );
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      setIsSuggestionOpen(false);
      setActiveSuggestionIndex(-1);
    }
  }

  async function handleApplyPincode() {
    if (!pincode) {
      setError("Please enter a pincode.");
      return;
    }
    setIsApplying(true);
    setError(null);
    try {
      const response = await api.verifyPincode(pincode);
      setPincode(response.pincode);
      setLocationLabel(response.location);
      writePincodePreference({
        pincode: response.pincode,
        location: response.location,
      });
      setShowPincodeEdit(false);
    } catch {
      setError("Enter a valid Indian pincode.");
    } finally {
      setIsApplying(false);
    }
  }

  return (
    <main className="proto-page search-page">
      {/* Polished Top Navigation Bar */}
      <header className="proto-topbar" role="banner">
        <div className="proto-topbar__inner">
          <CostiqoBrand />

          {/* Desktop Nav Links */}
          <nav className="proto-nav" aria-label="Primary navigation">
            <Link className="proto-nav__link proto-nav__link--active" to="/">
              Overview
            </Link>
            <Link className="proto-nav__link" to="/search?q=Raspberry+Pi+4">
              Explore Deals
            </Link>
            {/* {user?.role === "admin" && (
              <Link className="proto-nav__link" to="/admin">
                Admin Portal
              </Link>
            )} */}
          </nav>

          <div className="proto-topbar__actions">
            {/* Desktop Location Widget */}
            <div className="desktop-location-chip" onClick={() => setShowPincodeEdit(!showPincodeEdit)}>
              <svg viewBox="0 0 24 24" className="location-icon" aria-hidden="true">
                <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" />
              </svg>
              <span>{pincode || "Delivery Pincode"}</span>
              <span className="location-chevron">▾</span>
            </div>

            <Link className="proto-btn proto-btn--ghost proto-btn--sm" to={hasToken ? "/account" : "/login"}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="8" r="4" />
                <path d="M20 21a8 8 0 10-16 0" />
              </svg>
              <span>{hasToken ? "Account" : "Sign in"}</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Floating Pincode Dropdown overlay */}
      {showPincodeEdit && (
        <div className="pincode-dropdown-backdrop" onClick={() => setShowPincodeEdit(false)}>
          <div className="mobile-pincode-dropdown" onClick={(e) => e.stopPropagation()}>
            <input
              value={pincode}
              onChange={(e) => setPincode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="6-digit pincode"
              inputMode="numeric"
              maxLength={6}
              aria-label="Delivery pincode"
            />
            <button
              type="button"
              className="proto-btn proto-btn--primary proto-btn--sm"
              disabled={isApplying}
              onClick={handleApplyPincode}
            >
              {isApplying ? "..." : "Apply"}
            </button>
          </div>
        </div>
      )}

      {/* Hero Section with Line-Art Composition */}
      <section className="costiqo-hero" aria-labelledby="hero-title">
        <div className="costiqo-hero__layout">
          <div className="costiqo-hero__content">
            <div className="costiqo-hero__badge">
              <span className="badge-pulse" aria-hidden="true" />
              Multi-store real-time price intelligence
            </div>

            <h1 id="hero-title" className="costiqo-hero__title">
              Compare product prices across verified stores with total clarity.
            </h1>

            <p className="costiqo-hero__subtitle">
              {getGreeting()}, {firstName}. Discover the real landed cost for electronics, hardware, and components across Amazon, Flipkart, Croma, Robu, and local sellers before you buy.
            </p>

            {/* Main Interactive Search Box */}
            <div
              className="costiqo-hero__search-container"
              ref={searchWrapperRef}
              onBlur={() => {
                window.requestAnimationFrame(() => {
                  if (!searchWrapperRef.current?.contains(document.activeElement)) {
                    setIsSuggestionOpen(false);
                    setActiveSuggestionIndex(-1);
                  }
                });
              }}
            >
              <form className="search-box costiqo-hero__search-box" onSubmit={handleSubmit}>
                <div className="search-input-section">
                  <span className="search-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24">
                      <circle cx="11" cy="11" r="8" />
                      <line x1="21" y1="21" x2="16.65" y2="16.65" />
                    </svg>
                  </span>
                  <input
                    type="text"
                    placeholder="Search products (e.g. Raspberry Pi 4, Arduino, SSD)..."
                    value={query}
                    onChange={(e) => {
                      const next = e.target.value;
                      setQuery(next);
                      setIsSuggestionOpen(next.trim().length >= 2);
                      setActiveSuggestionIndex(-1);
                    }}
                    onFocus={() => {
                      if (trimmedQuery.length >= 2) {
                        setIsSuggestionOpen(true);
                      }
                    }}
                    onKeyDown={handleQueryKeyDown}
                    aria-label="Product search query"
                    aria-autocomplete="list"
                    aria-expanded={showSuggestionPanel}
                  />
                </div>

                <div className="search-divider" aria-hidden="true" />

                <div className="search-location-section">
                  <svg viewBox="0 0 24 24" className="location-pin-icon" aria-hidden="true">
                    <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" />
                  </svg>
                  <input
                    type="text"
                    placeholder="Pincode"
                    value={pincode}
                    onChange={(e) => setPincode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                    inputMode="numeric"
                    maxLength={6}
                    aria-label="Delivery pincode"
                  />
                </div>

                <button type="submit" className="proto-btn proto-btn--primary home-search-btn" aria-label="Search prices">
                  <svg viewBox="0 0 24 24" aria-hidden="true" className="home-search-btn__icon">
                    <circle cx="11" cy="11" r="8" />
                    <path d="m21 21-4.35-4.35" />
                  </svg>
                  <span className="home-search-btn__text">Search</span>
                </button>
              </form>

              {showSuggestionPanel && (
                <div className="search-suggestions hero-search-suggestions" role="listbox" aria-label="Suggested products">
                  {suggestions.map((suggestion, index) => {
                    const topDealers = suggestion.source_stores
                      .slice(0, 4)
                      .map((store) => formatVendorLabel(store.vendor))
                      .join(" · ");

                    return (
                      <button
                        type="button"
                        className={`search-suggestion ${index === activeSuggestionIndex ? "search-suggestion--active" : ""}`}
                        key={suggestion.id}
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => handleSuggestionSelect(suggestion)}
                      >
                        <span className="search-suggestion__leading search-suggestion__leading--icon" aria-hidden="true">
                          <svg viewBox="0 0 24 24">
                            <path
                              d="M10.5 4.5a6 6 0 1 0 0 12a6 6 0 0 0 0-12Zm0-2a8 8 0 1 1 4.95 14.285l4.132 4.133l-1.414 1.414l-4.133-4.132A8 8 0 0 1 10.5 2.5Z"
                              fill="currentColor"
                            />
                          </svg>
                        </span>
                        <span className="search-suggestion__body">
                          <span className="search-suggestion__title">{formatProductLabel(suggestion.canonical_name)}</span>
                          <span className="search-suggestion__subtitle">
                            {topDealers || `${suggestion.live_store_count} live dealers`}
                          </span>
                        </span>
                        <span className="search-suggestion__trailing">
                          <strong>{formatCurrency(suggestion.best_price)}</strong>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {error && <div className="error-message" style={{ color: "var(--proto-cream-deeper)", marginTop: "8px" }}>{error}</div>}

            {/* Popular Curated Searches */}
            <div className="hero-quick-tags" aria-label="Trending searches">
              <span className="hero-quick-tags__label">Trending:</span>
              <div className="hero-quick-tags__list">
                {POPULAR_DISCOVERIES.map((item) => (
                  <button
                    key={item.query}
                    type="button"
                    className="hero-quick-tag"
                    onClick={() => {
                      setQuery(item.query);
                      searchFor(item.query);
                    }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Hero Line-Art Showcase Visual */}
          <div className="costiqo-hero__visual" aria-hidden="true">
            <HeroComparisonIllustration />
          </div>
        </div>

        {/* Recent Searches Strip */}
        {recentSearches.length > 0 && (
          <div className="recent-searches costiqo-hero__recent">
            <div className="recent-searches__header">
              <h3>Recent Searches</h3>
              <span className="caption">Quickly resume your price lookups</span>
            </div>
            <div className="recent-list">
              {recentSearches.map((item, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="recent-item"
                  onClick={() => {
                    setQuery(item.query);
                    searchFor(item.query, item.pincode);
                  }}
                >
                  <span className="ri-icon">
                    <svg viewBox="0 0 24 24">
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="12 6 12 12 16 14" />
                    </svg>
                  </span>
                  <span className="ri-query">{item.query}</span>
                  {item.pincode ? <span className="ri-meta">{item.pincode}</span> : null}
                </button>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Feature & Value Section: Line-Art Storytelling */}
      <section className="costiqo-values" aria-labelledby="values-heading">
        <div className="costiqo-values__inner">
          <div className="section-intro">
            <span className="section-eyebrow">Why Costiqo</span>
            <h2 id="values-heading" className="section-title">
              Designed for transparent, confident purchasing decisions.
            </h2>
            <p className="section-desc">
              We monitor prices across India&apos;s leading e-commerce platforms and niche electronic stores to eliminate guesswork and hidden delivery costs.
            </p>
          </div>

          <div className="values-grid">
            <article className="value-card">
              <div className="value-card__art">
                <MultiStoreLineArt width={64} height={64} />
              </div>
              <h3 className="value-card__title">Multi-Store Crawl</h3>
              <p className="value-card__text">
                Live parallel scans across Amazon, Flipkart, Croma, Robu, Moglix, IBO, and specialized stores to find available stock.
              </p>
            </article>

            <article className="value-card">
              <div className="value-card__art">
                <PriceComparisonLineArt width={64} height={64} />
              </div>
              <h3 className="value-card__title">True Landed Price</h3>
              <p className="value-card__text">
                Automatic calculation of base prices, taxes, and shipping fees so you always see the true out-of-pocket cost.
              </p>
            </article>

            <article className="value-card">
              <div className="value-card__art">
                <DeliveryTrustLineArt width={64} height={64} />
              </div>
              <h3 className="value-card__title">Location-Aware ETAs</h3>
              <p className="value-card__text">
                Pinpoint delivery windows for your exact 6-digit pincode to compare speed versus savings across different sellers.
              </p>
            </article>

            <article className="value-card">
              <div className="value-card__art">
                <VerifiedSavingsLineArt width={64} height={64} />
              </div>
              <h3 className="value-card__title">Verified Live Offers</h3>
              <p className="value-card__text">
                Automated offer verification checks seller links directly, protecting you from stale cache data or out-of-stock listings.
              </p>
            </article>
          </div>
        </div>
      </section>

      {/* SEO & Informational Content Showcase */}
      <section className="costiqo-seo-guide" aria-label="Smart Shopping Guide">
        <div className="costiqo-seo-guide__inner">
          <div className="seo-guide-col">
            <h3>Save on Electronics & Hardware</h3>
            <p>
              Component and gadget pricing fluctuates daily across retail networks. Costiqo organizes listings by model number, canonical product identity, and specifications so you never overpay for developer kits, smart devices, or accessories.
            </p>
          </div>
          <div className="seo-guide-col">
            <h3>Verified Procurement & Offline Quotes</h3>
            <p>
              Whether you are an individual hobbyist or an institutional procurement buyer, Costiqo blends public online prices with recorded offline supplier quotes for a complete benchmark view.
            </p>
          </div>
        </div>
      </section>

      {/* Reusable Comprehensive Footer */}
      <SiteFooter />
    </main>
  );
}
