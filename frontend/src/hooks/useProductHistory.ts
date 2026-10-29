import { useQuery } from "@tanstack/react-query";

import { api } from "../services/api";

export function useProductHistory(productId: number | null) {
  return useQuery({
    queryKey: ["history", productId],
    queryFn: () => api.fetchProductHistory(productId as number),
    enabled: productId !== null,
  });
}
