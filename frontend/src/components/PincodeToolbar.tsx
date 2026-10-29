type PincodeToolbarProps = {
  pincode?: string;
  onPincodeChange: (value: string) => void;
  onApplyPincode?: () => void;
  onClearPincode?: () => void;
  isApplyingPincode?: boolean;
  pincodeInvalid?: boolean;
};

export function PincodeToolbar({
  pincode = "",
  onPincodeChange,
  onApplyPincode,
  onClearPincode,
  isApplyingPincode = false,
  pincodeInvalid = false,
}: PincodeToolbarProps) {
  const showClearButton = Boolean(pincode && onClearPincode);

  return (
    <div className={`pincode-toolbar ${pincodeInvalid ? "pincode-toolbar--invalid" : ""}`}>
      <span className="pincode-toolbar__field">
        <input
          className="search-input pincode-toolbar__input"
          value={pincode}
          onChange={(event) => onPincodeChange(event.target.value.replace(/\D/g, "").slice(0, 6))}
          placeholder="Pincode"
          inputMode="numeric"
          pattern="[0-9]{6}"
          aria-label="Indian pincode"
          aria-invalid={pincodeInvalid}
        />
        {showClearButton ? (
          <button
            type="button"
            className="pincode-toolbar__clear"
            onClick={onClearPincode}
            aria-label="Clear pincode"
          >
            x
          </button>
        ) : null}
      </span>
      <button
        type="button"
        className="secondary-button pincode-toolbar__apply"
        onClick={onApplyPincode}
        disabled={isApplyingPincode}
      >
        {isApplyingPincode ? "..." : "Apply"}
      </button>
    </div>
  );
}
