import { Link } from "react-router-dom";

type CostiqoBrandProps = {
  className?: string;
  size?: "sm" | "md" | "lg";
  to?: string;
};

export function CostiqoBrand({ className = "", size = "md", to = "/" }: CostiqoBrandProps) {
  return (
    <Link
      className={`proto-brand proto-brand--${size} ${className}`.trim()}
      to={to}
      aria-label="Costiqo Home"
    >
      <span className="proto-brand__logo-mark" aria-hidden="true">
        <img
          src="/costiqo-logo.png"
          alt="Costiqo Logo"
          className="proto-brand__img"
        />
      </span>
      <span className="proto-brand__name">Costiqo</span>
    </Link>
  );
}
