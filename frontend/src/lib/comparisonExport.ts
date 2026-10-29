import type { ComparisonResponse } from "../types/product";

function escapeCsv(value: string | number | null | undefined) {
  if (value === null || value === undefined) {
    return "";
  }
  const text = String(value);
  if (/[",\n]/.test(text)) {
    return `"${text.split('"').join('""')}"`;
  }
  return text;
}

function sanitizeFilenamePart(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40) || "comparison";
}

export function downloadComparisonCsv(comparison: ComparisonResponse) {
  const lines = [
    ["Query", comparison.query],
    ["Ranking mode", comparison.ranking_mode],
    ["Location", comparison.location ?? ""],
    ["Pincode", comparison.pincode ?? ""],
    ["Product", comparison.product_name ?? ""],
    [],
    [
      "Vendor",
      "Trusted Domain",
      "Vendor Domain",
      "Source Type",
      "Product Name",
      "Base Price",
      "Landed Price",
      "Shipping Cost",
      "Delivery Days",
      "Rating",
      "Review Count",
      "Sentiment Score",
      "Price Confidence",
      "Price Verification Status",
      "Reasonability",
      "Delta vs Median Percent",
      "Delta vs Last Purchase Percent",
      "Product URL",
    ],
    ...comparison.results.map((result) => [
      result.vendor,
      result.vendor_is_trusted ? "yes" : "no",
      result.vendor_domain ?? "",
      result.source_type,
      result.product_name,
      result.price,
      result.landed_price,
      result.shipping_cost ?? "",
      result.estimated_delivery_days ?? "",
      result.rating ?? "",
      result.review_count,
      result.sentiment_score ?? "",
      result.price_confidence,
      result.price_verification_status,
      result.reasonability_label,
      result.delta_from_median_percent ?? "",
      result.delta_from_last_purchase_percent ?? "",
      result.product_url,
    ]),
  ];

  const csv = lines
    .map((row) => row.map((value) => escapeCsv(value)).join(","))
    .join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `costiqo-${sanitizeFilenamePart(comparison.query)}-${comparison.ranking_mode}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
