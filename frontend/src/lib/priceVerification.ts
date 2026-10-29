export function formatVerificationStatus(status: string) {
  if (status === "verified") {
    return "Store price verified";
  }
  if (status === "mismatch_detected") {
    return "Price mismatch detected";
  }
  if (status === "supplier-quoted") {
    return "Supplier quoted";
  }
  if (status === "stale") {
    return "Price needs refresh";
  }
  if (status === "incomplete") {
    return "Verification incomplete";
  }
  return "Fresh scraped price";
}

export function formatPriceConfidence(value: number) {
  return `${Math.round(value * 100)}% confidence`;
}

export function isLowConfidence(value: number) {
  return value < 0.5;
}
