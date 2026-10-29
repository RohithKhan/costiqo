import { Link } from "react-router-dom";
import { CostiqoBrand } from "./CostiqoBrand";

export function SiteFooter() {
  return (
    <footer className="costiqo-footer" aria-label="Site footer">
      <div className="costiqo-footer__inner">
        <div className="costiqo-footer__brand-col">
          <CostiqoBrand size="md" />
          <p className="costiqo-footer__tagline">
            Smart, transparent product price comparison across leading verified marketplaces and retail stores.
          </p>
          <p className="costiqo-footer__copy-meta">
            © {new Date().getFullYear()} Costiqo. Live price data updated dynamically from verified vendors.
          </p>
        </div>

        <div className="costiqo-footer__links-col">
          <div className="costiqo-footer__group">
            <h4 className="costiqo-footer__heading">Navigation</h4>
            <ul className="costiqo-footer__list">
              <li>
                <Link to="/">Home & Search</Link>
              </li>
              <li>
                <Link to="/search?q=Raspberry+Pi+4">Electronics & Dev</Link>
              </li>
              <li>
                <Link to="/account">Saved Bookmarks</Link>
              </li>
            </ul>
          </div>

          <div className="costiqo-footer__group">
            <h4 className="costiqo-footer__heading">Supported Vendors</h4>
            <ul className="costiqo-footer__list">
              <li>
                <span>Amazon India</span>
              </li>
              <li>
                <span>Flipkart</span>
              </li>
              <li>
                <span>Croma & Reliance</span>
              </li>
              <li>
                <span>Robu, IBO & Moglix</span>
              </li>
            </ul>
          </div>

          <div className="costiqo-footer__group">
            <h4 className="costiqo-footer__heading">Transparency</h4>
            <ul className="costiqo-footer__list">
              <li>
                <span>Landed price calculations</span>
              </li>
              <li>
                <span>Real-time stock validation</span>
              </li>
              <li>
                <span>No sponsored distortion</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </footer>
  );
}
