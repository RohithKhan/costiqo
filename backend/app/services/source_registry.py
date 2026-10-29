from collections.abc import Callable

from app.core.config import Settings
from app.scrapers.amazon_scraper import AmazonScraper
from app.scrapers.base import BaseScraper
from app.scrapers.croma_scraper import CromaScraper
from app.scrapers.electronics_comp_scraper import ElectronicsCompScraper
from app.scrapers.flipkart_scraper import FlipkartScraper
from app.scrapers.global_electronics_scraper import GlobalElectronicsScraper
from app.scrapers.ibo_scraper import IboScraper
from app.scrapers.moglix_scraper import MoglixScraper
from app.scrapers.poorvika_scraper import PoorvikaScraper
from app.scrapers.reliance_digital_scraper import RelianceDigitalScraper
from app.scrapers.robu_scraper import RobuScraper


SCRAPER_BUILDERS: dict[str, Callable[[Settings], BaseScraper]] = {
    "amazon": lambda settings: AmazonScraper(),
    "croma": lambda settings: CromaScraper(),
    "electronicscomp": lambda settings: ElectronicsCompScraper(),
    "flipkart": lambda settings: FlipkartScraper(),
    "global-electronics": lambda settings: GlobalElectronicsScraper(),
    "ibo": lambda settings: IboScraper(),
    "moglix": lambda settings: MoglixScraper(),
    "poorvika": lambda settings: PoorvikaScraper(),
    "reliance-digital": lambda settings: RelianceDigitalScraper(),
    "robu": lambda settings: RobuScraper(),
}


class SourceRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_scrapers(self) -> list[BaseScraper]:
        return list(self.build_scrapers_by_source().values())

    def build_scrapers_by_source(self) -> dict[str, BaseScraper]:
        scrapers: dict[str, BaseScraper] = {}
        degraded_sources = set(self.settings.degraded_sources)
        for source_name in self.settings.all_configured_sources:
            if source_name in degraded_sources:
                continue
            scraper_builder = SCRAPER_BUILDERS.get(source_name)
            if scraper_builder is None:
                continue
            scrapers[source_name] = scraper_builder(self.settings)
        return scrapers

    def available_sources(self) -> list[str]:
        return list(SCRAPER_BUILDERS)
