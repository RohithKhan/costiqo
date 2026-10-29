import { formatVendorLabel } from "../lib/displayText";

type VendorBadgeProps = {
  vendor: string;
  href?: string;
  trusted?: boolean;
};

function resolveVendorIcon(vendor: string, href?: string) {
  if (href && !href.startsWith("#")) {
    try {
      const hostname = new URL(href).hostname;
      return `https://www.google.com/s2/favicons?domain=${hostname}&sz=64`;
    } catch {
      return null;
    }
  }

  const fallbackHost = vendor
    .toLowerCase()
    .replace(/^offline\s·\s/, "")
    .replace(/\s+/g, "");
  return fallbackHost ? `https://www.google.com/s2/favicons?domain=${fallbackHost}.com&sz=64` : null;
}

export function VendorBadge({ vendor, href, trusted = false }: VendorBadgeProps) {
  const icon = resolveVendorIcon(vendor, href);
  const label = formatVendorLabel(vendor);
  const content = (
    <>
      {icon ? <img className="vendor-badge__icon" src={icon} alt="" aria-hidden="true" /> : null}
      <span>{label}</span>
      {trusted ? <span className="vendor-badge__trust">Trusted</span> : null}
    </>
  );

  if (href && !href.startsWith("#")) {
    return (
      <a
        className="vendor-badge vendor-badge--interactive"
        href={href}
        target="_blank"
        rel="noreferrer"
      >
        {content}
      </a>
    );
  }

  return <span className="vendor-badge">{content}</span>;
}
