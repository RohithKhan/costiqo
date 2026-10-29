import { FormEvent } from "react";

type PincodeBarProps = {
  pincode: string;
  onPincodeChange: (value: string) => void;
  onApply: () => void;
  onClear: () => void;
  locationLabel?: string | null;
  error?: string | null;
  isApplying?: boolean;
};

export function PincodeBar({
  pincode,
  onPincodeChange,
  onApply,
  onClear,
  error,
  isApplying = false,
}: PincodeBarProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onApply();
  }

  return (
    <form className="pincode-bar" onSubmit={handleSubmit}>
      <span className="pincode-field">
        <input
          className="search-input pincode-input"
          value={pincode}
          onChange={(event) => onPincodeChange(event.target.value.replace(/\D/g, "").slice(0, 6))}
          placeholder="Pincode"
          inputMode="numeric"
          pattern="[0-9]{6}"
          aria-label="Indian pincode"
          aria-invalid={Boolean(error)}
          title={error ?? "Indian pincode"}
        />
        {pincode ? (
          <button type="button" className="pincode-field__clear" onClick={onClear} aria-label="Clear pincode">
            x
          </button>
        ) : null}
      </span>
      <button type="submit" className="secondary-button" disabled={isApplying}>
        {isApplying ? "Checking" : "Apply"}
      </button>
    </form>
  );
}
