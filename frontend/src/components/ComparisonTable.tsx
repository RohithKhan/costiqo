import type { ComparisonResponse } from "../types/product";
import { formatAvailabilityLabel, formatProductLabel } from "../lib/displayText";
import { formatPriceConfidence, formatVerificationStatus, isLowConfidence } from "../lib/priceVerification";
import { VendorBadge } from "./VendorBadge";

type ComparisonTableProps = {
  comparison: ComparisonResponse;
  highlightBest?: boolean;
};

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDelta(value: number | null) {
  if (value === null) {
    return null;
  }
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function formatDeliveryWindow(days: number | null) {
  if (days === null) {
    return "ETA not listed";
  }
  if (days <= 1) {
    return "1 day";
  }
  return `${days} days`;
}

function formatSentimentChip(value: number | null) {
  if (value === null) {
    return null;
  }
  if (value >= 0.4) {
    return "Positive reviews";
  }
  if (value <= -0.1) {
    return "Mixed reviews";
  }
  return null;
}

function formatSourceType(sourceType: string) {
  return sourceType === "offline" ? "Offline quote" : "Marketplace";
}

function buildOfferMeta({
  availability_status,
  rating,
  review_count,
}: ComparisonResponse["results"][number]) {
  const items: string[] = [];

  if (rating !== null) {
    items.push(`${rating.toFixed(1)} rating`);
  }

  if (review_count > 0) {
    items.push(`${review_count} reviews`);
  } else if (rating === null) {
    items.push("No reviews yet");
  }

  items.push(formatAvailabilityLabel(availability_status));
  return items;
}

export function ComparisonTable({ comparison, highlightBest = true }: ComparisonTableProps) {
  if (!comparison.results.length) {
    return null;
  }

  return (
    <div className="offer-list">
      {comparison.results.map((result, index) => (
        <article
          className={`offer-card ${highlightBest && index === 0 ? "offer-card--best" : ""} ${isLowConfidence(result.price_confidence) ? "offer-card--warning" : ""}`}
          key={result.vendor_product_id}
        >
          <div className="offer-card__main">
            <div className="offer-card__header">
              <div className="table-vendor">
                <VendorBadge
                  vendor={result.vendor}
                  href={result.product_url}
                  trusted={result.vendor_is_trusted}
                />
                {highlightBest && index === 0 ? <span className="pill">Best offer</span> : null}
                <span className="pill pill--muted">{formatSourceType(result.source_type)}</span>
              </div>
              <span className="offer-card__landed-inline">{formatCurrency(result.landed_price)}</span>
            </div>
            {result.product_url.startsWith("#") ? (
              <strong className="offer-card__title">{formatProductLabel(result.product_name)}</strong>
            ) : (
              <a
                className="offer-card__title"
                href={result.product_url}
                target="_blank"
                rel="noreferrer"
              >
                {formatProductLabel(result.product_name)}
              </a>
            )}
            <div className="offer-card__meta">
              {buildOfferMeta(result).map((item) => (
                <span key={`${result.vendor_product_id}-${item}`}>{item}</span>
              ))}
            </div>
            <div className="offer-card__facts">
              <div className="offer-card__fact">
                <span className="small-copy">Base price</span>
                <strong>{formatCurrency(result.price)}</strong>
              </div>
              <div className="offer-card__fact">
                <span className="small-copy">Shipping</span>
                <strong>
                  {result.shipping_cost !== null ? formatCurrency(result.shipping_cost) : "Not listed"}
                </strong>
              </div>
              <div className="offer-card__fact">
                <span className="small-copy">ETA</span>
                <strong>{formatDeliveryWindow(result.estimated_delivery_days)}</strong>
              </div>
            </div>
            <div className="offer-card__signals">
              <span className="offer-card__signal">{result.reasonability_label}</span>
              <span className="offer-card__signal">{formatVerificationStatus(result.price_verification_status)}</span>
              <span className="offer-card__signal">{formatPriceConfidence(result.price_confidence)}</span>
              {result.seller_location ? (
                <span className="offer-card__signal">{result.seller_location}</span>
              ) : null}
              {result.delta_from_median_percent !== null ? (
                <span className="offer-card__signal">vs median {formatDelta(result.delta_from_median_percent)}</span>
              ) : null}
              {result.delta_from_last_purchase_percent !== null ? (
                <span className="offer-card__signal">vs last buy {formatDelta(result.delta_from_last_purchase_percent)}</span>
              ) : null}
              {result.price_verification_status === "mismatch_detected" && result.verified_price !== null ? (
                <span className="offer-card__signal">Store page {formatCurrency(result.verified_price)}</span>
              ) : null}
              {formatSentimentChip(result.sentiment_score) ? (
                <span className="offer-card__signal">{formatSentimentChip(result.sentiment_score)}</span>
              ) : null}
            </div>
          </div>

          <div className="offer-card__side">
            <span className="small-copy">Total price</span>
            <strong className="price-highlight">{formatCurrency(result.landed_price)}</strong>
            {result.product_url.startsWith("#") ? (
              <span className="small-copy">Offline supplier quote</span>
            ) : (
              <a
                className="secondary-button"
                href={result.product_url}
                target="_blank"
                rel="noreferrer"
              >
                Open site
              </a>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
