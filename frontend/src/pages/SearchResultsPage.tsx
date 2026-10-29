import { FormEvent, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { useAuth } from "../app/auth";
import { CostiqoBrand } from "../components/CostiqoBrand";
import { ErrorState } from "../components/ErrorState";
import { OfferSearchLoading } from "../components/OfferSearchLoading";
import { EmptySearchLineArt } from "../components/LineArtIllustrations";
import { SiteFooter } from "../components/SiteFooter";
import { useComparison } from "../hooks/useSearch";
import { formatProductLabel, formatVendorLabel } from "../lib/displayText";
import { addRecentSearch } from "../lib/recentSearches";
import { api } from "../services/api";
import type { ComparisonItem } from "../types/product";

type SortMode = "low" | "high";
const ALL_VENDOR_FILTER = "all";

function createProgressId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `progress-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function formatCurrency(value: number | null) {
  if (value === null) {
    return "N/A";
  }

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function getHostLabel(url: string) {
  if (url.startsWith("#")) {
    return "Offline quote";
  }
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "Product link";
  }
}

function formatReadableLabel(value: string | null | undefined) {
  const normalized = (value ?? "").replace(/[_-]+/g, " ").trim();
  if (!normalized) {
    return "";
  }
  return normalized.replace(/\w\S*/g, (word) => word[0].toUpperCase() + word.slice(1).toLowerCase());
}

function isOfferInStock(result: ComparisonItem) {
  const status = result.availability_status.toLowerCase();
  return !status.includes("out") && !status.includes("unavailable");
}

function getAvailabilityLabel(result: ComparisonItem) {
  if (isOfferInStock(result)) {
    return "In stock";
  }
  return formatReadableLabel(result.availability_status) || "Check stock";
}

function VendorLogo({
  vendor,
  productUrl,
}: {
  vendor: string;
  productUrl: string;
}) {
  const vendorLabel = formatVendorLabel(vendor);
  const logoUrl = (() => {
    if (productUrl && !productUrl.startsWith("#")) {
      try {
        return `https://www.google.com/s2/favicons?domain=${new URL(productUrl).hostname}&sz=128`;
      } catch {
        return null;
      }
    }
    return null;
  })();

  if (logoUrl) {
    return (
      <div className="offer-card__vendor-logo">
        <img src={logoUrl} alt={`${vendorLabel} logo`} />
      </div>
    );
  }

  return (
    <div className="offer-card__vendor-logo offer-card__vendor-logo--fallback" aria-hidden="true">
      {vendorLabel.slice(0, 2).toUpperCase()}
    </div>
  );
}

