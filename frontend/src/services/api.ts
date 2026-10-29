import axios from "axios";

import type { AlertRule, SavedProduct, SavedSearch } from "../types/account";
import type { AuthResponse, AuthUser } from "../types/auth";
import type { ProductHistoryResponse } from "../types/history";
import type {
  ComparisonResponse,
  ComparisonProgressResponse,
  ComparisonRankingMode,
  OfflineQuote,
  PincodeVerificationResponse,
  ProductDetail,
  ProcurementSummary,
  PurchaseRecord,
  ScrapeJob,
  SearchResponse,
  SearchSuggestionsResponse,
  QuoteStatus,
  VendorStatus,
} from "../types/product";
import type { ProductSentimentResponse, ReviewsResponse } from "../types/review";

const tokenStorageKey = "costiqo-token";
const userStorageKey = "costiqo-user";
const defaultApiHost =
  typeof window !== "undefined" ? window.location.hostname : "localhost";
const apiBaseUrl =
  import.meta.env.VITE_API_BASE_URL ?? `http://${defaultApiHost}:7070/api/v1`;
const backendOrigin = apiBaseUrl.replace(/\/api\/v1\/?$/, "");
const warmupFreshWindowMs = 2 * 60 * 1000;

let lastBackendWakeAt = 0;
let backendWakePromise: Promise<void> | null = null;

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
  timeout: 65000,
  headers: {
    "Content-Type": "application/json",
  },
});

const healthClient = axios.create({
  baseURL: backendOrigin,
  timeout: 20_000,
});

function isAuthUser(value: unknown): value is AuthUser {
  if (!value || typeof value !== "object") {
    return false;
  }
  const user = value as Partial<AuthUser>;
  return (
    typeof user.id === "number" &&
    typeof user.name === "string" &&
    typeof user.email === "string" &&
    typeof user.role === "string" &&
    typeof user.created_at === "string"
  );
}

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(tokenStorageKey);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const authStorage = {
  getToken: () => localStorage.getItem(tokenStorageKey),
  setToken: (token: string) => localStorage.setItem(tokenStorageKey, token),
  clearToken: () => {
    localStorage.removeItem(tokenStorageKey);
    localStorage.removeItem(userStorageKey);
  },
  getUser: (token: string) => {
    const rawUser = localStorage.getItem(userStorageKey);
    if (!rawUser) {
      return null;
    }
    try {
      const parsed = JSON.parse(rawUser) as { token?: unknown; user?: unknown };
      if (parsed.token === token && isAuthUser(parsed.user)) {
        return parsed.user;
      }
    } catch {
      localStorage.removeItem(userStorageKey);
    }
    return null;
  },
  setUser: (token: string, user: AuthUser) => {
    localStorage.setItem(userStorageKey, JSON.stringify({ token, user }));
  },
};

async function wakeBackend(force = false) {
  const now = Date.now();
  if (!force && now - lastBackendWakeAt < warmupFreshWindowMs) {
    return;
  }
  if (backendWakePromise) {
    return backendWakePromise;
  }

  backendWakePromise = healthClient
    .get("/health")
    .then(() => {
      lastBackendWakeAt = Date.now();
    })
    .catch(() => undefined)
    .finally(() => {
      backendWakePromise = null;
    });

  return backendWakePromise;
}

