from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SearchFilterDiagnostic:
    key: str
    label: str
    detail: str
    source: str | None = None
    active: bool = True
    removed_count: int = 0


@dataclass(slots=True)
class SearchDiagnostics:
    query: str
    source_profile: str
    location: str | None = None
    pincode: str | None = None
    intent: str | None = None
    corrected_query: str | None = None
    source_groups_checked: list[str] = field(default_factory=list)
    coverage_status: str | None = None
    match_confidence: float | None = None
    sources_checked: list[str] = field(default_factory=list)
    observed_offer_count: int = 0
    matched_offer_count: int = 0
    filters: list[SearchFilterDiagnostic] = field(default_factory=list)

    def copy(self) -> "SearchDiagnostics":
        return SearchDiagnostics(
            query=self.query,
            source_profile=self.source_profile,
            location=self.location,
            pincode=self.pincode,
            intent=self.intent,
            corrected_query=self.corrected_query,
            source_groups_checked=list(self.source_groups_checked),
            coverage_status=self.coverage_status,
            match_confidence=self.match_confidence,
            sources_checked=list(self.sources_checked),
            observed_offer_count=self.observed_offer_count,
            matched_offer_count=self.matched_offer_count,
            filters=[
                SearchFilterDiagnostic(
                    key=filter_item.key,
                    label=filter_item.label,
                    detail=filter_item.detail,
                    source=filter_item.source,
                    active=filter_item.active,
                    removed_count=filter_item.removed_count,
                )
                for filter_item in self.filters
            ],
        )

    def add_filter(self, filter_item: SearchFilterDiagnostic) -> None:
        for existing in self.filters:
            if existing.key != filter_item.key or existing.source != filter_item.source:
                continue
            existing.removed_count += filter_item.removed_count
            existing.active = existing.active or filter_item.active
            if filter_item.detail and filter_item.detail != existing.detail:
                existing.detail = filter_item.detail
            return
        self.filters.append(filter_item)
