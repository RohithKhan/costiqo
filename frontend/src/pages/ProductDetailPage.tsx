import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";

import { useAuth } from "../app/auth";
import { ComparisonToolbar } from "../components/ComparisonToolbar";
import { ComparisonTable } from "../components/ComparisonTable";
import { CostiqoBrand } from "../components/CostiqoBrand";
import { DecisionSummary } from "../components/DecisionSummary";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PriceTrendChart } from "../components/PriceTrendChart";
import { SentimentSummary } from "../components/SentimentSummary";
import { SiteFooter } from "../components/SiteFooter";
import { downloadComparisonCsv } from "../lib/comparisonExport";
import { formatProductLabel, formatVendorLabel } from "../lib/displayText";
import { comparisonRankingLabel, normalizeComparisonRankingMode } from "../lib/comparisonRanking";
import { formatPriceConfidence, formatVerificationStatus } from "../lib/priceVerification";
import { api } from "../services/api";
import { useProductHistory } from "../hooks/useProductHistory";

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

export function ProductDetailPage() {
  const { hasToken, isAuthenticated } = useAuth();
  const location = useLocation();
  const queryClient = useQueryClient();
  const params = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [saveStatus, setSaveStatus] = useState("");
  const [accountAction, setAccountAction] = useState<"save" | null>(null);
  const [toast, setToast] = useState<{ message: string; action?: { label: string; to: string } } | null>(null);
  const [optimisticSaved, setOptimisticSaved] = useState<boolean | null>(null);
  const productId = Number(params.productId);
  const filterLocation = searchParams.get("location") ?? undefined;
  const pincode = searchParams.get("pincode") ?? undefined;
  const rankingMode = normalizeComparisonRankingMode(searchParams.get("ranking"));

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const savedProductsQuery = useQuery({
    queryKey: ["saved-products"],
    queryFn: api.fetchSavedProducts,
    enabled: isAuthenticated,
    staleTime: 30_000,
  });

  const productQuery = useQuery({
    queryKey: ["product", productId, filterLocation, pincode, rankingMode],
    queryFn: () => api.fetchProductDetail(productId, { location: filterLocation, pincode, rankingMode }),
    enabled: Number.isFinite(productId),
  });
  const historyQuery = useProductHistory(Number.isFinite(productId) ? productId : null);
  const reviewsQuery = useQuery({
    queryKey: ["reviews", productId],
    queryFn: () => api.fetchReviews(productId),
    enabled: Number.isFinite(productId),
  });
  const sentimentQuery = useQuery({
    queryKey: ["sentiment", productId],
    queryFn: () => api.fetchSentiment(productId),
    enabled: Number.isFinite(productId),
  });

  const targetProductUrl = productQuery.data?.comparison.best_option?.product_url ?? productQuery.data?.best_product_url;
  const displayProductName = productQuery.data ? formatProductLabel(productQuery.data.canonical_name) : "";

  const existingSavedProduct = useMemo(() => {
    if (!savedProductsQuery.data || !productQuery.data) return null;
    return savedProductsQuery.data.find(
      (p) =>
        (targetProductUrl && p.product_url === targetProductUrl) ||
        (displayProductName && p.product_name.toLowerCase() === displayProductName.toLowerCase())
    );
  }, [savedProductsQuery.data, productQuery.data, targetProductUrl, displayProductName]);

  if (
    productQuery.isLoading ||
    historyQuery.isLoading ||
    reviewsQuery.isLoading ||
    sentimentQuery.isLoading
  ) {
    return <LoadingState message="Loading live product comparison..." />;
  }

  if (productQuery.isError || !productQuery.data) {
    return <ErrorState message="Product detail could not be loaded." />;
  }

  const product = productQuery.data;
  const comparison = product.comparison;
  const bestOption = comparison.best_option;
  const bestResult = comparison.results.find(
    (result) => result.vendor_product_id === bestOption?.vendor_product_id,
  ) ?? null;
  const offlineQuotes = product.offline_quotes;
  const latestPurchase = comparison.latest_purchase;
  const bestVendorLabel = bestOption?.vendor
    ? formatVendorLabel(bestOption.vendor)
    : product.best_vendor
      ? formatVendorLabel(product.best_vendor)
      : "N/A";

  const isSaved = optimisticSaved !== null ? optimisticSaved : Boolean(existingSavedProduct);

  async function handleSaveProduct() {
    if (!isAuthenticated) {
      setToast({
        message: "Sign in before saving products to your account.",
        action: {
          label: "Sign In →",
          to: `/login?next=${encodeURIComponent(location.pathname + location.search)}`,
        },
      });
      return;
    }
    const productUrl = targetProductUrl;
    if (!productUrl) {
      setToast({ message: "No product link is available to bookmark." });
      return;
    }

    setAccountAction("save");
    const willBeSaved = !isSaved;
    setOptimisticSaved(willBeSaved);

    try {
      if (!willBeSaved && existingSavedProduct) {
        await api.removeSavedProduct(existingSavedProduct.id);
        await queryClient.invalidateQueries({ queryKey: ["saved-products"] });
        setToast({ message: "Removed product from Bookmarks." });
        setSaveStatus("");
      } else {
        await api.saveProduct({
          product_name: displayProductName,
          product_url: productUrl,
        });
        await queryClient.invalidateQueries({ queryKey: ["saved-products"] });
        setToast({
          message: "✓ Product saved to your Bookmarks!",
          action: { label: "View Bookmarks →", to: "/account" },
        });
        setSaveStatus("Product bookmarked to your account.");
      }
    } catch {
      setOptimisticSaved(!willBeSaved);
      setToast({ message: "Could not update bookmark. Please try again." });
    } finally {
      setAccountAction(null);
    }
  }

  function handleRankingModeChange(nextMode: typeof rankingMode) {
    const nextParams = new URLSearchParams(searchParams);
    if (nextMode === "recommended") {
      nextParams.delete("ranking");
    } else {
      nextParams.set("ranking", nextMode);
    }
    setSearchParams(nextParams);
  }

  return (
    <main className="proto-page product-detail-page">
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
          </nav>

          <div className="proto-topbar__actions">
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

      <div className="page product-detail-shell">
        {/* Breadcrumb Navigation */}
        <nav className="detail-breadcrumb" aria-label="Breadcrumb">
          <Link to="/">Home</Link>
          <span aria-hidden="true">/</span>
          <Link to={`/search?q=${encodeURIComponent(product.category || product.canonical_name)}`}>
            {product.category || "Products"}
          </Link>
          <span aria-hidden="true">/</span>
          <span className="detail-breadcrumb__active">{displayProductName}</span>
        </nav>

        {/* Hero Section */}
        <section className="detail-hero-premium">
          <div className="detail-hero__copy">
            <span className="detail-category-chip">{product.category ?? "Electronic Component"}</span>
            <h1 className="detail-title">{displayProductName}</h1>

            <div className="detail-price-box">
              <span className="detail-price-box__label">Best Live Market Price</span>
              <div className="detail-price-box__val">
                {formatCurrency(bestOption?.price ?? product.best_price)}
              </div>
              <p className="detail-price-box__vendor">
                Offered by <strong>{bestVendorLabel}</strong>
                {bestResult?.estimated_delivery_days !== null && bestResult?.estimated_delivery_days !== undefined
                  ? ` · Delivery in ${bestResult.estimated_delivery_days <= 1 ? "1 day" : `${bestResult.estimated_delivery_days} days`}`
                  : ""}
              </p>
            </div>

            {bestResult ? (
              <div className="detail-trust-pills">
                <span className="detail-trust-pill">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  {formatVerificationStatus(bestResult.price_verification_status)}
                </span>
                <span className="detail-trust-pill">
                  {formatPriceConfidence(bestResult.price_confidence)}
                </span>
                {bestResult.product_url && !bestResult.product_url.startsWith("#") ? (
                  <a
                    className="detail-trust-pill detail-trust-pill--link"
                    href={bestResult.product_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open store link ↗
                  </a>
                ) : null}
              </div>
            ) : null}

            <div className="detail-action-buttons">
              <button
                type="button"
                className={`proto-btn ${isSaved ? "proto-btn--saved" : "proto-btn--primary"}`}
                disabled={accountAction === "save"}
                onClick={handleSaveProduct}
                aria-pressed={isSaved}
                title={isSaved ? "Bookmarked to your account (click to remove)" : "Save to Bookmarks"}
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill={isSaved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
                  <path d="M19 21 12 17 5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
                </svg>
                <span>{isSaved ? "Saved in Bookmarks" : "Save to Bookmarks"}</span>
              </button>

              <Link className="proto-btn proto-btn--outline" to={hasToken ? "/account" : "/login"}>
                {hasToken ? "View Bookmarks" : "Sign In to Track"}
              </Link>
            </div>

            {saveStatus ? <p className="status-note">{saveStatus}</p> : null}
          </div>

          <div className="detail-hero__media">
            {product.image_url ? (
              <img className="detail-product-img" src={product.image_url} alt={displayProductName} />
            ) : (
              <div className="detail-product-img--placeholder">
                <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <rect x="2" y="2" width="20" height="20" rx="5" />
                  <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
                </svg>
                <span>No product image available</span>
              </div>
            )}
          </div>
        </section>

        {/* Market Benchmark Cards */}
        {comparison.benchmark ? (
          <section className="section panel detail-benchmark-panel">
            <div className="section-heading">
              <div>
                <h2>Market Benchmark & Distribution</h2>
                <span className="small-copy">Calculated from {comparison.results.length} active store listings</span>
              </div>
            </div>
            <div className="panel-grid">
              <article className="stat-card">
                <span className="stat-label">Market Median</span>
                <strong>{formatCurrency(comparison.benchmark.median_price)}</strong>
              </article>
              <article className="stat-card">
                <span className="stat-label">Market Range</span>
                <strong>
                  {formatCurrency(comparison.benchmark.min_price)} – {formatCurrency(comparison.benchmark.max_price)}
                </strong>
              </article>
              <article className="stat-card">
                <span className="stat-label">Market Average</span>
                <strong>{formatCurrency(comparison.benchmark.average_price)}</strong>
              </article>
              <article className="stat-card">
                <span className="stat-label">Last Procurement</span>
                <strong>
                  {latestPurchase ? formatCurrency(latestPurchase.unit_price) : "None recorded"}
                </strong>
              </article>
            </div>
          </section>
        ) : null}

        {/* Procurement Context */}
        {latestPurchase || offlineQuotes.length ? (
          <section className="section panel">
            <div className="section-heading">
              <div>
                <h2>Procurement Context & Offline Bids</h2>
                <span className="small-copy">Internal verified records for commercial buyers</span>
              </div>
            </div>
            <div className="panel-grid panel-grid--wide">
              <article className="stat-card">
                <span className="stat-label">Recorded Purchase</span>
                <strong>
                  {latestPurchase ? formatCurrency(latestPurchase.unit_price) : "Not recorded"}
                </strong>
                {latestPurchase ? (
                  <>
                    <p className="small-copy">Supplier: {latestPurchase.supplier_name}</p>
                    <p className="small-copy">
                      Order Qty: {latestPurchase.quantity} · Freight: {formatCurrency(latestPurchase.shipping_cost)}
                    </p>
                  </>
                ) : (
                  <p className="small-copy">No previous purchase records saved.</p>
                )}
              </article>
              <article className="stat-card">
                <span className="stat-label">Offline Supplier Quotes</span>
                <strong>{offlineQuotes.length} quotes</strong>
                {offlineQuotes.slice(0, 3).map((quote) => (
                  <p className="small-copy" key={quote.id}>
                    {quote.supplier_name}: {formatCurrency(quote.quoted_price + quote.shipping_cost)}
                  </p>
                ))}
              </article>
            </div>
          </section>
        ) : null}

        {/* Decision Summary */}
        <DecisionSummary comparison={comparison} />

        {/* Vendor Comparison Table */}
        <section className="section detail-comparison-section">
          <div className="section-heading">
            <div>
              <h2>All Store Offers & Comparisons</h2>
              <span className="small-copy">
                {comparison.results.length} offers compared across {product.vendor_count} vendors · ranked by{" "}
                {comparisonRankingLabel(rankingMode).toLowerCase()}
              </span>
            </div>
            <ComparisonToolbar
              rankingMode={rankingMode}
              onRankingModeChange={handleRankingModeChange}
              onExport={() => downloadComparisonCsv(comparison)}
            />
          </div>
          <ComparisonTable comparison={comparison} />
        </section>

        {/* Price History Chart */}
        {historyQuery.data && historyQuery.data.history.length > 0 ? (
          <section className="section panel">
            <div className="section-heading">
              <div>
                <h2>Price History & Fluctuations</h2>
                <span className="small-copy">Historical price trends across tracked seller channels</span>
              </div>
            </div>
            <PriceTrendChart history={historyQuery.data.history} />
          </section>
        ) : null}

        {/* Review Sentiment Analysis */}
        {sentimentQuery.data ? <SentimentSummary sentiment={sentimentQuery.data} /> : null}

        {/* Customer Reviews Section */}
        {reviewsQuery.data && reviewsQuery.data.reviews.length > 0 ? (
          <section className="section panel">
            <div className="section-heading">
              <div>
                <h2>Verified Buyer Reviews</h2>
                <span className="small-copy">{reviewsQuery.data.reviews.length} authentic excerpts</span>
              </div>
            </div>
            <div className="review-list">
              {reviewsQuery.data.reviews.slice(0, 6).map((review) => (
                <article className="review-card" key={review.id}>
                  <div className="section-heading">
                    <strong>{review.title ?? "Buyer Review"}</strong>
                    <span className="small-copy review-vendor-tag">{review.vendor}</span>
                  </div>
                  <p>{review.body}</p>
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </div>

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
