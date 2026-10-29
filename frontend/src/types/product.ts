export type VendorListingSummary = {
  id: number;
  vendor: string;
  vendor_product_name: string;
  product_url: string;
  current_price: number;
  raw_price: string;
  currency: string;
  rating: number | null;
  review_count: number;
  delivery_info: string | null;
  availability_status: string;
  sentiment_score: number | null;
  last_seen_at: string;
};

export type ProductSummary = {
  id: number;
  canonical_name: string;
  brand: string | null;
  category: string | null;
  model_number: string | null;
  image_url: string | null;
  best_price: number | null;
  best_vendor: string | null;
  best_product_url: string | null;
  vendor_count: number;
};

export type ProductDetail = ProductSummary & {
  created_at: string;
  vendors: VendorListingSummary[];
  comparison: ComparisonResponse;
  offline_quotes: OfflineQuote[];
};

export type SearchResponse = {
  query: string;
  results: ProductSummary[];
  search_diagnostics: SearchDiagnosticsSummary | null;
};

export type SuggestionStorePreview = {
  vendor: string;
  price: number | null;
};

export type SearchSuggestion = {
  id: number;
  canonical_name: string;
  brand: string | null;
  category: string | null;
  image_url: string | null;
  best_price: number | null;
  best_vendor: string | null;
  vendor_count: number;
  live_store_count: number;
  source_stores: SuggestionStorePreview[];
};

export type SearchSuggestionsResponse = {
  query: string;
  sources: string[];
  results: SearchSuggestion[];
};

export type PincodeVerificationResponse = {
  pincode: string;
  district: string;
  state: string;
  office_name: string | null;
  location: string;
};

export type BestOption = {
  vendor: string;
  price: number;
  product_url: string;
  vendor_product_id: number;
};

export type ComparisonRankingMode =
  | "recommended"
  | "cheapest"
  | "fastest_delivery"
  | "best_value"
  | "best_reviewed";

export type DecisionHighlight = {
  vendor: string;
  vendor_product_id: number;
  product_url: string;
  source_type: string;
  price: number;
  landed_price: number;
  price_confidence: number;
  estimated_delivery_days: number | null;
  sentiment_score: number | null;
  detail: string | null;
};

export type DecisionSummary = {
  recommended: DecisionHighlight;
  recommendation_reason: string;
  cheapest_offer: DecisionHighlight | null;
  best_landed_price: DecisionHighlight | null;
  fastest_delivery: DecisionHighlight | null;
  best_reviewed: DecisionHighlight | null;
  best_sentiment: DecisionHighlight | null;
  best_value: DecisionHighlight | null;
  best_for_location: DecisionHighlight | null;
  location_context_applied: boolean;
  location_context_label: string | null;
  warnings: string[];
};

export type LatestPurchaseSummary = {
  supplier_name: string;
  unit_price: number;
  quantity: number;
  shipping_cost: number;
  total_price: number;
  buyer_location: string | null;
  delivery_days: number | null;
  purchased_at: string;
};

export type QuoteStatus =
  | "draft"
  | "submitted"
  | "approved"
  | "purchased"
  | "closed"
  | "expired";

export type BenchmarkSummary = {
  min_price: number;
  max_price: number;
  average_price: number;
  median_price: number;
  offer_count: number;
  last_purchase_unit_price: number | null;
};

export type SearchFilterSummary = {
  key: string;
  label: string;
  detail: string;
  source: string | null;
  active: boolean;
  removed_count: number;
};

export type SearchDiagnosticsSummary = {
  query: string;
  source_profile: string;
  location: string | null;
  pincode: string | null;
  intent: string | null;
  corrected_query: string | null;
  source_groups_checked: string[];
  coverage_status: string | null;
  match_confidence: number | null;
  sources_checked: string[];
  observed_offer_count: number;
  matched_offer_count: number;
  filters: SearchFilterSummary[];
};

