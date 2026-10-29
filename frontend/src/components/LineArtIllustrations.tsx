import React from "react";

/**
 * Premium, bespoke SVG Line-Art illustrations for Costiqo's aesthetic identity.
 * Features delicate strokes, flowing geometric contours, and shopping/technology motifs.
 */

interface IllustrationProps {
  className?: string;
  width?: number | string;
  height?: number | string;
}

export function HeroComparisonIllustration({
  className = "",
  width = "100%",
  height = "auto",
}: IllustrationProps) {
  return (
    <svg
      className={`line-art line-art--hero ${className}`}
      viewBox="0 0 640 440"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ width, height, overflow: "visible" }}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="coralGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38000A" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#8E1422" stopOpacity="0.6" />
        </linearGradient>
        <linearGradient id="goldGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#D4A373" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#CCD5AE" stopOpacity="0.4" />
        </linearGradient>
        <linearGradient id="softFillGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#FBF4F5" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0.2" />
        </linearGradient>
      </defs>

      {/* Decorative background grid and orbital flow lines */}
      <circle cx="320" cy="220" r="190" stroke="#EAE5E0" strokeWidth="1" strokeDasharray="6 6" />
      <circle cx="320" cy="220" r="130" stroke="#F0ECE8" strokeWidth="1" />
      <path
        d="M 60 220 C 180 80, 460 80, 580 220 C 460 360, 180 360, 60 220 Z"
        stroke="url(#coralGradient)"
        strokeWidth="1.2"
        strokeOpacity="0.3"
      />

      {/* Central Device / Scanner Podium */}
      <g transform="translate(220, 100)">
        {/* Sleek Floating Device Outline */}
        <rect
          x="0"
          y="0"
          width="200"
          height="240"
          rx="24"
          fill="url(#softFillGradient)"
          stroke="#38000A"
          strokeWidth="2"
        />
        {/* Device screen header */}
        <line x1="20" y1="36" x2="100" y2="36" stroke="#8E1422" strokeWidth="3" strokeLinecap="round" />
        <circle cx="170" cy="36" r="5" stroke="#38000A" strokeWidth="1.5" />

        {/* Live Scan Rays */}
        <path d="M 20 70 L 180 70" stroke="#E29578" strokeWidth="1.5" strokeDasharray="4 4" />
        <path d="M 20 120 L 180 120" stroke="#8E1422" strokeWidth="1" strokeOpacity="0.4" />

        {/* Dynamic Mini Price Tag floating inside screen */}
        <rect x="24" y="90" width="152" height="48" rx="12" fill="#FFFFFF" stroke="#38000A" strokeWidth="1.2" />
        <circle cx="48" cy="114" r="8" stroke="#8E1422" strokeWidth="1.5" />
        <line x1="68" y1="108" x2="130" y2="108" stroke="#38000A" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="68" y1="120" x2="105" y2="120" stroke="#718096" strokeWidth="1.5" strokeLinecap="round" />

        {/* Bottom spark indicator */}
        <circle cx="100" cy="180" r="18" stroke="#8E1422" strokeWidth="1.5" />
        <path d="M 100 170 L 100 190 M 90 180 L 110 180" stroke="#8E1422" strokeWidth="1.5" />
      </g>

      {/* Left Satellite - Marketplace Seller Card (Amazon/Flipkart motif) */}
      <g transform="translate(60, 140)">
        <rect x="0" y="0" width="130" height="110" rx="16" fill="#FFFFFF" stroke="#B08968" strokeWidth="1.5" />
        <circle cx="30" cy="30" r="12" stroke="#B08968" strokeWidth="1.5" />
        <line x1="50" y1="26" x2="105" y2="26" stroke="#4A5568" strokeWidth="2" strokeLinecap="round" />
        <line x1="50" y1="36" x2="85" y2="36" stroke="#A0AEC0" strokeWidth="1.5" strokeLinecap="round" />

        {/* Price tag */}
        <line x1="20" y1="70" x2="80" y2="70" stroke="#38000A" strokeWidth="3" strokeLinecap="round" />
        <rect x="20" y="82" width="60" height="14" rx="4" fill="#FBF4F5" stroke="#8E1422" strokeWidth="0.8" />

        {/* Connection flow line to center */}
        <path
          d="M 130 55 C 160 55, 180 80, 220 120"
          stroke="#B08968"
          strokeWidth="1.5"
          strokeDasharray="5 5"
        />
      </g>

      {/* Right Satellite - Best Verified Offer & Savings Sparkle */}
      <g transform="translate(450, 120)">
        <rect x="0" y="0" width="140" height="130" rx="18" fill="#FFFFFF" stroke="#38000A" strokeWidth="1.8" />
        {/* Crown/Verified badge symbol */}
        <circle cx="34" cy="34" r="14" fill="#FBF4F5" stroke="#38000A" strokeWidth="1.5" />
        <path d="M 28 34 L 32 38 L 40 30" stroke="#2E7D5B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />

        <line x1="58" y1="28" x2="115" y2="28" stroke="#38000A" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="58" y1="40" x2="95" y2="40" stroke="#2E7D5B" strokeWidth="2" strokeLinecap="round" />

        {/* Best Price highlight */}
        <rect x="18" y="66" width="104" height="44" rx="10" fill="#F3FAF6" stroke="#2E7D5B" strokeWidth="1.2" />
        <line x1="30" y1="84" x2="85" y2="84" stroke="#2E7D5B" strokeWidth="3" strokeLinecap="round" />
        <line x1="30" y1="96" x2="65" y2="96" stroke="#718096" strokeWidth="1.5" strokeLinecap="round" />

        {/* Connection flow line to center */}
        <path
          d="M 0 65 C -20 65, -30 90, -30 140"
          stroke="#2E7D5B"
          strokeWidth="1.5"
          strokeDasharray="4 4"
        />
      </g>

      {/* Geometric Floating Accent Elements */}
      <polygon points="170,80 185,90 175,105 160,95" stroke="#D4A373" strokeWidth="1.2" fill="none" />
      <circle cx="480" cy="80" r="6" stroke="#8E1422" strokeWidth="1.5" />
      <path d="M 520 320 L 535 305 M 520 305 L 535 320" stroke="#38000A" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M 120 330 L 130 315 L 140 330 Z" stroke="#8E1422" strokeWidth="1.2" fill="none" />
    </svg>
  );
}

