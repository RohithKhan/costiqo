export type ReviewItem = {
  id: number;
  vendor: string;
  title: string | null;
  body: string;
  rating: number | null;
  review_date: string | null;
};

export type ReviewsResponse = {
  product_id: number;
  reviews: ReviewItem[];
};

export type SentimentBreakdown = {
  vendor_product_id: number;
  vendor: string;
  product_url: string;
  positive_count: number;
  neutral_count: number;
  negative_count: number;
  sentiment_score: number;
};

export type ProductSentimentResponse = {
  product_id: number;
  sentiment_score: number;
  positive_count: number;
  neutral_count: number;
  negative_count: number;
  vendor_breakdown: SentimentBreakdown[];
};