export function SearchResultsPage() {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const pincode = searchParams.get("pincode") ?? "600119";
  const searchLocation = searchParams.get("location") ?? "";
  const validPincode = pincode.length === 6 && !pincode.startsWith("0") ? pincode : "";
  const pincodeWarning = pincode && !validPincode
    ? "Enter a valid 6-digit pincode to personalize delivery. Showing all-location offers for now."
    : "";
  const [draftQuery, setDraftQuery] = useState(query);
  const [draftPincode, setDraftPincode] = useState(pincode);
  const [sortMode, setSortMode] = useState<SortMode>("low");
  const [saveStatus, setSaveStatus] = useState("");
  const [savingOfferKey, setSavingOfferKey] = useState<string | null>(null);
  const [liveOfferCount, setLiveOfferCount] = useState(0);

  const savedProductsQuery = useQuery({
    queryKey: ["saved-products"],
    queryFn: api.fetchSavedProducts,
    enabled: isAuthenticated,
    staleTime: 30_000,
  });

  const savedSearchesQuery = useQuery({
    queryKey: ["saved-searches"],
    queryFn: api.fetchSavedSearches,
    enabled: isAuthenticated,
    staleTime: 30_000,
  });

  const savedProductMap = useMemo(() => {
    const map = new Map<string, number>();
    (savedProductsQuery.data ?? []).forEach((item) => {
      map.set(item.product_url, item.id);
    });
    return map;
  }, [savedProductsQuery.data]);

  const savedSearchMap = useMemo(() => {
    const map = new Map<string, number>();
    (savedSearchesQuery.data ?? []).forEach((item) => {
      map.set(item.query.trim().toLowerCase(), item.id);
    });
    return map;
  }, [savedSearchesQuery.data]);

  const [optimisticSavedUrls, setOptimisticSavedUrls] = useState<Map<string, boolean>>(new Map());
  const [optimisticSavedSearches, setOptimisticSavedSearches] = useState<Map<string, boolean>>(new Map());
  const [toast, setToast] = useState<{ message: string; action?: { label: string; to: string } } | null>(null);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  function isOfferSaved(productUrl: string) {
    if (optimisticSavedUrls.has(productUrl)) {
      return Boolean(optimisticSavedUrls.get(productUrl));
    }
    return savedProductMap.has(productUrl);
  }

  const normalizedCurrentQuery = query.trim().toLowerCase();
  const isCurrentSearchSaved = optimisticSavedSearches.has(normalizedCurrentQuery)
    ? Boolean(optimisticSavedSearches.get(normalizedCurrentQuery))
    : savedSearchMap.has(normalizedCurrentQuery);
  const [showSortDropdown, setShowSortDropdown] = useState(false);
  const [selectedVendor, setSelectedVendor] = useState(ALL_VENDOR_FILTER);
  const [trustedOnly, setTrustedOnly] = useState(false);
  const [inStockOnly, setInStockOnly] = useState(false);
  const [maxPrice, setMaxPrice] = useState<number | null>(null);
  const progressId = useMemo(
    () => (query.trim() ? createProgressId() : ""),
    [query, searchLocation, validPincode],
  );
  const comparisonQuery = useComparison(query, {
    location: searchLocation,
    pincode: validPincode,
    rankingMode: "recommended",
    progressId,
  });
  const comparison = comparisonQuery.data;
  const isLoading = comparisonQuery.isLoading || comparisonQuery.isFetching;
  const loadingActive = Boolean(query && isLoading);
  const baseResults = useMemo(() => comparison?.results ?? [], [comparison?.results]);
  const vendorSummaries = useMemo(() => {
    const vendorCounts = new Map<string, number>();
    baseResults.forEach((result) => {
      vendorCounts.set(result.vendor, (vendorCounts.get(result.vendor) ?? 0) + 1);
    });
    return Array.from(vendorCounts, ([vendor, count]) => ({
      vendor,
      count,
      label: formatVendorLabel(vendor),
    })).sort((a, b) => a.label.localeCompare(b.label));
  }, [baseResults]);
  const priceBounds = useMemo(() => {
    if (!baseResults.length) {
      return { min: 0, max: 0 };
    }
    const prices = baseResults.map((result) => result.landed_price);
    return {
      min: Math.floor(Math.min(...prices)),
      max: Math.ceil(Math.max(...prices)),
    };
  }, [baseResults]);
  const priceCap = maxPrice ?? priceBounds.max;
  const filteredResults = useMemo(() => {
    return baseResults.filter((result) => {
      if (selectedVendor !== ALL_VENDOR_FILTER && result.vendor !== selectedVendor) {
        return false;
      }
      if (trustedOnly && !result.vendor_is_trusted) {
        return false;
      }
      if (inStockOnly && !isOfferInStock(result)) {
        return false;
      }
      if (priceBounds.max > 0 && result.landed_price > priceCap) {
        return false;
      }
      return true;
    });
  }, [baseResults, inStockOnly, priceBounds.max, priceCap, selectedVendor, trustedOnly]);
  const results = useMemo(() => {
    return [...filteredResults].sort((a, b) =>
      sortMode === "low" ? a.landed_price - b.landed_price : b.landed_price - a.landed_price,
    );
  }, [filteredResults, sortMode]);
  const uniqueStoreCount = new Set(results.map((result) => result.vendor)).size;
  const displayQuery = query.trim() || "this product";
  const cheapestOffer = useMemo(() => {
    if (!baseResults.length) {
      return null;
    }
    return [...baseResults].sort((a, b) => a.landed_price - b.landed_price)[0];
  }, [baseResults]);
  const activeFilterCount = [
    selectedVendor !== ALL_VENDOR_FILTER,
    trustedOnly,
    inStockOnly,
    priceBounds.max > 0 && priceCap < priceBounds.max,
  ].filter(Boolean).length;

  useEffect(() => {
    void api.wakeBackend().catch(() => undefined);
  }, []);

  useEffect(() => {
    setLiveOfferCount(0);
  }, [progressId]);

  useEffect(() => {
    setSelectedVendor(ALL_VENDOR_FILTER);
    setTrustedOnly(false);
    setInStockOnly(false);
    setMaxPrice(priceBounds.max > 0 ? priceBounds.max : null);
  }, [priceBounds.max, query, validPincode]);

  useEffect(() => {
    if (!loadingActive || !progressId) {
      return undefined;
    }

    let cancelled = false;
    const refreshProgress = async () => {
      try {
        const progress = await api.fetchComparisonProgress(progressId);
        if (!cancelled) {
          setLiveOfferCount(progress.offer_count);
        }
      } catch {
        if (!cancelled) {
          setLiveOfferCount((current) => current);
        }
      }
    };

    void refreshProgress();
    const interval = window.setInterval(() => {
      void refreshProgress();
    }, 350);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [loadingActive, progressId]);

  useEffect(() => {
    setDraftQuery(query);
    setDraftPincode(pincode);
  }, [query, pincode]);

  useEffect(() => {
    if (query.trim()) {
      addRecentSearch(user?.id, { query, pincode });
    }
  }, [pincode, query, user?.id]);

  function runSearch(nextQuery: string, nextPincode: string) {
    const trimmedQuery = nextQuery.trim();
    if (!trimmedQuery) {
      return;
    }

    const normalizedPincode = nextPincode.replace(/\D/g, "").slice(0, 6);
    addRecentSearch(user?.id, { query: trimmedQuery, pincode: normalizedPincode });
    setSaveStatus("");
    setSearchParams({
      q: trimmedQuery,
      ...(normalizedPincode.length === 6 && !normalizedPincode.startsWith("0")
        ? { pincode: normalizedPincode }
        : {}),
    });
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    runSearch(draftQuery, draftPincode);
  }

  async function handleBookmarkOffer(result: ComparisonItem) {
    if (result.product_url.startsWith("#")) {
      setToast({ message: "Offline quotes cannot be bookmarked as product links." });
      return;
    }

    if (!isAuthenticated) {
      setToast({
        message: "Sign in to save bookmarks to your account.",
        action: {
          label: "Sign In →",
          to: `/login?next=${encodeURIComponent(location.pathname + location.search)}`,
        },
      });
      return;
    }

    const key = `${result.vendor_product_id}-${result.product_url}`;
    const currentlySaved = isOfferSaved(result.product_url);
    const existingId = savedProductMap.get(result.product_url);

    setSavingOfferKey(key);
    // Instant optimistic UI toggle
    setOptimisticSavedUrls((prev) => new Map(prev).set(result.product_url, !currentlySaved));

    try {
      if (currentlySaved && existingId) {
        await api.removeSavedProduct(existingId);
        await queryClient.invalidateQueries({ queryKey: ["saved-products"] });
        setToast({ message: "Bookmark removed from account." });
        setSaveStatus("");
      } else {
        await api.saveProduct({
          product_name: formatProductLabel(result.product_name),
          product_url: result.product_url,
        });
        await queryClient.invalidateQueries({ queryKey: ["saved-products"] });
        setToast({
          message: "✓ Offer saved to your Bookmarks!",
          action: { label: "View Bookmarks →", to: "/account" },
        });
        setSaveStatus("Bookmark saved to your account.");
      }
    } catch {
      // Revert optimistic update
      setOptimisticSavedUrls((prev) => new Map(prev).set(result.product_url, currentlySaved));
      setToast({ message: "Could not update bookmark. Please try again." });
    } finally {
      setSavingOfferKey(null);
    }
  }

  async function handleToggleSaveSearch() {
    if (!query.trim()) return;
    if (!isAuthenticated) {
      setToast({
        message: "Sign in to save searches to your account.",
        action: {
          label: "Sign In →",
          to: `/login?next=${encodeURIComponent(location.pathname + location.search)}`,
        },
      });
      return;
    }

    const currentlySaved = isCurrentSearchSaved;
    const existingId = savedSearchMap.get(normalizedCurrentQuery);
    setOptimisticSavedSearches((prev) => new Map(prev).set(normalizedCurrentQuery, !currentlySaved));

    try {
      if (currentlySaved && existingId) {
        await api.removeSavedSearch(existingId);
        await queryClient.invalidateQueries({ queryKey: ["saved-searches"] });
        setToast({ message: "Search removed from account." });
      } else {
        await api.saveSearch({
          query: query.trim(),
          pincode: validPincode || undefined,
          location: searchLocation || undefined,
        });
        await queryClient.invalidateQueries({ queryKey: ["saved-searches"] });
        setToast({
          message: "✓ Search saved to your account!",
          action: { label: "View Searches →", to: "/account" },
        });
      }
    } catch {
      setOptimisticSavedSearches((prev) => new Map(prev).set(normalizedCurrentQuery, currentlySaved));
      setToast({ message: "Could not save search. Please try again." });
    }
  }

  function clearFilters() {
    setSelectedVendor(ALL_VENDOR_FILTER);
    setTrustedOnly(false);
    setInStockOnly(false);
    setMaxPrice(priceBounds.max > 0 ? priceBounds.max : null);
  }

  return (
    <main className="proto-page products-page">
      <OfferSearchLoading
        active={loadingActive}
        offerCount={liveOfferCount}
      />

      {/* Modern Top Navigation Bar */}
      <header className="results-topbar" role="banner">
        <CostiqoBrand />
        
        <form className="results-search-widget" onSubmit={handleSubmit} role="search">
          <div className="results-search-input-wrapper">
            <span aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.35-4.35" />
              </svg>
            </span>
            <input
              value={draftQuery}
              onChange={(event) => setDraftQuery(event.target.value)}
              placeholder="Search product by name..."
              aria-label="Search product by name"
            />
          </div>
          <div className="results-search-location">
            <input
              value={draftPincode}
              onChange={(event) => setDraftPincode(event.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="Pincode"
              inputMode="numeric"
              aria-label="Delivery pincode"
            />
          </div>
          <button className="proto-btn proto-btn--primary proto-btn--sm results-search-btn" type="submit" aria-label="Search">
            <svg viewBox="0 0 24 24" aria-hidden="true" className="results-search-btn__icon">
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            <span className="results-search-btn__text">Search</span>
          </button>
        </form>

        <Link className="results-account-btn" to="/account" title="Account profile & bookmarks">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="8" r="4" />
            <path d="M20 21a8 8 0 1 0-16 0" />
          </svg>
        </Link>
      </header>

      {comparisonQuery.isError ? (
        <ErrorState
          message="We could not load offers right now."
          detail="Target vendors may be undergoing maintenance or the network timed out."
          actionLabel="Retry"
          onAction={() => comparisonQuery.refetch()}
        />
      ) : null}

      {query && !comparison && isLoading && !comparisonQuery.isError ? (
        <section className="results-skeleton-shell" aria-label="Loading offers">
          <div style={{ marginBottom: "20px" }}>
            <div className="skeleton-box" style={{ width: "240px", height: "32px", marginBottom: "10px" }} />
            <div className="skeleton-box" style={{ width: "160px", height: "18px" }} />
          </div>
          <div style={{ display: "grid", gap: "14px" }}>
            {[1, 2, 3].map((n) => (
              <div className="skeleton-offer-card" key={n}>
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <div className="skeleton-box" style={{ width: "48px", height: "48px", borderRadius: "12px" }} />
                  <div className="skeleton-box" style={{ width: "90px", height: "18px" }} />
                </div>
                <div>
                  <div className="skeleton-box" style={{ width: "85%", height: "20px", marginBottom: "8px" }} />
                  <div className="skeleton-box" style={{ width: "45%", height: "14px" }} />
                </div>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "8px" }}>
                  <div className="skeleton-box" style={{ width: "100px", height: "26px" }} />
                  <div className="skeleton-box" style={{ width: "120px", height: "38px", borderRadius: "8px" }} />
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {comparison && baseResults.length ? (
        <>
          {/* Results Summary & Header */}
          <section className="results-bar" aria-label="Search summary">
            <div className="results-bar__copy">
              <span className="results-eyebrow">Verified Marketplace Scan</span>
              <div className="results-title-row">
                <h1>Best offers for &quot;{displayQuery}&quot;</h1>
                {query.trim() ? (
                  <button
                    type="button"
                    className={`save-search-pill ${isCurrentSearchSaved ? "save-search-pill--saved" : ""}`}
                    onClick={handleToggleSaveSearch}
                    title={isCurrentSearchSaved ? "Search saved to account (click to remove)" : "Save this search query to account"}
                    aria-pressed={isCurrentSearchSaved}
                  >
                    <svg viewBox="0 0 24 24" width="14" height="14" fill={isCurrentSearchSaved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <path d="M19 21 12 17 5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
                    </svg>
                    <span>{isCurrentSearchSaved ? "Search Saved" : "Save Search"}</span>
                  </button>
                ) : null}
              </div>
              <p className="caption">
                {results.length === baseResults.length ? results.length : `${results.length} of ${baseResults.length}`} offers from{" "}
                {uniqueStoreCount} {uniqueStoreCount === 1 ? "store" : "stores"}
                {validPincode ? ` for pincode ${validPincode}` : " nationwide"}
              </p>
              <div className="results-insights" aria-label="Search metrics">
                <span>
                  <strong>{cheapestOffer ? formatCurrency(cheapestOffer.landed_price) : "N/A"}</strong>
                  Lowest landed price
                </span>
                <span>
                  <strong>{comparison.benchmark ? formatCurrency(comparison.benchmark.median_price) : "N/A"}</strong>
                  Market median
                </span>
                <span>
                  <strong>{comparison.decision_summary?.location_context_label ?? (validPincode || "All India")}</strong>
                  Delivery context
                </span>
              </div>
              {pincodeWarning ? <p className="small-copy" style={{ color: "var(--proto-cream-accent)" }}>{pincodeWarning}</p> : null}
              {saveStatus ? <p className="small-copy" style={{ color: "var(--proto-success)" }}>{saveStatus}</p> : null}
            </div>

            {/* Sort Dropdown */}
            <div className="filter-wrapper">
              <button
                type="button"
                className="filter-toggle-btn"
                aria-haspopup="menu"
                aria-expanded={showSortDropdown}
                onClick={() => setShowSortDropdown((isOpen) => !isOpen)}
              >
                Sort: {sortMode === "low" ? "Price: Low to High" : "Price: High to Low"} ▾
              </button>
              
              <div className={`filter-options ${showSortDropdown ? "open" : ""}`} role="menu">
                <button
                  type="button"
                  className={`filter-btn ${sortMode === "low" ? "active" : ""}`}
                  role="menuitemradio"
                  aria-checked={sortMode === "low"}
                  onClick={() => {
                    setSortMode("low");
                    setShowSortDropdown(false);
                  }}
                >
                  Price: Low to High
                </button>
                <button
                  type="button"
                  className={`filter-btn ${sortMode === "high" ? "active" : ""}`}
                  role="menuitemradio"
                  aria-checked={sortMode === "high"}
                  onClick={() => {
                    setSortMode("high");
                    setShowSortDropdown(false);
                  }}
                >
                  Price: High to Low
                </button>
              </div>
            </div>
          </section>

          {/* Mobile Filter Strip */}
          <section className="mobile-filter-strip" aria-label="Mobile result filters">
            <div className="mobile-filter-strip__header">
              <span>{activeFilterCount ? `${activeFilterCount} active filters` : "Refine results"}</span>
              {activeFilterCount ? (
                <button type="button" onClick={clearFilters}>
                  Reset
                </button>
              ) : null}
            </div>

            <div className="mobile-filter-scroll" role="group" aria-label="Stores">
              <button
                type="button"
                className={`mobile-filter-chip ${selectedVendor === ALL_VENDOR_FILTER ? "active" : ""}`}
                aria-pressed={selectedVendor === ALL_VENDOR_FILTER}
                onClick={() => setSelectedVendor(ALL_VENDOR_FILTER)}
              >
                All stores
                <strong>{baseResults.length}</strong>
              </button>
              {vendorSummaries.map((vendor) => (
                <button
                  type="button"
                  className={`mobile-filter-chip ${selectedVendor === vendor.vendor ? "active" : ""}`}
                  aria-pressed={selectedVendor === vendor.vendor}
                  key={vendor.vendor}
                  onClick={() => setSelectedVendor(vendor.vendor)}
                >
                  {vendor.label}
                  <strong>{vendor.count}</strong>
                </button>
              ))}
            </div>

            <div className="mobile-filter-scroll" role="group" aria-label="Quick filters">
              <button
                type="button"
                className={`mobile-filter-chip mobile-filter-chip--toggle ${inStockOnly ? "active" : ""}`}
                aria-pressed={inStockOnly}
                onClick={() => setInStockOnly((current) => !current)}
              >
                In stock
              </button>
              <button
                type="button"
                className={`mobile-filter-chip mobile-filter-chip--toggle ${trustedOnly ? "active" : ""}`}
                aria-pressed={trustedOnly}
                onClick={() => setTrustedOnly((current) => !current)}
              >
                Trusted sellers
              </button>
            </div>

            {priceBounds.max > priceBounds.min ? (
              <label className="mobile-price-filter">
                <span>
                  Price cap: <strong>{formatCurrency(priceCap)}</strong>
                </span>
                <input
                  type="range"
                  min={priceBounds.min}
                  max={priceBounds.max}
                  value={priceCap}
                  onChange={(event) => setMaxPrice(Number(event.target.value))}
                />
              </label>
            ) : null}
          </section>

          {/* Desktop Filter Sidebar + Offers Layout */}
          <section className="results-commerce-shell">
            <aside className="results-filter-rail" aria-label="Search filters">
              <div className="filter-rail__header">
                <div>
                  <span>Refine Results</span>
                  <strong>{activeFilterCount ? `${activeFilterCount} active` : "All offers"}</strong>
                </div>
                {activeFilterCount > 0 && (
                  <button type="button" onClick={clearFilters}>
                    Reset
                  </button>
                )}
              </div>

              <div className="filter-rail__market">
                <div>
                  <span>Lowest</span>
                  <strong>{cheapestOffer ? formatCurrency(cheapestOffer.landed_price) : "N/A"}</strong>
                </div>
                <div>
                  <span>Stores</span>
                  <strong>{vendorSummaries.length}</strong>
                </div>
              </div>

              <div className="filter-rail__section">
                <span className="filter-rail__label">Stores</span>
                <button
                  type="button"
                  className={`filter-rail__option ${selectedVendor === ALL_VENDOR_FILTER ? "active" : ""}`}
                  onClick={() => setSelectedVendor(ALL_VENDOR_FILTER)}
                >
                  <span>All stores</span>
                  <strong>{baseResults.length}</strong>
                </button>
                {vendorSummaries.map((vendor) => (
                  <button
                    type="button"
                    className={`filter-rail__option ${selectedVendor === vendor.vendor ? "active" : ""}`}
                    key={vendor.vendor}
                    onClick={() => setSelectedVendor(vendor.vendor)}
                  >
                    <span>{vendor.label}</span>
                    <strong>{vendor.count}</strong>
                  </button>
                ))}
              </div>

              {priceBounds.max > 0 ? (
                <div className="filter-rail__section">
                  <label className="filter-rail__range">
                    <span>
                      Price cap: <strong>{formatCurrency(priceCap)}</strong>
                    </span>
                    <input
                      type="range"
                      min={priceBounds.min}
                      max={priceBounds.max}
                      value={priceCap}
                      onChange={(event) => setMaxPrice(Number(event.target.value))}
                    />
                  </label>
                </div>
              ) : null}

              <div className="filter-rail__section">
                <span className="filter-rail__label">Quick Filters</span>
                <label className="filter-rail__check">
                  <input
                    type="checkbox"
                    checked={inStockOnly}
                    onChange={(event) => setInStockOnly(event.target.checked)}
                  />
                  <span>In stock only</span>
                </label>
                <label className="filter-rail__check">
                  <input
                    type="checkbox"
                    checked={trustedOnly}
                    onChange={(event) => setTrustedOnly(event.target.checked)}
                  />
                  <span>Trusted sellers</span>
                </label>
              </div>
            </aside>

            {/* Offer Cards Container */}
            <section className="offers-container" aria-label="Offer results">
              <div className="offers-grid">
                {results.map((result, index) => {
                  const productName = formatProductLabel(result.product_name);
                  const offerKey = `${result.vendor_product_id}-${result.product_url}`;
                  const isLowestPrice =
                    cheapestOffer !== null &&
                    cheapestOffer.vendor_product_id === result.vendor_product_id &&
                    cheapestOffer.product_url === result.product_url;
                  return (
                    <article
                      className={`offer-card ${isLowestPrice ? "offer-card--top-deal" : ""}`}
                      key={offerKey}
                      style={{ animationDelay: `${Math.min(index * 0.04, 0.4)}s` }}
                    >
                      {isLowestPrice ? <span className="offer-card__ribbon">Lowest Price</span> : null}
                      <div className="offer-card__vendor-cluster">
                        <VendorLogo vendor={result.vendor} productUrl={result.product_url} />
                        <div>
                          <div className="offer-card__vendor-name">{formatVendorLabel(result.vendor)}</div>
                          <div className="offer-card__link-host">{getHostLabel(result.product_url)}</div>
                        </div>
                      </div>

                      <div className="offer-card__info">
                        <h2 className="offer-card__product-name">{productName}</h2>
                        <div className="offer-card__badges" aria-label="Offer highlights">
                          <span className={`offer-badge ${isOfferInStock(result) ? "offer-badge--success" : "offer-badge--muted"}`}>
                            {getAvailabilityLabel(result)}
                          </span>
                          {result.vendor_is_trusted ? <span className="offer-badge offer-badge--trusted">Trusted</span> : null}
                          {result.estimated_delivery_days !== null && (
                            <span className="offer-badge offer-badge--shipping">
                              {result.estimated_delivery_days <= 1 ? "1-day delivery" : `${result.estimated_delivery_days} days ETA`}
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="offer-card__price-section">
                        <span className="offer-card__price-label">Landed Price</span>
                        <div className="offer-card__price">{formatCurrency(result.landed_price)}</div>
                        {result.shipping_cost && result.shipping_cost > 0 ? (
                          <span className="offer-card__shipping-note">+ {formatCurrency(result.shipping_cost)} shipping</span>
                        ) : (
                          <span className="offer-card__shipping-note offer-card__shipping-note--free">Free delivery</span>
                        )}

                        <div className="offer-card__actions">
                          {(() => {
                            const isSaved = isOfferSaved(result.product_url);
                            return (
                              <button
                                type="button"
                                className={`offer-card__save-btn ${isSaved ? "offer-card__save-btn--saved" : ""}`}
                                disabled={savingOfferKey === offerKey || result.product_url.startsWith("#")}
                                aria-label={isSaved ? `Remove bookmark for ${productName}` : `Bookmark ${productName}`}
                                aria-pressed={isSaved}
                                title={isSaved ? "Saved to Bookmarks (click to remove)" : "Save to Bookmarks"}
                                onClick={() => handleBookmarkOffer(result)}
                              >
                                <svg viewBox="0 0 24 24" aria-hidden="true" fill={isSaved ? "currentColor" : "none"}>
                                  <path d="M19 21 12 17 5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
                                </svg>
                              </button>
                            );
                          })()}
                          {result.product_url.startsWith("#") ? (
                            <span className="offer-card__open-btn offer-card__open-btn--disabled">Offline quote</span>
                          ) : (
                            <a
                              className="offer-card__open-btn"
                              href={result.product_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              <span>Open site</span>
                              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                                <path d="M7 17L17 7M17 7H7M17 7V17" />
                              </svg>
                            </a>
                          )}
                        </div>
                      </div>
                    </article>
                  );
                })}
                {!results.length ? (
                  <div className="offer-filter-empty">
                    <EmptySearchLineArt width={120} height={120} />
                    <strong>No offers match these filters.</strong>
                    <p className="small-copy">Clear a filter or raise the price cap to see more live results.</p>
                    <button type="button" className="proto-btn proto-btn--outline proto-btn--sm" onClick={clearFilters}>
                      Clear filters
                    </button>
                  </div>
                ) : null}
              </div>
            </section>
          </section>
        </>
      ) : null}

      {comparison && !baseResults.length && !comparisonQuery.isError ? (
        <section className="empty-state">
          <EmptySearchLineArt width={140} height={140} />
          <h2>No live offers matched &quot;{displayQuery}&quot;</h2>
          <p className="small-copy">Try searching for an exact product name, brand, or model number (e.g. Raspberry Pi 4, Arduino Uno, or Kingston SSD).</p>
        </section>
      ) : null}

      {!query ? (
        <section className="empty-state">
          <EmptySearchLineArt width={140} height={140} />
          <h2>Search for a product to compare live offers</h2>
          <p className="small-copy">Enter a product title or component model above to scan prices across verified Indian retailers.</p>
        </section>
      ) : null}

      {toast ? (
        <aside className="costiqo-toast-floating" role="status" aria-live="polite">
          <div className="costiqo-toast-content">
            <span className="costiqo-toast-icon">✓</span>
            <span className="costiqo-toast-text">{toast.message}</span>
            {toast.action ? (
              <Link to={toast.action.to} className="costiqo-toast-action">
                {toast.action.label}
              </Link>
            ) : null}
          </div>
        </aside>
      ) : null}

      <SiteFooter />
    </main>
  );
}
