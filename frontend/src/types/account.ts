import type { ProductSummary } from "./product";

export type SavedProduct = {
  id: number;
  product_name: string;
  product_url: string;
  created_at: string;
};

export type SavedSearch = {
  id: number;
  query: string;
  location: string | null;
  pincode: string | null;
  created_at: string;
};

export type AlertRule = {
  id: number;
  trigger_type: string;
  target_price: number | null;
  is_active: boolean;
  query: string | null;
  location: string | null;
  pincode: string | null;
  created_at: string;
  product: ProductSummary | null;
};
