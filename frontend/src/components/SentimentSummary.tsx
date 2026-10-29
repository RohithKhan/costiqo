import type { ProductSentimentResponse } from "../types/review";
import { VendorBadge } from "./VendorBadge";

type SentimentSummaryProps = {
  sentiment: ProductSentimentResponse;
};

export function SentimentSummary({ sentiment }: SentimentSummaryProps) {
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>Review sentiment</h2>
        <span className="price-highlight">{sentiment.sentiment_score.toFixed(2)}</span>
      </div>
      <div className="panel-grid">
        <div className="stat-card">
          <span className="stat-label">Positive</span>
          <strong>{sentiment.positive_count}</strong>
        </div>
        <div className="stat-card">
          <span className="stat-label">Neutral</span>
          <strong>{sentiment.neutral_count}</strong>
        </div>
        <div className="stat-card">
          <span className="stat-label">Negative</span>
          <strong>{sentiment.negative_count}</strong>
        </div>
      </div>
      <div className="review-list">
        {sentiment.vendor_breakdown.map((item) => (
            <article className="review-card" key={item.vendor_product_id}>
              <div className="section-heading">
                <VendorBadge vendor={item.vendor} href={item.product_url} />
                <span className="small-copy">Score {item.sentiment_score.toFixed(2)}</span>
              </div>
              <p className="small-copy">
              {item.positive_count} positive · {item.neutral_count} neutral · {item.negative_count} negative
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
