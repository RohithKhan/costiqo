export type HistoryPoint = {
  timestamp: string;
  price: number;
};

export type VendorHistorySeries = {
  vendor_product_id: number;
  vendor: string;
  points: HistoryPoint[];
};

export type ProductHistoryResponse = {
  product_id: number;
  product_name: string;
  history: VendorHistorySeries[];
};
