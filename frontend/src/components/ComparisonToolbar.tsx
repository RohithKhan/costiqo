import type { ComparisonRankingMode } from "../types/product";
import { comparisonRankingOptions } from "../lib/comparisonRanking";

type ComparisonToolbarProps = {
  rankingMode: ComparisonRankingMode;
  onRankingModeChange: (mode: ComparisonRankingMode) => void;
  onExport: () => void;
};

export function ComparisonToolbar({
  rankingMode,
  onRankingModeChange,
  onExport,
}: ComparisonToolbarProps) {
  return (
    <div className="comparison-toolbar__actions">
      <label className="comparison-toolbar__field">
        <span className="small-copy">Sort by</span>
        <select
          value={rankingMode}
          onChange={(event) => onRankingModeChange(event.target.value as ComparisonRankingMode)}
        >
          {comparisonRankingOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="secondary-button" onClick={onExport}>
        Export CSV
      </button>
    </div>
  );
}
