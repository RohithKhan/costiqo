const VENDOR_LABELS: Record<string, string> = {
  amazon: "Amazon",
  flipkart: "Flipkart",
  poorvika: "Poorvika",
  "reliance digital": "Reliance Digital",
  "reliancedigital.in": "Reliance Digital",
  "bigbasket.com": "BigBasket",
  croma: "Croma",
  "global electronics": "Global Electronics",
  "globalelectronics.in": "Global Electronics",
  ibo: "IBO",
  "ibo.com": "IBO",
  moglix: "Moglix",
  "moglix.com": "Moglix",
  robu: "Robu",
  "robu.in": "Robu",
  "vijay sales": "Vijay Sales",
  "tatacliq.com": "Tata Cliq",
  jiomart: "JioMart",
};

function titleCase(value: string) {
  return value
    .split(" ")
    .filter(Boolean)
    .map((segment) => segment[0]?.toUpperCase() + segment.slice(1))
    .join(" ");
}

export function formatVendorLabel(vendor: string) {
  const normalized = vendor
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, "")
    .replace(/^www\./, "")
    .replace(/\/.*$/, "")
    .replace(/[?#!]+$/g, "");
  const mappedLabel = VENDOR_LABELS[normalized];
  if (mappedLabel) {
    return mappedLabel;
  }

  if (normalized.includes(".")) {
    const baseSegment = normalized.split(".")[0] ?? normalized;
    return titleCase(baseSegment.replace(/[-_]+/g, " "));
  }

  return titleCase(normalized.replace(/[-_]+/g, " "));
}

export function formatProductLabel(name: string) {
  return name
    .replace(/\b(\d+)\s*GB\b/g, "$1 GB")
    .replace(/\b(\d+)\s*TB\b/g, "$1 TB")
    .replace(/\bStorage\b/gi, "")
    .replace(/\b0\s*mAH\b/gi, "")
    .replace(/\b1\s*Unit\b/gi, "")
    .replace(/\(\s+/g, "(")
    .replace(/\s+\)/g, ")")
    .replace(/,\s*,/g, ", ")
    .replace(/\(\s*,/g, "(")
    .replace(/,\s*\)/g, ")")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+,/g, ",")
    .replace(/[,\-]\s*$/g, "")
    .trim();
}

export function formatAvailabilityLabel(status: string) {
  const normalized = status.trim().toLowerCase();
  if (!normalized) {
    return "Availability not listed";
  }

  if (normalized.includes("out of stock")) {
    return "Out of stock";
  }

  if (normalized.includes("limited stock")) {
    return "Limited stock";
  }

  if (normalized.includes("preorder")) {
    return "Preorder";
  }

  if (normalized.includes("in stock")) {
    return "In stock";
  }

  if (normalized.includes("unavailable")) {
    return "Unavailable";
  }

  if (normalized.includes("free delivery")) {
    return "Free delivery";
  }

  if (normalized.includes("delivery")) {
    return "Delivery info listed";
  }

  return status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}
