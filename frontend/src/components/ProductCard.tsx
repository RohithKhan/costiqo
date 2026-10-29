import { Link } from "react-router-dom";

import type { ProductSummary } from "../types/product";
import { VendorBadge } from "./VendorBadge";

type ProductCardProps = {
  product: ProductSummary;
};

function formatCurrency(value: number | null) {
  if (value === null) {
    return "N/A";
  }
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

export function ProductCard({ product }: ProductCardProps) {
  return (
    <article className="product-card">
      <Link className="product-card__media" to={`/products/${product.id}`}>
        {product.image_url ? (
          <img src={product.image_url} alt={product.canonical_name} />
        ) : (
          <div className="product-card__placeholder">No image</div>
        )}
      </Link>
      <div className="product-card__body">
        <div className="tag-row">
          {product.category ? <span className="tag">{product.category}</span> : null}
          {product.best_vendor ? (
            <VendorBadge vendor={product.best_vendor} href={product.best_product_url ?? undefined} />
          ) : null}
        </div>
        <Link className="product-card__title" to={`/products/${product.id}`}>
          <h3>{product.canonical_name}</h3>
        </Link>
        <p className="small-copy">
          {product.brand ?? "Unknown brand"} · {product.vendor_count} vendor
          {product.vendor_count === 1 ? "" : "s"}
        </p>
        <div className="product-card__meta">
          <span className="product-card__price">{formatCurrency(product.best_price)}</span>
          <Link className="small-copy product-card__cta" to={`/products/${product.id}`}>
            View comparison
          </Link>
        </div>
      </div>
    </article>
  );
}
