import { useEffect, useState } from "react";

type OfferSearchLoadingProps = {
  active: boolean;
  offerCount: number;
  complete?: boolean;
};

const STORES = [
  { name: "Amazon", delay: "0s" },
  { name: "Flipkart", delay: "0.2s" },
  { name: "Croma", delay: "0.4s" },
  { name: "Robu", delay: "0.6s" },
  { name: "Local Sellers", delay: "0.8s" },
];

const stages = [
  "Connecting to verified retail networks...",
  "Scanning hardware & electronics listings...",
  "Comparing live store prices & landed shipping...",
  "Finalizing best value recommendations...",
];

export function OfferSearchLoading({
  active,
  offerCount,
  complete = false,
}: OfferSearchLoadingProps) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!active) {
      setTick(0);
      return undefined;
    }

    const interval = window.setInterval(() => setTick((current) => current + 1), 320);
    return () => window.clearInterval(interval);
  }, [active]);

  const stageFromCount = offerCount >= 60 ? 3 : offerCount >= 30 ? 2 : offerCount >= 10 ? 1 : 0;
  const stageFromTick = Math.min(stages.length - 1, Math.floor(tick / 4));
  const stageIndex = complete
    ? stages.length - 1
    : offerCount > 0
      ? stageFromCount
      : stageFromTick;

  const progressFromCount = Math.min(94, 12 + Math.round((offerCount / 100) * 82));
  const progressFromTick = Math.min(94, 12 + tick * 5);
  const progress = complete
    ? 100
    : offerCount > 0
      ? progressFromCount
      : progressFromTick;

  if (!active) {
    return null;
  }

  return (
    <div className="offer-loading" role="status" aria-live="polite">
      <div className="offer-loading__card">
        {/* Brand Mark with scanning ring */}
        <div className="offer-loading__brand-wrap" aria-hidden="true">
          <div className="offer-loading__pulse-ring" />
          <div className="offer-loading__logo">
            <img
              src="/costiqo-logo.png"
              alt="Costiqo"
              style={{ width: "26px", height: "26px", objectFit: "contain", borderRadius: "6px" }}
            />
          </div>
        </div>

        <div className="offer-loading__headline">
          <h3>Searching verified stores</h3>
          <p className="offer-loading__subtext">
            {offerCount > 0
              ? `Found ${offerCount} offers across online & local dealers...`
              : "Scanning verified retailers for the lowest landed prices..."}
          </p>
        </div>

        {/* Store nodes animation */}
        <div className="offer-loading__nodes" aria-hidden="true">
          {STORES.map((s, idx) => (
            <span
              key={s.name}
              className={`offer-loading__node ${idx <= stageIndex + 1 ? "active" : ""}`}
              style={{ animationDelay: s.delay }}
            >
              {s.name}
            </span>
          ))}
        </div>

        {/* Progress bar */}
        <div className="offer-loading__bar" aria-hidden="true">
          <span style={{ width: `${progress}%` }} />
        </div>

        {/* Stage list */}
        <div className="offer-loading__stages">
          {stages.map((stage, index) => (
            <div
              className={`offer-loading__stage ${
                index < stageIndex ? "done" : index === stageIndex ? "active" : ""
              }`}
              key={stage}
            >
              <i aria-hidden="true" />
              <span>{stage}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
