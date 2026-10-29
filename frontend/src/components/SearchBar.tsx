import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";

import { useSearchSuggestions } from "../hooks/useSearch";
import { formatProductLabel, formatVendorLabel } from "../lib/displayText";
import type { SearchSuggestion } from "../types/product";

type SearchBarProps = {
  initialValue?: string;
  onSearch: (value: string) => void;
  compact?: boolean;
  pincode?: string;
  location?: string;
  onPincodeChange?: (value: string) => void;
  onApplyPincode?: () => void;
  onClearPincode?: () => void;
  isApplyingPincode?: boolean;
  pincodeInvalid?: boolean;
};

function formatCurrency(value: number | null) {
  if (value === null) {
    return "Best price unavailable";
  }
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

export function SearchBar({
  initialValue = "",
  onSearch,
  compact = false,
  pincode = "",
  location,
  onPincodeChange,
  onApplyPincode,
  onClearPincode,
  isApplyingPincode = false,
  pincodeInvalid = false,
}: SearchBarProps) {
  const [query, setQuery] = useState(() => initialValue);
  const [debouncedQuery, setDebouncedQuery] = useState(() => initialValue);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [isSuggestionOpen, setIsSuggestionOpen] = useState(false);
  const queryShellRef = useRef<HTMLDivElement | null>(null);
  const showClearButton = Boolean(pincode && onClearPincode && !compact);
  const suggestionPincode = pincode.length === 6 ? pincode : "";
  const trimmedQuery = query.trim();
  const trimmedDebouncedQuery = debouncedQuery.trim();
  const queryIsAheadOfSuggestions =
    trimmedQuery.toLowerCase() !== trimmedDebouncedQuery.toLowerCase();

  const suggestionQuery = useSearchSuggestions(trimmedDebouncedQuery, {
    location,
    pincode: suggestionPincode || undefined,
    limit: 6,
  });
  const rawSuggestions = suggestionQuery.data?.results ?? [];
  const suggestions = queryIsAheadOfSuggestions ? [] : rawSuggestions;

  useEffect(() => {
    setQuery(initialValue);
    setDebouncedQuery(initialValue);
    setActiveSuggestionIndex(-1);
    setIsSuggestionOpen(false);
  }, [initialValue]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setDebouncedQuery(query);
    }, 180);
    return () => window.clearTimeout(timeout);
  }, [query]);

  useEffect(() => {
    if (activeSuggestionIndex >= suggestions.length) {
      setActiveSuggestionIndex(-1);
    }
  }, [activeSuggestionIndex, suggestions.length]);

  const showSuggestionLoading =
    isSuggestionOpen &&
    trimmedQuery.length >= 2 &&
    (queryIsAheadOfSuggestions || suggestionQuery.isFetching || suggestionQuery.isPending);
  const showSuggestionPanel =
    isSuggestionOpen &&
    trimmedQuery.length >= 2 &&
    !showSuggestionLoading &&
    suggestions.length > 0;

  function submitSearch(value: string) {
    const trimmed = value.trim();
    if (!trimmed) {
      return;
    }
    setIsSuggestionOpen(false);
    setActiveSuggestionIndex(-1);
    onSearch(trimmed);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (showSuggestionPanel && activeSuggestionIndex >= 0 && suggestions[activeSuggestionIndex]) {
      submitSearch(suggestions[activeSuggestionIndex].canonical_name);
      setQuery(suggestions[activeSuggestionIndex].canonical_name);
      return;
    }
    submitSearch(query);
  }

  function handleSuggestionSelect(suggestion: SearchSuggestion) {
    setQuery(suggestion.canonical_name);
    submitSearch(suggestion.canonical_name);
  }

  function handleQueryKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!showSuggestionPanel || !suggestions.length) {
      if (event.key === "Escape") {
        setIsSuggestionOpen(false);
      }
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveSuggestionIndex((current) =>
        current >= suggestions.length - 1 ? 0 : current + 1,
      );
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveSuggestionIndex((current) =>
        current <= 0 ? suggestions.length - 1 : current - 1,
      );
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      setIsSuggestionOpen(false);
      setActiveSuggestionIndex(-1);
    }
  }

  return (
    <form className={`search-bar ${compact ? "search-bar--compact" : ""}`} onSubmit={handleSubmit}>
      <div
        className="search-bar__query-shell"
        ref={queryShellRef}
        onBlur={() => {
          window.requestAnimationFrame(() => {
            if (!queryShellRef.current?.contains(document.activeElement)) {
              setIsSuggestionOpen(false);
              setActiveSuggestionIndex(-1);
            }
          });
        }}
      >
        <div className="search-bar__query">
          <input
            className="search-input"
            value={query}
            onChange={(event) => {
              const nextQuery = event.target.value;
              setQuery(nextQuery);
              setIsSuggestionOpen(nextQuery.trim().length >= 2);
              setActiveSuggestionIndex(-1);
            }}
            onFocus={() => {
              if (trimmedQuery.length >= 2) {
                setIsSuggestionOpen(true);
              }
            }}
            onKeyDown={handleQueryKeyDown}
            placeholder="Search hardware, components, and electronics parts"
            aria-label="Search products"
            aria-autocomplete="list"
            aria-expanded={showSuggestionPanel}
          />
          <button type="submit" className="search-bar__icon-button" aria-label="Search">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M10.5 4.5a6 6 0 1 0 0 12a6 6 0 0 0 0-12Zm0-2a8 8 0 1 1 4.95 14.285l4.132 4.133l-1.414 1.414l-4.133-4.132A8 8 0 0 1 10.5 2.5Z"
                fill="currentColor"
              />
            </svg>
          </button>
        </div>
        {showSuggestionPanel ? (
          <div className="search-suggestions" role="listbox" aria-label="Suggested products">
            {suggestions.map((suggestion, index) => {
              const topDealers = suggestion.source_stores
                .slice(0, 4)
                .map((store) => formatVendorLabel(store.vendor))
                .join(" · ");

              return (
                  <button
                    type="button"
                    className={`search-suggestion ${index === activeSuggestionIndex ? "search-suggestion--active" : ""}`}
                    key={suggestion.id}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => handleSuggestionSelect(suggestion)}
                  >
                    <span className="search-suggestion__leading search-suggestion__leading--icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24">
                        <path
                          d="M10.5 4.5a6 6 0 1 0 0 12a6 6 0 0 0 0-12Zm0-2a8 8 0 1 1 4.95 14.285l4.132 4.133l-1.414 1.414l-4.133-4.132A8 8 0 0 1 10.5 2.5Z"
                          fill="currentColor"
                        />
                      </svg>
                    </span>
                    <span className="search-suggestion__body">
                      <span className="search-suggestion__title">{formatProductLabel(suggestion.canonical_name)}</span>
                      <span className="search-suggestion__subtitle">
                        {topDealers || `${suggestion.live_store_count} live dealers`}
                      </span>
                    </span>
                    <span className="search-suggestion__trailing">
                      <strong>{formatCurrency(suggestion.best_price)}</strong>
                    </span>
                  </button>
              );
            })}
          </div>
        ) : null}
      </div>
      {onPincodeChange ? (
        <div className="search-bar__side">
          <span className={`pincode-field ${pincodeInvalid ? "pincode-field--invalid" : ""}`}>
            <input
              className="search-input pincode-input"
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
                className="pincode-field__clear"
                onClick={onClearPincode}
                aria-label="Clear pincode"
              >
                x
              </button>
            ) : null}
          </span>
          <button
            type="button"
            className="secondary-button search-bar__apply"
            onClick={onApplyPincode}
            disabled={isApplyingPincode}
          >
            {isApplyingPincode ? "Applying…" : "Apply"}
          </button>
        </div>
      ) : null}
      <button type="submit" className="search-button search-bar__submit">
        Search
      </button>
    </form>
  );
}
