import { useQuery } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { CostiqoBrand } from "../components/CostiqoBrand";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { SiteFooter } from "../components/SiteFooter";
import { api } from "../services/api";
import type { ProductSummary, QuoteStatus } from "../types/product";

const editableQuoteStatuses: QuoteStatus[] = ["draft", "submitted", "approved", "purchased", "closed", "expired"];
const creatableQuoteStatuses: QuoteStatus[] = ["draft", "submitted", "approved"];

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

function formatDateTime(value: string | null) {
  if (!value) {
    return "Not recorded";
  }
  return new Date(value).toLocaleString("en-IN");
}

function formatDate(value: string | null) {
  if (!value) {
    return "No expiry";
  }
  return new Date(value).toLocaleDateString("en-IN");
}

function formatPercent(value: number | null) {
  if (value === null) {
    return "N/A";
  }
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function statusLabel(status: QuoteStatus) {
  return status.replace("_", " ");
}

export function AdminPage() {
  const [jobMessage, setJobMessage] = useState("");
  const [quoteMessage, setQuoteMessage] = useState("");
  const [purchaseMessage, setPurchaseMessage] = useState("");
  const [summaryMessage, setSummaryMessage] = useState("");
  const [lookupQuery, setLookupQuery] = useState("");
  const [lookupResults, setLookupResults] = useState<ProductSummary[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<ProductSummary | null>(null);
  const [running, setRunning] = useState(false);
  const [savingQuote, setSavingQuote] = useState(false);
  const [savingPurchase, setSavingPurchase] = useState(false);
  const [updatingQuoteId, setUpdatingQuoteId] = useState<number | null>(null);
  const [quoteStatusDrafts, setQuoteStatusDrafts] = useState<Record<number, QuoteStatus>>({});

  const vendorQuery = useQuery({
    queryKey: ["admin-vendors"],
    queryFn: api.fetchAdminVendors,
  });
  const quoteQuery = useQuery({
    queryKey: ["admin-offline-quotes", selectedProduct?.id ?? null],
    queryFn: () => api.fetchOfflineQuotes(selectedProduct!.id),
    enabled: Boolean(selectedProduct),
  });
  const purchaseQuery = useQuery({
    queryKey: ["admin-purchases", selectedProduct?.id ?? null],
    queryFn: () => api.fetchPurchaseRecords(selectedProduct!.id),
    enabled: Boolean(selectedProduct),
  });
  const procurementQuery = useQuery({
    queryKey: ["admin-procurement-summary", selectedProduct?.id ?? null],
    queryFn: () => api.fetchProcurementSummary(selectedProduct!.id),
    enabled: Boolean(selectedProduct),
  });

  async function refreshProcurementViews() {
    const results = await Promise.allSettled([
      quoteQuery.refetch(),
      purchaseQuery.refetch(),
      procurementQuery.refetch(),
    ]);

    return results.every((result) => {
      if (result.status !== "fulfilled") {
        return false;
      }
      return !result.value.isError;
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const query = String(formData.get("query") ?? "").trim();
    if (!query) {
      return;
    }

    setRunning(true);
    setJobMessage("");
    try {
      const job = await api.triggerScrape(query);
      setJobMessage(
        `Job ${job.id} completed with ${job.result_count} listings for "${job.query}".`,
      );
      vendorQuery.refetch();
    } catch {
      setJobMessage("Scrape trigger failed. Log in as an admin account before retrying.");
    } finally {
      setRunning(false);
    }
  }

  async function handleLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = lookupQuery.trim();
    if (!trimmed) {
      return;
    }

    try {
      const results = await api.searchProducts(trimmed);
      setLookupResults(results.results);
      if (results.results.length) {
        setSelectedProduct(results.results[0]);
      }
    } catch {
      setLookupResults([]);
    }
  }

  async function handleQuoteSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProduct) {
      setQuoteMessage("Pick a product first.");
      return;
    }

    const form = event.currentTarget;
    const formData = new FormData(event.currentTarget);
    setSavingQuote(true);
    setQuoteMessage("");
    try {
      const quote = await api.createOfflineQuote({
        product_id: selectedProduct.id,
        supplier_name: String(formData.get("supplier_name") ?? ""),
        quoted_price: Number(formData.get("quoted_price") ?? 0),
        shipping_cost: Number(formData.get("shipping_cost") ?? 0),
        seller_location: String(formData.get("seller_location") ?? "") || undefined,
        pincode: String(formData.get("pincode") ?? "") || undefined,
        estimated_delivery_days: Number(formData.get("estimated_delivery_days") ?? 0) || undefined,
        contact_name: String(formData.get("contact_name") ?? "") || undefined,
        contact_phone: String(formData.get("contact_phone") ?? "") || undefined,
        quote_reference: String(formData.get("quote_reference") ?? "") || undefined,
        supplier_score: Number(formData.get("supplier_score") ?? 0) || undefined,
        status: String(formData.get("status") ?? "submitted") as QuoteStatus,
        valid_until: String(formData.get("valid_until") ?? "") || undefined,
        notes: String(formData.get("notes") ?? "") || undefined,
      });
      form.reset();
      const refreshSucceeded = await refreshProcurementViews();
      setQuoteMessage(
        refreshSucceeded
          ? `Offline quote saved for ${quote.supplier_name} with status ${statusLabel(quote.status)}.`
          : `Offline quote saved for ${quote.supplier_name}, but the dashboard needs a manual refresh to pick up the latest state.`,
      );
    } catch {
      setQuoteMessage("Offline quote could not be saved.");
    } finally {
      setSavingQuote(false);
    }
  }

  async function handlePurchaseSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProduct) {
      setPurchaseMessage("Pick a product first.");
      return;
    }

    const form = event.currentTarget;
    const formData = new FormData(event.currentTarget);
    const relatedQuoteId = String(formData.get("related_quote_id") ?? "");
    setSavingPurchase(true);
    setPurchaseMessage("");
    try {
      const record = await api.createPurchaseRecord({
        product_id: selectedProduct.id,
        supplier_name: String(formData.get("supplier_name") ?? ""),
        unit_price: Number(formData.get("unit_price") ?? 0),
        quantity: Number(formData.get("quantity") ?? 1),
        shipping_cost: Number(formData.get("shipping_cost") ?? 0),
        buyer_location: String(formData.get("buyer_location") ?? "") || undefined,
        pincode: String(formData.get("pincode") ?? "") || undefined,
        delivery_days: Number(formData.get("delivery_days") ?? 0) || undefined,
        reference_number: String(formData.get("reference_number") ?? "") || undefined,
        related_quote_ids: relatedQuoteId ? [Number(relatedQuoteId)] : undefined,
        notes: String(formData.get("notes") ?? "") || undefined,
      });
      form.reset();
      const refreshSucceeded = await refreshProcurementViews();
      setPurchaseMessage(
        refreshSucceeded
          ? `Purchase record saved for ${record.supplier_name}.`
          : `Purchase record saved for ${record.supplier_name}, but the dashboard needs a manual refresh to pick up the latest state.`,
      );
    } catch {
      setPurchaseMessage("Purchase record could not be saved.");
    } finally {
      setSavingPurchase(false);
    }
  }

  async function handleQuoteStatusUpdate(quoteId: number, fallbackStatus: QuoteStatus) {
    const nextStatus = quoteStatusDrafts[quoteId] ?? fallbackStatus;
    setUpdatingQuoteId(quoteId);
    setSummaryMessage("");
    try {
      const quote = await api.updateOfflineQuote(quoteId, { status: nextStatus });
      const refreshSucceeded = await refreshProcurementViews();
      setSummaryMessage(
        refreshSucceeded
          ? `Quote ${quote.supplier_name} moved to ${statusLabel(quote.status)}.`
          : `Quote ${quote.supplier_name} was updated, but the dashboard needs a manual refresh to pick up the latest state.`,
      );
    } catch {
      setSummaryMessage("Quote status could not be updated.");
    } finally {
      setUpdatingQuoteId(null);
    }
  }

  return (
    <main className="proto-page admin-page">
      <header className="proto-topbar" role="banner">
        <div className="proto-topbar__inner">
          <CostiqoBrand />

          <nav className="proto-nav" aria-label="Primary navigation">
            <Link className="proto-nav__link" to="/">
              Overview
            </Link>
            <Link className="proto-nav__link" to="/search?q=Raspberry+Pi+4">
              Explore Deals
            </Link>
            <Link className="proto-nav__link proto-nav__link--active" to="/admin">
              Admin Portal
            </Link>
          </nav>

          <div className="proto-topbar__actions">
            <Link className="proto-btn proto-btn--ghost proto-btn--sm" to="/account">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="8" r="4" />
                <path d="M20 21a8 8 0 10-16 0" />
              </svg>
              <span>Account</span>
            </Link>
          </div>
        </div>
      </header>

      <div className="admin-shell">
        <section className="page-header admin-header">
          <div>
            <p className="eyebrow">Procurement Operations</p>
            <h1>Source Health, Offline Quotes & Benchmark Intelligence</h1>
          </div>
        </section>

      <section className="form-card form-card--wide">
        <div className="section-heading">
          <h2>Run scrape job</h2>
        </div>
        <form onSubmit={handleSubmit} className="form-grid">
          <label className="form-row">
            <span>Product query</span>
            <input name="query" placeholder="iphone 15" required />
          </label>
          <button type="submit" className="search-button" disabled={running}>
            {running ? "Running..." : "Trigger scrape"}
          </button>
        </form>
        {jobMessage ? <p className="small-copy">{jobMessage}</p> : null}
      </section>

      <section className="form-card form-card--wide">
        <div className="section-heading">
          <h2>Choose product</h2>
          <span className="small-copy">Use one product at a time to inspect quote lifecycle and purchase benchmarks.</span>
        </div>
        <form className="form-grid" onSubmit={handleLookup}>
          <label className="form-row">
            <span>Search product catalog</span>
            <input
              value={lookupQuery}
              onChange={(event) => setLookupQuery(event.target.value)}
              placeholder="iphone 15 256 gb"
              required
            />
          </label>
          <button type="submit" className="secondary-button">
            Find products
          </button>
        </form>

        {selectedProduct ? (
          <div className="selected-product">
            <strong>{selectedProduct.canonical_name}</strong>
            <span className="small-copy">
              Product ID {selectedProduct.id} · Best live price{" "}
              {selectedProduct.best_price !== null ? formatCurrency(selectedProduct.best_price) : "N/A"}
            </span>
          </div>
        ) : null}

        {lookupResults.length ? (
          <div className="product-grid">
            {lookupResults.slice(0, 6).map((product) => (
              <article className="status-card" key={product.id}>
                <strong>{product.canonical_name}</strong>
                <p className="small-copy">
                  {product.vendor_count} vendors ·{" "}
                  {product.best_price !== null ? formatCurrency(product.best_price) : "N/A"}
                </p>
                <button
                  type="button"
                  className="link-button"
                  onClick={() => setSelectedProduct(product)}
                >
                  Use product
                </button>
              </article>
            ))}
          </div>
        ) : null}
      </section>

      <section className="admin-grid">
        {/* Record Offline Quote Card */}
        <section className="form-card">
          <div className="admin-form-card__header">
            <div className="admin-form-card__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <polyline points="10 9 9 9 8 9" />
              </svg>
            </div>
            <div className="admin-form-card__title">
              <h2>Record Offline Quote</h2>
              <p className="admin-form-card__subtitle">
                Log verified supplier estimates or wholesale price sheets for benchmark comparisons.
              </p>
            </div>
          </div>

          {selectedProduct ? (
            <div className="admin-card-target-pill" role="status">
              <span>🎯</span>
              <span>Target: <strong>{selectedProduct.canonical_name}</strong> (ID #{selectedProduct.id})</span>
            </div>
          ) : (
            <div className="admin-card-target-pill admin-card-target-pill--warning" role="alert">
              <span>⚠️</span>
              <span>Select a target product from the lookup section above first.</span>
            </div>
          )}

          <form onSubmit={handleQuoteSubmit} className="admin-form-fields-grid">
            <div className="admin-form-field admin-form-field--full">
              <label htmlFor="quote-supplier">Supplier Name *</label>
              <input id="quote-supplier" name="supplier_name" placeholder="e.g. Local Mobile Hub / Wholesale Dist." required />
            </div>

            <div className="admin-form-field">
              <label htmlFor="quote-price">Quoted Price (₹) *</label>
              <input id="quote-price" name="quoted_price" type="number" min="1" step="0.01" placeholder="e.g. 4500" required />
            </div>

            <div className="admin-form-field">
              <label htmlFor="quote-shipping">Shipping Cost (₹)</label>
              <input id="quote-shipping" name="shipping_cost" type="number" min="0" step="0.01" defaultValue="0" />
            </div>

            <div className="admin-form-field">
              <label htmlFor="quote-status">Lifecycle Status</label>
              <select id="quote-status" name="status" defaultValue="submitted">
                {creatableQuoteStatuses.map((status) => (
                  <option key={status} value={status}>
                    {statusLabel(status)}
                  </option>
                ))}
              </select>
            </div>

            <div className="admin-form-field">
              <label htmlFor="quote-ref">Quote Reference #</label>
              <input id="quote-ref" name="quote_reference" placeholder="e.g. Q-2026-014" />
            </div>

            <div className="admin-form-field">
              <label htmlFor="quote-score">Supplier Score (0–5)</label>
              <input id="quote-score" name="supplier_score" type="number" min="0" max="5" step="0.1" placeholder="e.g. 4.6" />
            </div>

            <div className="admin-form-field">
              <label htmlFor="quote-valid">Valid Until</label>
              <input id="quote-valid" name="valid_until" type="date" />
            </div>

            <div className="admin-form-field">
              <label htmlFor="quote-location">Seller Location / City</label>
              <input id="quote-location" name="seller_location" placeholder="e.g. Bengaluru, Karnataka" />
            </div>

            <div className="admin-form-field">
              <label htmlFor="quote-pincode">Delivery Pincode</label>
              <input id="quote-pincode" name="pincode" placeholder="e.g. 560001" maxLength={6} />
            </div>

            <div className="admin-form-field">
              <label htmlFor="quote-delivery-days">Est. Delivery (Days)</label>
              <input id="quote-delivery-days" name="estimated_delivery_days" type="number" min="0" placeholder="e.g. 2" />
            </div>

            <div className="admin-form-field">
              <label htmlFor="quote-contact-name">Contact Person</label>
              <input id="quote-contact-name" name="contact_name" placeholder="e.g. Rajesh Kumar" />
            </div>

            <div className="admin-form-field">
              <label htmlFor="quote-contact-phone">Contact Phone</label>
              <input id="quote-contact-phone" name="contact_phone" placeholder="e.g. +91 98765 43210" />
            </div>

            <div className="admin-form-field admin-form-field--full">
              <label htmlFor="quote-notes">Quote Terms & Notes</label>
              <input id="quote-notes" name="notes" placeholder="e.g. In-store pickup option, 1-year local warranty" />
            </div>

            <button type="submit" className="admin-submit-btn" disabled={savingQuote}>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              <span>{savingQuote ? "Saving Quote..." : "Save Offline Quote"}</span>
            </button>
          </form>

          {quoteMessage ? (
            <div
              className={`admin-form-feedback ${
                quoteMessage.toLowerCase().includes("could not") || quoteMessage.toLowerCase().includes("failed")
                  ? "admin-form-feedback--error"
                  : "admin-form-feedback--success"
              }`}
              role="alert"
            >
              <span>{quoteMessage.toLowerCase().includes("could not") ? "❌" : "✓"}</span>
              <span>{quoteMessage}</span>
            </div>
          ) : null}
        </section>

        {/* Record Purchase Card */}
        <section className="form-card">
          <div className="admin-form-card__header">
            <div className="admin-form-card__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="2" y="4" width="20" height="16" rx="2" />
                <line x1="2" y1="10" x2="22" y2="10" />
                <circle cx="7" cy="15" r="1" />
                <circle cx="12" cy="15" r="1" />
              </svg>
            </div>
            <div className="admin-form-card__title">
              <h2>Record Purchase</h2>
              <p className="admin-form-card__subtitle">
                Log actual transactions and associate them with approved supplier quotes for landed audits.
              </p>
            </div>
          </div>

          {selectedProduct ? (
            <div className="admin-card-target-pill" role="status">
              <span>🎯</span>
              <span>Target: <strong>{selectedProduct.canonical_name}</strong> (ID #{selectedProduct.id})</span>
            </div>
          ) : (
            <div className="admin-card-target-pill admin-card-target-pill--warning" role="alert">
              <span>⚠️</span>
              <span>Select a target product from the lookup section above first.</span>
            </div>
          )}

          <form onSubmit={handlePurchaseSubmit} className="admin-form-fields-grid">
            <div className="admin-form-field admin-form-field--full">
              <label htmlFor="purchase-supplier">Supplier / Vendor Name *</label>
              <input id="purchase-supplier" name="supplier_name" placeholder="e.g. Department PO / Authorized Dealer" required />
            </div>

            <div className="admin-form-field">
              <label htmlFor="purchase-unit-price">Unit Price (₹) *</label>
              <input id="purchase-unit-price" name="unit_price" type="number" min="1" step="0.01" placeholder="e.g. 4350" required />
            </div>

            <div className="admin-form-field">
              <label htmlFor="purchase-qty">Quantity</label>
              <input id="purchase-qty" name="quantity" type="number" min="1" defaultValue="1" />
            </div>

            <div className="admin-form-field">
              <label htmlFor="purchase-shipping">Shipping Cost (₹)</label>
              <input id="purchase-shipping" name="shipping_cost" type="number" min="0" step="0.01" defaultValue="0" />
            </div>

            <div className="admin-form-field">
              <label htmlFor="purchase-ref">PO / Invoice Reference #</label>
              <input id="purchase-ref" name="reference_number" placeholder="e.g. PO-2026-001" />
            </div>

            <div className="admin-form-field admin-form-field--full">
              <label htmlFor="purchase-quote">Linked Offline Quote</label>
              <select id="purchase-quote" name="related_quote_id" defaultValue="">
                <option value="">No linked quote (Direct Procurement)</option>
                {(quoteQuery.data ?? [])
                  .filter((quote) => quote.is_active && ["submitted", "approved"].includes(quote.status))
                  .map((quote) => (
                    <option key={quote.id} value={quote.id}>
                      #{quote.id} · {quote.supplier_name} · {statusLabel(quote.status)} · {formatCurrency(quote.total_price)}
                    </option>
                  ))}
              </select>
            </div>

            <div className="admin-form-field">
              <label htmlFor="purchase-location">Buyer Location</label>
              <input id="purchase-location" name="buyer_location" placeholder="e.g. Bengaluru, HQ" />
            </div>

            <div className="admin-form-field">
              <label htmlFor="purchase-pincode">Delivery Pincode</label>
              <input id="purchase-pincode" name="pincode" placeholder="e.g. 560001" maxLength={6} />
            </div>

            <div className="admin-form-field">
              <label htmlFor="purchase-days">Delivery Duration (Days)</label>
              <input id="purchase-days" name="delivery_days" type="number" min="0" placeholder="e.g. 3" />
            </div>

            <div className="admin-form-field admin-form-field--full">
              <label htmlFor="purchase-notes">Purchase Notes / Benchmark Memo</label>
              <input id="purchase-notes" name="notes" placeholder="e.g. Paid price matched market low, bulk order discount applied" />
            </div>

            <button type="submit" className="admin-submit-btn" disabled={savingPurchase}>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                <path d="M5 13l4 4L19 7" />
              </svg>
              <span>{savingPurchase ? "Saving Purchase..." : "Save Purchase Record"}</span>
            </button>
          </form>

          {purchaseMessage ? (
            <div
              className={`admin-form-feedback ${
                purchaseMessage.toLowerCase().includes("could not") || purchaseMessage.toLowerCase().includes("failed")
                  ? "admin-form-feedback--error"
                  : "admin-form-feedback--success"
              }`}
              role="alert"
            >
              <span>{purchaseMessage.toLowerCase().includes("could not") ? "❌" : "✓"}</span>
              <span>{purchaseMessage}</span>
            </div>
          ) : null}
        </section>
      </section>

      {selectedProduct && procurementQuery.data ? (
        <>
          <section className="section panel">
            <div className="section-heading">
              <h2>Procurement summary</h2>
              <span className="small-copy">{procurementQuery.data.product_name}</span>
            </div>
            <div className="panel-grid panel-grid--wide">
              <article className="stat-card">
                <span className="stat-label">Active quotes</span>
                <strong>{procurementQuery.data.active_quote_count}</strong>
              </article>
              <article className="stat-card">
                <span className="stat-label">Expiring soon</span>
                <strong>{procurementQuery.data.expiring_quote_count}</strong>
              </article>
              <article className="stat-card">
                <span className="stat-label">Approved quotes</span>
                <strong>{procurementQuery.data.approved_quote_count}</strong>
              </article>
              <article className="stat-card">
                <span className="stat-label">Status mix</span>
                <strong>
                  {procurementQuery.data.quote_status_breakdown
                    .map((item) => `${statusLabel(item.status)} ${item.count}`)
                    .join(" · ")}
                </strong>
              </article>
            </div>
            {procurementQuery.data.latest_purchase_benchmark ? (
              <div className="admin-benchmark">
                <strong>Latest purchase vs market</strong>
                <p className="small-copy">
                  {procurementQuery.data.latest_purchase_benchmark.supplier_name} ·{" "}
                  {formatCurrency(procurementQuery.data.latest_purchase_benchmark.unit_price)} · bought{" "}
                  {formatDateTime(procurementQuery.data.latest_purchase_benchmark.purchased_at)}
                </p>
                <p className="small-copy">
                  Best online {formatCurrency(procurementQuery.data.latest_purchase_benchmark.market_best_price)} ·
                  Median {formatCurrency(procurementQuery.data.latest_purchase_benchmark.market_median_price)} ·
                  vs best {formatPercent(procurementQuery.data.latest_purchase_benchmark.delta_from_market_best_percent)} ·
                  vs median {formatPercent(procurementQuery.data.latest_purchase_benchmark.delta_from_market_median_percent)}
                </p>
                <p className="small-copy">{procurementQuery.data.latest_purchase_benchmark.benchmark_note}</p>
              </div>
            ) : (
              <p className="small-copy">No purchase benchmark recorded yet for this product.</p>
            )}
          </section>

          <section className="section panel">
            <div className="section-heading">
              <h2>Supplier competitiveness</h2>
              <span className="small-copy">Offline suppliers compared against current online market.</span>
            </div>
            <div className="saved-list">
              {procurementQuery.data.supplier_competitiveness.length ? (
                procurementQuery.data.supplier_competitiveness.map((supplier) => (
                  <article className="saved-card" key={supplier.supplier_name}>
                    <div>
                      <strong>{supplier.supplier_name}</strong>
                      <p className="small-copy">
                        {supplier.competitiveness_label} · quotes {supplier.quote_count} · purchases{" "}
                        {supplier.purchase_count}
                      </p>
                    </div>
                    <div className="procurement-inline-metrics">
                      <span>Best quote {formatCurrency(supplier.best_quote_total_price)}</span>
                      <span>Average quote {formatCurrency(supplier.average_quote_total_price)}</span>
                      <span>Average paid {formatCurrency(supplier.average_purchase_unit_price)}</span>
                      <span>Latest status {supplier.latest_quote_status ? statusLabel(supplier.latest_quote_status) : "none"}</span>
                    </div>
                  </article>
                ))
              ) : (
                <p className="small-copy">No supplier activity recorded yet.</p>
              )}
            </div>
          </section>

          <section className="section panel">
            <div className="section-heading">
              <h2>Quote lifecycle</h2>
              <span className="small-copy">Manage active, approved, purchased, and expiring quotes.</span>
            </div>
            {summaryMessage ? <p className="small-copy">{summaryMessage}</p> : null}
            <div className="saved-list">
              {(quoteQuery.data ?? []).length ? (
                quoteQuery.data!.map((quote) => {
                  const draftStatus = quoteStatusDrafts[quote.id] ?? quote.status;
                  return (
                    <article className="saved-card" key={quote.id}>
                      <div>
                        <strong>{quote.supplier_name}</strong>
                        <p className="small-copy">
                          {formatCurrency(quote.total_price)} · {statusLabel(quote.status)} · expiry {formatDate(quote.valid_until)}
                        </p>
                        <p className="small-copy">
                          Ref {quote.quote_reference ?? "not set"} · Supplier score{" "}
                          {quote.supplier_score !== null ? quote.supplier_score.toFixed(1) : "N/A"} · created{" "}
                          {formatDateTime(quote.created_at)}
                        </p>
                        {quote.is_expiring_soon ? (
                          <p className="small-copy">This quote expires within the next 7 days.</p>
                        ) : null}
                      </div>
                      <div className="procurement-actions">
                        <select
                          value={draftStatus}
                          onChange={(event) =>
                            setQuoteStatusDrafts((current) => ({
                              ...current,
                              [quote.id]: event.target.value as QuoteStatus,
                            }))
                          }
                        >
                          {editableQuoteStatuses.map((status) => (
                            <option key={status} value={status}>
                              {statusLabel(status)}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={updatingQuoteId === quote.id}
                          onClick={() => handleQuoteStatusUpdate(quote.id, quote.status)}
                        >
                          {updatingQuoteId === quote.id ? "Updating..." : "Update status"}
                        </button>
                      </div>
                    </article>
                  );
                })
              ) : (
                <p className="small-copy">No offline quotes recorded yet.</p>
              )}
            </div>
          </section>

          <section className="section panel">
            <div className="section-heading">
              <h2>Purchase history</h2>
              <span className="small-copy">Last paid records and current benchmark deltas.</span>
            </div>
            <div className="saved-list">
              {(purchaseQuery.data ?? []).length ? (
                purchaseQuery.data!.map((record) => (
                  <article className="saved-card" key={record.id}>
                    <div>
                      <strong>{record.supplier_name}</strong>
                      <p className="small-copy">
                        {formatCurrency(record.unit_price)} per unit · total {formatCurrency(record.total_price)} ·{" "}
                        {formatDateTime(record.purchased_at)}
                      </p>
                      <p className="small-copy">
                        vs best {formatPercent(record.delta_from_market_best_percent)} · vs median{" "}
                        {formatPercent(record.delta_from_market_median_percent)} · linked quotes{" "}
                        {record.related_quote_ids.length}
                      </p>
                    </div>
                    <div className="procurement-inline-metrics">
                      <span>Qty {record.quantity}</span>
                      <span>Best online {formatCurrency(record.market_best_price)}</span>
                      <span>Median {formatCurrency(record.market_median_price)}</span>
                      <span>Ref {record.reference_number ?? "not set"}</span>
                    </div>
                  </article>
                ))
              ) : (
                <p className="small-copy">No purchase records recorded yet.</p>
              )}
            </div>
          </section>
        </>
      ) : null}

      {vendorQuery.isLoading ? <LoadingState message="Loading vendor health..." /> : null}
      {vendorQuery.isError ? (
        <ErrorState message="Vendor health could not be loaded." />
      ) : null}

      {vendorQuery.data ? (
        <section className="section">
          <div className="section-heading">
            <h2>Vendor status</h2>
          </div>
          <div className="status-grid">
            {vendorQuery.data.map((vendor) => (
              <article className="status-card" key={vendor.id}>
                <div className="section-heading">
                  <strong>{vendor.name}</strong>
                  <span className={`pill ${vendor.is_active ? "" : "pill--muted"}`}>
                    {vendor.is_active ? "Active" : "Inactive"}
                  </span>
                </div>
                <p className="small-copy">{vendor.base_url}</p>
                <p className="small-copy">Strategy: {vendor.scrape_strategy}</p>
                <p className="small-copy">Last status: {vendor.last_status ?? "idle"}</p>
                <p className="small-copy">
                  Last scrape: {vendor.last_scraped_at ? new Date(vendor.last_scraped_at).toLocaleString() : "never"}
                </p>
              </article>
            ))}
          </div>
        </section>
      ) : null}
      </div>
      <SiteFooter />
    </main>
  );
}