export type ComparisonItem = {
  vendor_product_id: number;
  vendor: string;
  vendor_domain: string | null;
  vendor_is_trusted: boolean;
  product_name: string;
  price: number;
  displayed_price: number;
  raw_price: string | null;
  rating: number | null;
  review_count: number;
  delivery_info: string | null;
  sentiment_score: number | null;
  availability_status: string;
  product_url: string;
  shipping_cost: number | null;
  estimated_delivery_days: number | null;
  seller_location: string | null;
  seller_pincode: string | null;
  landed_price: number;
  source_type: string;
  price_verification_status: string;
  price_confidence: number;
  verified_price: number | null;
  price_verified_at: string | null;
  last_seen_at: string | null;
  reasonability_label: string;
  delta_from_median_percent: number | null;
  delta_from_last_purchase_percent: number | null;
};

export type RelatedStoreLink = {
  vendor: string;
  product_url: string;
  search_label: string;
  note: string | null;
};

export type ProductGroupSummary = {
  label: string;
  relation: string;
  confidence: number;
  result_count: number;
  results: ComparisonItem[];
};

export type ComparisonResponse = {
  query: string;
  ranking_mode: ComparisonRankingMode;
  product_id: number | null;
  product_name: string | null;
  product_image_url: string | null;
  location: string | null;
  pincode: string | null;
  latest_purchase: LatestPurchaseSummary | null;
  benchmark: BenchmarkSummary | null;
  best_option: BestOption | null;
  decision_summary: DecisionSummary | null;
  results: ComparisonItem[];
  product_groups: ProductGroupSummary[];
  related_store_results: ComparisonItem[];
  related_store_links: RelatedStoreLink[];
  search_diagnostics: SearchDiagnosticsSummary | null;
};

export type ComparisonProgressResponse = {
  progress_id: string;
  offer_count: number;
  status: string;
};

export type OfflineQuote = {
  id: number;
  product_id: number;
  supplier_name: string;
  quoted_price: number;
  shipping_cost: number;
  total_price: number;
  currency: string;
  seller_location: string | null;
  pincode: string | null;
  estimated_delivery_days: number | null;
  contact_name: string | null;
  contact_phone: string | null;
  quote_reference: string | null;
  status: QuoteStatus;
  supplier_score: number | null;
  notes: string | null;
  valid_until: string | null;
  days_until_expiry: number | null;
  is_expiring_soon: boolean;
  is_active: boolean;
  submitted_at: string | null;
  approved_at: string | null;
  closed_at: string | null;
  created_at: string;
};

export type PurchaseRecord = {
  id: number;
  product_id: number;
  supplier_name: string;
  unit_price: number;
  quantity: number;
  shipping_cost: number;
  total_price: number;
  buyer_location: string | null;
  pincode: string | null;
  delivery_days: number | null;
  reference_number: string | null;
  notes: string | null;
  related_quote_ids: number[];
  market_best_price: number | null;
  market_median_price: number | null;
  delta_from_market_best_percent: number | null;
  delta_from_market_median_percent: number | null;
  purchased_at: string;
  created_at: string;
};

export type ProcurementStatusCount = {
  status: QuoteStatus;
  count: number;
};

export type SupplierCompetitivenessSummary = {
  supplier_name: string;
  quote_count: number;
  purchase_count: number;
  best_quote_total_price: number | null;
  average_quote_total_price: number | null;
  average_purchase_unit_price: number | null;
  latest_quote_status: QuoteStatus | null;
  competitiveness_label: string;
};

export type PurchaseBenchmarkSummary = {
  supplier_name: string;
  purchased_at: string;
  unit_price: number;
  total_price: number;
  market_best_price: number | null;
  market_median_price: number | null;
  delta_from_market_best_percent: number | null;
  delta_from_market_median_percent: number | null;
  benchmark_note: string;
};

export type ProcurementSummary = {
  product_id: number;
  product_name: string;
  active_quote_count: number;
  expiring_quote_count: number;
  approved_quote_count: number;
  quote_status_breakdown: ProcurementStatusCount[];
  active_quotes: OfflineQuote[];
  expiring_quotes: OfflineQuote[];
  supplier_competitiveness: SupplierCompetitivenessSummary[];
  latest_purchase_benchmark: PurchaseBenchmarkSummary | null;
};

export type VendorStatus = {
  id: number;
  name: string;
  base_url: string;
  is_active: boolean;
  scrape_strategy: string;
  last_status: string | null;
  last_scraped_at: string | null;
};

export type ScrapeJob = {
  id: string;
  query: string;
  status: string;
  result_count: number;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
};
