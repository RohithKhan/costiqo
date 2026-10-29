import { useQuery } from "@tanstack/react-query";

import type { ComparisonRankingMode } from "../types/product";
import { api } from "../services/api";

export function useSearch(query: string) {
  return useQuery({
    queryKey: ["search", query],
    queryFn: () => api.searchProducts(query),
    enabled: query.trim().length > 0,
    retry: 1,
    retryDelay: 1500,
  });
}

export function useComparison(
  query: string,
  options?: { location?: string; pincode?: string; rankingMode?: ComparisonRankingMode; progressId?: string; },
) {
  return useQuery({
    queryKey: [
      "comparison",
      query,
      options?.location ?? "",
      options?.pincode ?? "",
      options?.rankingMode ?? "recommended",
      options?.progressId ?? "",
    ],
    queryFn: () => api.fetchComparison(query, options),
    enabled: query.trim().length > 0,
    retry: 1,
    retryDelay: 1500,
  });
}

export function useSearchSuggestions(
  query: string,
  options?: { location?: string; pincode?: string; limit?: number; },
) {
  return useQuery({
    queryKey: [
      "search-suggestions",
      query,
      options?.location ?? "",
      options?.pincode ?? "",
      options?.limit ?? 6,
    ],
    queryFn: () => api.fetchSearchSuggestions(query, options),
    enabled: query.trim().length >= 2,
    retry: false,
    staleTime: 60_000,
    placeholderData: (previousData) => previousData,
  });
}