export const api = {
  wakeBackend,
  async searchProducts(query: string) {
    await wakeBackend();
    const response = await apiClient.get<SearchResponse>("/products/search", {
      params: { q: query },
    });
    return response.data;
  },
  async fetchSearchSuggestions(
    query: string,
    options?: { location?: string; pincode?: string; limit?: number; },
  ) {
    await wakeBackend();
    const response = await apiClient.get<SearchSuggestionsResponse>("/products/suggestions", {
      params: {
        q: query,
        location: options?.location || undefined,
        pincode: options?.pincode || undefined,
        limit: options?.limit || undefined,
      },
    });
    return response.data;
  },
  async verifyPincode(pincode: string) {
    await wakeBackend();
    const response = await apiClient.get<PincodeVerificationResponse>("/locations/pincode", {
      params: { pincode },
    });
    return response.data;
  },
  async fetchComparison(
    query: string,
    options?: { location?: string; pincode?: string; rankingMode?: ComparisonRankingMode; progressId?: string; },
  ) {
    await wakeBackend();
    const response = await apiClient.get<ComparisonResponse>("/comparisons", {
      params: {
        q: query,
        location: options?.location || undefined,
        pincode: options?.pincode || undefined,
        ranking_mode: options?.rankingMode || undefined,
        progress_id: options?.progressId || undefined,
      },
    });
    return response.data;
  },
  async fetchComparisonProgress(progressId: string) {
    const response = await apiClient.get<ComparisonProgressResponse>(`/comparisons/progress/${progressId}`);
    return response.data;
  },
  async fetchProductDetail(
    productId: number,
    options?: { location?: string; pincode?: string; rankingMode?: ComparisonRankingMode; },
  ) {
    const response = await apiClient.get<ProductDetail>(`/products/${productId}`, {
      params: {
        location: options?.location || undefined,
        pincode: options?.pincode || undefined,
        ranking_mode: options?.rankingMode || undefined,
      },
    });
    return response.data;
  },
  async fetchProductHistory(productId: number) {
    const response = await apiClient.get<ProductHistoryResponse>(
      `/products/${productId}/history`,
    );
    return response.data;
  },
  async fetchReviews(productId: number) {
    const response = await apiClient.get<ReviewsResponse>(`/products/${productId}/reviews`);
    return response.data;
  },
  async fetchSentiment(productId: number) {
    const response = await apiClient.get<ProductSentimentResponse>(
      `/products/${productId}/sentiment`,
    );
    return response.data;
  },
  async login(payload: { username: string; password: string; }) {
    const response = await apiClient.post<AuthResponse>("/auth/login", payload);
    return response.data;
  },
  async register(payload: { name: string; email: string; password: string; }) {
    const response = await apiClient.post<AuthResponse>("/auth/register", payload);
    return response.data;
  },
  async fetchMe(options?: { signal?: AbortSignal }) {
    const response = await apiClient.get<AuthUser>("/auth/me", {
      signal: options?.signal,
      timeout: 20_000,
    });
    return response.data;
  },
  async fetchSavedProducts() {
    const response = await apiClient.get<SavedProduct[]>("/me/saved-products");
    return response.data;
  },
  async saveProduct(payload: { product_name: string; product_url: string; }) {
    const response = await apiClient.post<SavedProduct>("/me/saved-products", payload);
    return response.data;
  },
  async removeSavedProduct(savedProductId: number) {
    await apiClient.delete(`/me/saved-products/${savedProductId}`);
  },
  async changePassword(payload: { current_password: string; new_password: string; }) {
    await apiClient.patch("/me/password", payload);
  },
  async deleteAccount() {
    await apiClient.delete("/me/account");
  },
  async fetchSavedSearches() {
    const response = await apiClient.get<SavedSearch[]>("/me/saved-searches");
    return response.data;
  },
  async saveSearch(payload: { query: string; location?: string; pincode?: string; }) {
    const response = await apiClient.post<SavedSearch>("/me/saved-searches", payload);
    return response.data;
  },
  async removeSavedSearch(savedSearchId: number) {
    await apiClient.delete(`/me/saved-searches/${savedSearchId}`);
  },
  async fetchAlerts() {
    const response = await apiClient.get<AlertRule[]>("/me/alerts");
    return response.data;
  },
  async createAlert(payload: {
    product_id?: number;
    query?: string;
    location?: string;
    pincode?: string;
    target_price?: number;
    trigger_type?: string;
  }) {
    const response = await apiClient.post<AlertRule>("/me/alerts", payload);
    return response.data;
  },
  async updateAlert(alertRuleId: number, payload: { is_active?: boolean; target_price?: number; }) {
    const response = await apiClient.patch<AlertRule>(`/me/alerts/${alertRuleId}`, payload);
    return response.data;
  },
  async removeAlert(alertRuleId: number) {
    await apiClient.delete(`/me/alerts/${alertRuleId}`);
  },
  async fetchAdminVendors() {
    const response = await apiClient.get<VendorStatus[]>("/admin/vendors");
    return response.data;
  },
  async triggerScrape(query: string) {
    const response = await apiClient.post<ScrapeJob>("/admin/scrape", { query });
    return response.data;
  },
  async fetchJob(jobId: string) {
    const response = await apiClient.get<ScrapeJob>(`/admin/jobs/${jobId}`);
    return response.data;
  },
  async createOfflineQuote(payload: {
    product_id: number;
    supplier_name: string;
    quoted_price: number;
    shipping_cost?: number;
    seller_location?: string;
    pincode?: string;
    estimated_delivery_days?: number;
    contact_name?: string;
    contact_phone?: string;
    quote_reference?: string;
    status?: QuoteStatus;
    supplier_score?: number;
    notes?: string;
    valid_until?: string;
  }) {
    const response = await apiClient.post<OfflineQuote>("/admin/offline-quotes", payload);
    return response.data;
  },
  async updateOfflineQuote(
    quoteId: number,
    payload: {
      status?: QuoteStatus;
      valid_until?: string | null;
      is_active?: boolean;
      notes?: string;
      supplier_score?: number;
      quote_reference?: string;
    },
  ) {
    const response = await apiClient.patch<OfflineQuote>(`/admin/offline-quotes/${quoteId}`, payload);
    return response.data;
  },
  async createPurchaseRecord(payload: {
    product_id: number;
    supplier_name: string;
    unit_price: number;
    quantity?: number;
    shipping_cost?: number;
    buyer_location?: string;
    pincode?: string;
    delivery_days?: number;
    reference_number?: string;
    related_quote_ids?: number[];
    notes?: string;
  }) {
    const response = await apiClient.post<PurchaseRecord>("/admin/purchases", payload);
    return response.data;
  },
  async fetchProcurementSummary(productId: number) {
    const response = await apiClient.get<ProcurementSummary>("/admin/procurement/summary", {
      params: { product_id: productId },
    });
    return response.data;
  },
  async fetchOfflineQuotes(productId: number) {
    const response = await apiClient.get<OfflineQuote[]>(`/products/${productId}/offline-quotes`);
    return response.data;
  },
  async fetchPurchaseRecords(productId: number) {
    const response = await apiClient.get<PurchaseRecord[]>(`/products/${productId}/purchases`);
    return response.data;
  },
};
