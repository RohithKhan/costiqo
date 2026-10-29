import type { ComparisonRankingMode } from "../types/product";

export const comparisonRankingOptions: Array<{
  value: ComparisonRankingMode;
  label: string;
  description: string;
}> = [
  {
    value: "recommended",
    label: "Recommended",
    description: "Balanced by trust, landed price, delivery, and sentiment.",
  },
  {
    value: "cheapest",
    label: "Cheapest",
    description: "Lowest landed price first.",
  },
  {
    value: "fastest_delivery",
    label: "Fastest delivery",
    description: "Soonest available delivery window first.",
  },
  {
    value: "best_value",
    label: "Best value",
    description: "Best blend of price, delivery, and confidence.",
  },
  {
    value: "best_reviewed",
    label: "Best reviewed",
    description: "Strongest rating and review signal first.",
  },
];

const rankingModeLookup = new Set(comparisonRankingOptions.map((option) => option.value));

export function normalizeComparisonRankingMode(value: string | null | undefined): ComparisonRankingMode {
  if (value && rankingModeLookup.has(value as ComparisonRankingMode)) {
    return value as ComparisonRankingMode;
  }
  return "recommended";
}

export function comparisonRankingLabel(mode: ComparisonRankingMode): string {
  return comparisonRankingOptions.find((option) => option.value === mode)?.label ?? "Recommended";
}