export function PriceComparisonLineArt({
  className = "",
  width = 72,
  height = 72,
}: IllustrationProps) {
  return (
    <svg
      className={`line-art ${className}`}
      width={width}
      height={height}
      viewBox="0 0 72 72"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <circle cx="36" cy="36" r="30" stroke="#E2DCD5" strokeWidth="1.2" />
      <path
        d="M 18 46 L 28 36 L 40 42 L 54 24"
        stroke="#38000A"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="54" cy="24" r="3.5" fill="#8E1422" stroke="#38000A" strokeWidth="1" />
      <line x1="22" y1="52" x2="50" y2="52" stroke="#A0AEC0" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M 44 24 L 54 24 L 54 34" stroke="#8E1422" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function MultiStoreLineArt({
  className = "",
  width = 72,
  height = 72,
}: IllustrationProps) {
  return (
    <svg
      className={`line-art ${className}`}
      width={width}
      height={height}
      viewBox="0 0 72 72"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <circle cx="36" cy="36" r="30" stroke="#E2DCD5" strokeWidth="1.2" />
      <rect x="22" y="24" width="28" height="32" rx="6" stroke="#38000A" strokeWidth="2" fill="#FFFFFF" />
      <path d="M 28 24 C 28 18, 44 18, 44 24" stroke="#8E1422" strokeWidth="2" strokeLinecap="round" />
      <line x1="30" y1="34" x2="42" y2="34" stroke="#38000A" strokeWidth="2" strokeLinecap="round" />
      <line x1="30" y1="42" x2="38" y2="42" stroke="#A0AEC0" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function DeliveryTrustLineArt({
  className = "",
  width = 72,
  height = 72,
}: IllustrationProps) {
  return (
    <svg
      className={`line-art ${className}`}
      width={width}
      height={height}
      viewBox="0 0 72 72"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <circle cx="36" cy="36" r="30" stroke="#E2DCD5" strokeWidth="1.2" />
      <path
        d="M 36 18 C 29 18 24 23 24 30 C 24 40 36 52 36 52 C 36 52 48 40 48 30 C 48 23 43 18 36 18 Z"
        stroke="#38000A"
        strokeWidth="2"
        fill="#FFFFFF"
      />
      <circle cx="36" cy="30" r="4.5" stroke="#8E1422" strokeWidth="2" fill="#FBF4F5" />
    </svg>
  );
}

export function VerifiedSavingsLineArt({
  className = "",
  width = 72,
  height = 72,
}: IllustrationProps) {
  return (
    <svg
      className={`line-art ${className}`}
      width={width}
      height={height}
      viewBox="0 0 72 72"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <circle cx="36" cy="36" r="30" stroke="#E2DCD5" strokeWidth="1.2" />
      <path
        d="M 36 20 L 46 25 L 46 37 C 46 45 42 50 36 53 C 30 50 26 45 26 37 L 26 25 Z"
        stroke="#38000A"
        strokeWidth="2"
        fill="#FFFFFF"
      />
      <path
        d="M 31 36 L 35 40 L 42 32"
        stroke="#2E7D5B"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function EmptySearchLineArt({
  className = "",
  width = 160,
  height = 160,
}: IllustrationProps) {
  return (
    <svg
      className={`line-art ${className}`}
      width={width}
      height={height}
      viewBox="0 0 160 160"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <circle cx="80" cy="80" r="70" stroke="#ECE8E4" strokeWidth="1" strokeDasharray="4 4" />
      <circle cx="70" cy="70" r="36" stroke="#38000A" strokeWidth="2.5" fill="#FAF7F5" />
      <line x1="96" y1="96" x2="124" y2="124" stroke="#38000A" strokeWidth="3.5" strokeLinecap="round" />
      <circle cx="70" cy="70" r="16" stroke="#B08968" strokeWidth="1.5" strokeDasharray="3 3" />
      <line x1="58" y1="70" x2="82" y2="70" stroke="#8E1422" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
