import type { ComparisonResponse, DecisionHighlight } from "../types/product";

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDelivery(days: number | null) {
  if (days === null) {
    return "Delivery timing unavailable";
  }
  if (days <= 1) {
    return "About 1 day";
  }
  return `About ${days} days`;
}

function renderHighlight(highlight: DecisionHighlight | null, fallback: string) {
  if (!highlight) {
    return <p className="small-copy">{fallback}</p>;
  }

  const vendorContent = highlight.product_url.startsWith("#") ? (
    <strong>{highlight.vendor}</strong>
  ) : (
    <a href={highlight.product_url} target="_blank" rel="noreferrer">
      <strong>{highlight.vendor}</strong>
    </a>
  );

  return (
    <>
      {vendorContent}
      <p className="small-copy">
        {formatCurrency(highlight.landed_price)} landed · {Math.round(highlight.price_confidence * 100)}% confidence
      </p>
      {highlight.detail ? <p className="small-copy">{highlight.detail}</p> : null}
    </>
  );
}

type DecisionSummaryProps = {
  comparison: ComparisonResponse;
};

export function DecisionSummary({ comparison }: DecisionSummaryProps) {
  const summary = comparison.decision_summary;

  if (!summary) {
    return null;
  }

  return (
    <section className="section panel">
      <div className="section-heading">
        <h2>Decision summary</h2>
        <span className="small-copy">
          {summary.location_context_applied && summary.location_context_label
            ? `Personalized for ${summary.location_context_label}`
            : "General recommendation"}
        </span>
      </div>
      <div className="panel-grid panel-grid--wide">
        <article className="stat-card">
          <span className="stat-label">Recommended vendor</span>
          {renderHighlight(summary.recommended, "No recommendation available yet.")}
        </article>
        <article className="stat-card">
          <span className="stat-label">Cheapest offer</span>
          {renderHighlight(summary.cheapest_offer, "No cheapest offer identified.")}
        </article>
        <article className="stat-card">
          <span className="stat-label">Best landed price</span>
          {renderHighlight(summary.best_landed_price, "No landed-price signal yet.")}
        </article>
        <article className="stat-card">
          <span className="stat-label">Best value</span>
          {renderHighlight(summary.best_value, "No value recommendation is available yet.")}
        </article>
        <article className="stat-card">
          <span className="stat-label">Fastest delivery</span>
          {summary.fastest_delivery ? (
            <>
              <strong>{summary.fastest_delivery.vendor}</strong>
              <p className="small-copy">{formatDelivery(summary.fastest_delivery.estimated_delivery_days)}</p>
              {summary.fastest_delivery.detail ? (
                <p className="small-copy">{summary.fastest_delivery.detail}</p>
              ) : null}
            </>
          ) : (
            <p className="small-copy">No delivery estimate is available yet.</p>
          )}
        </article>
        <article className="stat-card">
          <span className="stat-label">Best reviewed</span>
          {renderHighlight(summary.best_reviewed, "No review signal is available yet.")}
        </article>
        <article className="stat-card">
          <span className="stat-label">
            {summary.location_context_applied ? "Best for this location" : "Best for your location"}
          </span>
          {renderHighlight(summary.best_for_location, "Apply a pincode to personalize this choice.")}
        </article>
      </div>
      {summary.warnings.length ? (
        <div className="decision-summary__warnings">
          {summary.warnings.map((warning) => (
            <p className="small-copy" key={warning}>
              {warning}
            </p>
          ))}
        </div>
      ) : null}
    </section>
  );
}
