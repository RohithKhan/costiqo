import asyncio
from time import perf_counter
from decimal import Decimal

from app.core.config import Settings
from app.schemas.comparison import ComparisonItem
from app.scrapers.base import BaseScraper, PriceHistoryEntry, ScrapedListing, ScrapedReview, SearchContext
from app.scrapers.croma_scraper import CromaScraper
from app.scrapers.electronics_comp_scraper import ElectronicsCompScraper
from app.scrapers.global_electronics_scraper import GlobalElectronicsScraper
from app.scrapers.hardware_scraper_utils import query_variants
from app.scrapers.ibo_scraper import IboScraper
from app.scrapers.moglix_scraper import MoglixScraper
from app.scrapers.normalizers import listing_matches_query
from app.scrapers.robu_scraper import RobuScraper
from app.services.candidate_validation_service import CandidateValidationResult
from app.services.comparison_service import ComparisonService, LiveProductDescriptor
from app.services.query_cache_store import QueryCacheStore
from app.services.scrape_service import ScrapeService, SearchCoverageRequirement
from app.services.sentiment_service import SentimentService
from app.services.product_service import ProductService
from app.services.source_registry import SourceRegistry
from app.utils.time_utils import utc_now
from app.utils.vendor_links import build_vendor_search_url, canonicalize_vendor_product_url


def test_moglix_scraper_extracts_ssr_products():
    scraper = MoglixScraper()
    html = """
    <script>
    {&q;moglixPartNumber&q;:&q;MSN123&q;,&q;salesPrice&q;:1599,
    &q;productName&q;:&q;Waco Digital Multimeter 19TB&q;,
    &q;productUrl&q;:&q;waco-digital-multimeter-19tb/mp/msn123&q;,
    &q;brandName&q;:&q;Waco&q;,&q;categoryNames&q;:[&q;Measurement &a; Testing&q;,&q;Multimeters&q;],
    &q;mainImageLink&q;:&q;p/example-large.jpg&q;,&q;quantityAvailable&q;:3,
    &q;avgRating&q;:4.2,&q;reviewCount&q;:18,&q;eta&q;:&q;Tomorrow&q;}
    </script>
    """

    listings = scraper._build_live_listings("digital multimeter", html)

    assert len(listings) == 1
    assert listings[0].vendor == "Moglix"
    assert listings[0].price == Decimal("1599.00")
    assert listings[0].category == "Multimeters"
    assert listings[0].product_url == "https://www.moglix.com/waco-digital-multimeter-19tb/mp/msn123"


def test_ibo_scraper_extracts_next_search_products():
    scraper = IboScraper()
    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"pageProps":{"data":{"searchResults":{"products":[{
      "display_name":"Haoyue DT-830D Digital Multimeter",
      "esin":"EP6E7RGQLS",
      "media":{"primary_image_url":"https://services.ibo.com/multimeter.webp"},
      "prices":[{"type":"PRICE_INCL_TAX","price":{"cent_amount":19900,"currency":"INR","fraction":100}}],
      "earliest_delivery_date":{"label":"Delivery by tomorrow"},
      "product_url":"haoyue-dt830d-digital-multimeter/p/EP6E7RGQLS"
    }]}}}}}}
    </script>
    """

    listings = scraper._build_live_listings("multimeter", html)

    assert len(listings) == 1
    assert listings[0].vendor == "IBO"
    assert listings[0].price == Decimal("199.00")
    assert listings[0].delivery_info == "Delivery by tomorrow"


def test_global_electronics_scraper_extracts_wix_products():
    scraper = GlobalElectronicsScraper()
    html = """
    <script>
    {"id":"product-1","options":[],"customTextFields":[],"productType":"physical",
    "price":1899,"sku":"VARTECH V5300M","isInStock":true,
    "urlPart":"var-tech-digital-lcr-multimeter-v-5300-m",
    "formattedPrice":"₹1,899.00","name":"VAR TECH Digital LCR Multimeter V 5300 M",
    "media":[{"fullUrl":"https://static.wixstatic.com/media/example.jpg"}]}
    </script>
    """

    listings = scraper._build_live_listings("multimeter", html)

    assert len(listings) == 1
    assert listings[0].vendor == "Global Electronics"
    assert listings[0].price == Decimal("1899.00")
    assert listings[0].product_url == (
        "https://www.globalelectronics.in/product-page/var-tech-digital-lcr-multimeter-v-5300-m"
    )


def test_robu_scraper_extracts_store_api_products():
    scraper = RobuScraper()
    payload = [
        {
            "name": "Official Arduino Uno Media Carrier ASX00083",
            "slug": "official-arduino-uno-media-carrier",
            "sku": "R263488",
            "prices": {"price": "235900", "currency_minor_unit": 2},
            "average_rating": "4.5",
            "review_count": 3,
            "is_in_stock": True,
            "images": [{"src": "https://oldwp.robu.in/wp-content/uploads/2026/03/1-27.jpg"}],
            "categories": [{"name": "Arduino Accessories"}],
        }
    ]

    listings = scraper._build_api_listings("arduino", payload)

    assert len(listings) == 1
    assert listings[0].vendor == "Robu"
    assert listings[0].price == Decimal("2359.00")
    assert listings[0].model_number == "R263488"
    assert listings[0].product_url == "https://robu.in/product/official-arduino-uno-media-carrier/"


def test_robu_scraper_extracts_rendered_search_products():
    scraper = RobuScraper()
    raw_items = [
        {
            "href": "https://robu.in/product/mastech-mas830l-digital-multimeter-with-probes-original/",
            "title": "Mastech MAS830L Original Digital Multimeter LCD Display Portable Tester",
            "price": "₹ 826",
            "sku": "5981",
            "reviews": "6",
            "availability": "Add to Cart",
        }
    ]

    listings = scraper._build_live_listings("digital multimeter", raw_items)

    assert len(listings) == 1
    assert listings[0].vendor == "Robu"
    assert listings[0].price == Decimal("826.00")
    assert listings[0].model_number == "5981"
    assert listings[0].review_count == 6


def test_robu_scraper_extracts_graphql_search_products():
    scraper = RobuScraper()
    raw_items = [
        {
            "href": "https://robu.in/product/haoyue-Mt9205a-digital-multimeter/",
            "title": "Haoyue MT87 Digital Multimeter",
            "price": "₹499",
            "image": "https://robu-prod-media.s3.ap-south-1.amazonaws.com/product/3445536/example.webp",
            "sku": "R265692",
            "reviews": 0,
            "availability": "add to cart",
        }
    ]

    listings = scraper._build_live_listings("digital multimeter", raw_items)

    assert len(listings) == 1
    assert listings[0].vendor == "Robu"
    assert listings[0].price == Decimal("499.00")
    assert listings[0].model_number == "R265692"
    assert listings[0].availability_status == "in_stock"
    assert listings[0].product_url == "https://robu.in/product/haoyue-Mt9205a-digital-multimeter/"


def test_robu_scraper_treats_vendor_503_as_blocked():
    scraper = RobuScraper()

    assert scraper._is_blocked_or_unavailable("Vendor API failed with status 503: Service Temporarily Unavailable")
    assert scraper._is_blocked_or_unavailable("Vendor page failed with status 403: cf-mitigated: challenge")


def test_croma_scraper_treats_akamai_access_denied_as_blocked():
    scraper = CromaScraper()

    assert scraper._is_blocked_or_unavailable(
        "Vendor page returned no parsable results. title='Access Denied' status=403 "
        "https://errors.edgesuite.net/reference"
    )


def test_croma_scraper_extracts_search_api_products():
    scraper = CromaScraper()
    payload = {
        "products": [
            {
                "code": "300652",
                "name": "Apple iPhone 15 (128GB, Black)",
                "manufacturer": "Apple",
                "url": "/apple-iphone-15-128gb-black-/p/300652",
                "plpImage": "https://media.tatacroma.com/Croma/300652.png",
                "price": {"formattedValue": "₹59,900", "value": 59900.0},
                "pincodePrice": {"formattedValue": "₹59,900", "value": 59900.0},
                "averageRating": 3.4,
                "numberOfRatings": 79,
                "productMessage": "EMI Available",
                "stockFlag": ["SA-A557"],
            },
            {
                "code": "243463",
                "name": "Apple iPhone 13 (128GB, Blue)",
                "url": "/apple-iphone-13-128gb-blue-/p/243463",
                "price": {"formattedValue": "₹45,690", "value": 45690.0},
            },
        ]
    }

    listings = scraper._build_api_listings("iphone 15", payload)

    assert len(listings) == 1
    assert listings[0].vendor == "Croma"
    assert listings[0].price == Decimal("59900.00")
    assert listings[0].product_url == "https://www.croma.com/apple-iphone-15-128gb-black-/p/300652"
    assert listings[0].review_count == 79


def test_electronicscomp_scraper_extracts_opencart_products():
    scraper = ElectronicsCompScraper()
    html = """
    <div class="product-layout product-list col-xs-12">
      <div class="product-thumb">
        <div class="image">
          <a href="https://www.electronicscomp.com/30pin-esp32-expansion-board?search=esp32">
            <img src="https://www.electronicscomp.com/image/cache/esp32.jpg" />
          </a>
        </div>
        <div class="caption">
          <h4><a href="https://www.electronicscomp.com/30pin-esp32-expansion-board?search=esp32">30Pin ESP32 Expansion Board with Type-C USB</a></h4>
          <p class="price">Rs.114.00</p>
        </div>
      </div>
    </div>
    """

    listings = scraper._build_live_listings("esp32 expansion board", html)

    assert len(listings) == 1
    assert listings[0].vendor == "ElectronicsComp"
    assert listings[0].price == Decimal("114.00")
    assert listings[0].product_url == "https://www.electronicscomp.com/30pin-esp32-expansion-board"


def test_listing_match_accepts_quantity_package_component_terms():
    assert listing_matches_query(
        "jumper wires pack of 40",
        "40pcs Jumper Wires Male to Male Breadboard Jumper Cable Kit for Arduino Shield",
    )
    assert listing_matches_query(
        "jumper wires pack of 40",
        "Jumper Wires 20cm 40 Pieces Pack",
    )
    assert listing_matches_query(
        "jumper wires pack of 40",
        "High Quality 20cm Dupont Line Male to Female Jumper Cables Connector Wire 40 Pcs",
    )
    assert not listing_matches_query(
        "jumper wires pack of 40",
        "120 Pieces Jumper Wire Set",
    )
    assert not listing_matches_query(
        "iphone 15 128 gb",
        "iPhone 15 case pack",
    )


def test_live_search_foreground_timeout_returns_fast_results():
    asyncio.run(_assert_live_search_foreground_timeout_returns_fast_results())


async def _assert_live_search_foreground_timeout_returns_fast_results():
    fast_listing = _live_listing(
        vendor="Fast Hardware",
        name="ESP32 Development Board",
        model_number="esp32-development-board",
        price="249",
        brand="ESP32",
        category="Electronics",
    )
    service = ScrapeService(
        scrapers_by_source={
            "fast": _DelayScraper("Fast Hardware", "https://fast.example", [fast_listing], 0.0),
            "slow": _DelayScraper("Slow Hardware", "https://slow.example", [], 0.2),
        },
        primary_sources=["fast", "slow"],
        background_sources=[],
        sentiment_service=SentimentService(),
        query_cache_store=QueryCacheStore(None),
        retry_attempts=1,
    )

    started_at = perf_counter()
    listings, diagnostics = await service.fetch_live_listings_with_diagnostics(
        "esp32",
        source_profile="primary",
        foreground_timeout_seconds=0.05,
    )
    elapsed_seconds = perf_counter() - started_at

    assert elapsed_seconds < 0.15
    assert [listing.vendor for listing in listings] == ["Fast Hardware"]
    assert diagnostics.matched_offer_count == 1
    assert any(
        filter_item.key == "foreground_timeout" and filter_item.removed_count == 1
        for filter_item in diagnostics.filters
    )
    await asyncio.sleep(0.25)


def test_live_search_waits_for_required_coverage_before_returning():
    asyncio.run(_assert_live_search_waits_for_required_coverage_before_returning())


def test_live_search_allows_amazon_specific_foreground_wait():
    asyncio.run(_assert_live_search_allows_amazon_specific_foreground_wait())


def test_comparison_adds_robu_specific_wait_for_hardware_queries():
    class FakeScrapeService:
        primary_sources = ["amazon", "robu", "croma"]
        scrapers_by_source = {}

    comparison_service = ComparisonService(
        FakeScrapeService(),
        None,
        None,
        None,
        None,
        None,
        None,
    )

    assert comparison_service._source_foreground_timeout_overrides(
        ["amazon", "robu", "croma"],
        "digital multimeter",
    ) == {
        "Amazon": comparison_service.AMAZON_FOREGROUND_TIMEOUT_SECONDS,
        "Robu": comparison_service.ROBU_FOREGROUND_TIMEOUT_SECONDS,
    }
    assert comparison_service._source_foreground_timeout_overrides(
        ["amazon", "robu", "croma"],
        "kurti",
    ) == {
        "Amazon": comparison_service.AMAZON_FOREGROUND_TIMEOUT_SECONDS,
    }


async def _assert_live_search_allows_amazon_specific_foreground_wait():
    fast_listing = _live_listing(
        vendor="Fast Hardware",
        name="ESP32 Development Board",
        model_number="esp32-development-board",
        price="249",
        brand="ESP32",
        category="Electronics",
    )
    amazon_listing = _live_listing(
        vendor="Amazon",
        name="ESP32 Development Board",
        model_number="esp32-development-board",
        price="299",
        brand="ESP32",
        category="Electronics",
    )
    service = ScrapeService(
        scrapers_by_source={
            "fast": _DelayScraper("Fast Hardware", "https://fast.example", [fast_listing], 0.0),
            "amazon": _DelayScraper("Amazon", "https://amazon.example", [amazon_listing], 0.08),
            "slow": _DelayScraper("Slow Hardware", "https://slow.example", [], 0.2),
        },
        primary_sources=["fast", "amazon", "slow"],
        background_sources=[],
        sentiment_service=SentimentService(),
        query_cache_store=QueryCacheStore(None),
        retry_attempts=1,
    )

    started_at = perf_counter()
    listings, diagnostics = await service.fetch_live_listings_with_diagnostics(
        "esp32",
        source_profile="primary",
        foreground_timeout_seconds=0.03,
        source_foreground_timeout_seconds={"Amazon": 0.1},
    )
    elapsed_seconds = perf_counter() - started_at

    assert 0.07 <= elapsed_seconds < 0.16
    assert {listing.vendor for listing in listings} == {"Fast Hardware", "Amazon"}
    assert any(
        filter_item.key == "source_specific_foreground_wait"
        for filter_item in diagnostics.filters
    )
    assert any(
        filter_item.key == "foreground_timeout" and filter_item.removed_count == 1
        for filter_item in diagnostics.filters
    )
    await asyncio.sleep(0.25)


async def _assert_live_search_waits_for_required_coverage_before_returning():
    amazon_listing = _live_listing(
        vendor="Amazon",
        name="ESP32 Development Board",
        model_number="esp32-development-board",
        price="299",
        brand="ESP32",
        category="Electronics",
    )
    electronics_listing = _live_listing(
        vendor="ElectronicsComp",
        name="ESP32 Development Board",
        model_number="esp32-development-board",
        price="249",
        brand="ESP32",
        category="Electronics",
    )
    service = ScrapeService(
        scrapers_by_source={
            "amazon": _DelayScraper("Amazon", "https://amazon.example", [amazon_listing], 0.0),
            "electronicscomp": _DelayScraper(
                "ElectronicsComp",
                "https://electronics.example",
                [electronics_listing],
                0.08,
            ),
            "robu": _DelayScraper("Robu", "https://robu.example", [], 0.3),
        },
        primary_sources=["amazon", "electronicscomp", "robu"],
        background_sources=[],
        sentiment_service=SentimentService(),
        query_cache_store=QueryCacheStore(None),
        retry_attempts=1,
    )

    started_at = perf_counter()
    listings, diagnostics = await service.fetch_live_listings_with_diagnostics(
        "esp32 development board",
        source_profile="primary",
        foreground_timeout_seconds=0.03,
        coverage_timeout_seconds=0.2,
        coverage_requirements=(
            SearchCoverageRequirement(
                key="hardware_store_coverage",
                label="hardware specialist store coverage",
                vendors=("ElectronicsComp", "Robu"),
            ),
            SearchCoverageRequirement(
                key="mainstream_store_coverage",
                label="mainstream store coverage",
                vendors=("Amazon",),
            ),
        ),
    )
    elapsed_seconds = perf_counter() - started_at

    assert 0.07 <= elapsed_seconds < 0.18
    assert {listing.vendor for listing in listings} == {"Amazon", "ElectronicsComp"}
    assert any(
        filter_item.key == "source_coverage_wait"
        for filter_item in diagnostics.filters
    )
    assert not any(
        filter_item.key == "source_coverage_incomplete"
        for filter_item in diagnostics.filters
    )
    assert any(
        filter_item.key == "foreground_timeout" and filter_item.removed_count == 1
        for filter_item in diagnostics.filters
    )
    await asyncio.sleep(0.25)


def test_live_search_reports_incomplete_coverage_at_hard_deadline():
    asyncio.run(_assert_live_search_reports_incomplete_coverage_at_hard_deadline())


async def _assert_live_search_reports_incomplete_coverage_at_hard_deadline():
    amazon_listing = _live_listing(
        vendor="Amazon",
        name="ESP32 Development Board",
        model_number="esp32-development-board",
        price="299",
        brand="ESP32",
        category="Electronics",
    )
    service = ScrapeService(
        scrapers_by_source={
            "amazon": _DelayScraper("Amazon", "https://amazon.example", [amazon_listing], 0.0),
            "electronicscomp": _DelayScraper("ElectronicsComp", "https://electronics.example", [], 0.3),
        },
        primary_sources=["amazon", "electronicscomp"],
        background_sources=[],
        sentiment_service=SentimentService(),
        query_cache_store=QueryCacheStore(None),
        retry_attempts=1,
    )

    started_at = perf_counter()
    listings, diagnostics = await service.fetch_live_listings_with_diagnostics(
        "esp32 development board",
        source_profile="primary",
        foreground_timeout_seconds=0.03,
        coverage_timeout_seconds=0.09,
        coverage_requirements=(
            SearchCoverageRequirement(
                key="hardware_store_coverage",
                label="hardware specialist store coverage",
                vendors=("ElectronicsComp",),
            ),
            SearchCoverageRequirement(
                key="mainstream_store_coverage",
                label="mainstream store coverage",
                vendors=("Amazon",),
            ),
        ),
    )
    elapsed_seconds = perf_counter() - started_at

    assert elapsed_seconds < 0.15
    assert [listing.vendor for listing in listings] == ["Amazon"]
    assert any(
        filter_item.key == "source_coverage_incomplete"
        and filter_item.removed_count == 1
        for filter_item in diagnostics.filters
    )
    await asyncio.sleep(0.25)


def test_hardware_source_registry_and_vendor_links():
    settings = Settings(
        database_url="sqlite:///./test.db",
        enabled_sources_raw="moglix,robu,electronicscomp,ibo,global-electronics,croma",
        degraded_sources_raw="",
    )
    registry = SourceRegistry(settings)

    scrapers_by_source = registry.build_scrapers_by_source()

    assert {
        "moglix",
        "robu",
        "electronicscomp",
        "ibo",
        "global-electronics",
        "croma",
    } <= set(registry.available_sources())
    assert scrapers_by_source["moglix"].vendor_name == "Moglix"
    assert scrapers_by_source["robu"].vendor_name == "Robu"
    assert scrapers_by_source["electronicscomp"].vendor_name == "ElectronicsComp"
    assert scrapers_by_source["ibo"].vendor_name == "IBO"
    assert scrapers_by_source["global-electronics"].vendor_name == "Global Electronics"
    assert scrapers_by_source["croma"].vendor_name == "Croma"
    assert build_vendor_search_url("Moglix", "multimeter") == (
        "https://www.moglix.com/search?search_query=multimeter"
    )
    assert build_vendor_search_url("Global Electronics", "multimeter") == (
        "https://www.globalelectronics.in/all-products?q=multimeter"
    )
    assert build_vendor_search_url("ElectronicsComp", "esp32") == (
        "https://www.electronicscomp.com/search?search=esp32"
    )
    assert build_vendor_search_url("iNvent - Apple Premium Reseller", "Apple iPhone 15") == (
        "https://inventstore.in/?s=Apple+iPhone+15&post_type=product"
    )
    assert build_vendor_search_url("Vijay Sales", "Apple iPhone 15") == (
        "https://www.vijaysales.com/search?q=Apple+iPhone+15"
    )
    assert canonicalize_vendor_product_url(
        "Croma",
        "https://www.croma.com/apple-iphone-15/p/123456?utm=test",
        "https://www.croma.com",
    ) == "https://www.croma.com/apple-iphone-15/p/123456"
    assert canonicalize_vendor_product_url(
        "Croma",
        "https://www.croma.com/l/redirect?url=https%3A%2F%2Fwww.croma.com%2Fapple-iphone-15-128gb-black-%2Fp%2F300652",
        "https://www.croma.com",
    ) == "https://www.croma.com/apple-iphone-15-128gb-black-/p/300652"


def test_comparison_keeps_robu_accessory_category_for_precise_hardware_match():
    scraper = RobuScraper()
    listing = scraper._build_api_listings(
        "arduino uno media carrier",
        [
            {
                "name": "Official Arduino Uno Media Carrier ASX00083",
                "slug": "official-arduino-uno-media-carrier",
                "sku": "R263488",
                "prices": {"price": "235900", "currency_minor_unit": 2},
                "is_in_stock": True,
                "categories": [{"name": "Arduino Accessories"}],
            }
        ],
    )[0]
    comparison_service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )

    groups = comparison_service._group_live_listings(
        "arduino uno media carrier",
        [listing],
    )
    preferred_vendors = comparison_service._preferred_mainstream_vendors(
        LiveProductDescriptor(
            canonical_name="Official Arduino Uno Media Carrier ASX00083",
            brand="Official",
            category="Arduino Accessories",
        )
    )

    assert len(groups) == 1
    assert groups[0].listings[0].vendor == "Robu"
    assert preferred_vendors[:5] == [
        "Moglix",
        "Robu",
        "ElectronicsComp",
        "IBO",
        "Global Electronics",
    ]


def test_comparison_prefers_hardware_store_links_when_query_is_hardware():
    comparison_service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )

    preferred_vendors = comparison_service._preferred_mainstream_vendors(
        LiveProductDescriptor(
            canonical_name="ESP32-S3 GPIO Expension Board",
            brand="ESP32-S3",
            category="Electronics",
        ),
        query="ESP 32",
    )

    assert preferred_vendors[:5] == [
        "Moglix",
        "Robu",
        "ElectronicsComp",
        "IBO",
        "Global Electronics",
    ]


def test_live_group_selection_prefers_lower_price_within_score_window():
    comparison_service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    listings = [
        _live_listing(
            vendor="Poorvika",
            name="Apple iPhone 15 ( Blue,256GB )",
            model_number="apple-iphone-15",
            price="64900",
        ),
        _live_listing(
            vendor="Flipkart",
            name="Apple iPhone 15 (Blue, 256 GB)",
            model_number="iphone-15-256-gb",
            price="69900",
        ),
        _live_listing(
            vendor="Reliance Digital",
            name="Apple iPhone 15 256 GB Blue",
            model_number="iphone-15-256-gb",
            price="69900",
        ),
    ]

    selected_group = comparison_service._select_live_group(
        comparison_service._group_live_listings("iphone 15", listings),
        "iphone 15",
    )

    assert {listing.vendor for listing in selected_group.listings} == {"Poorvika"}


def test_live_grouping_merges_provider_and_direct_rows_with_different_source_keys():
    comparison_service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    groups = comparison_service._group_live_listings(
        "iphone 15",
        [
            _live_listing(
                vendor="Flipkart",
                name="Apple iPhone 15 (Black, 128 GB)",
                category="Smartphones",
                model_number="itm6ac6485515ae4",
                price="59900",
            ),
            _live_listing(
                vendor="iInvent",
                name="Apple iPhone 15 (Black, 128 GB)",
                category="Electronics",
                model_number="apple-iphone-15-black-128-gb",
                price="64900",
            ),
        ],
    )

    assert len(groups) == 1
    assert {listing.vendor for listing in groups[0].listings} == {"Flipkart", "iInvent"}


def test_live_grouping_keeps_different_storage_variants_separate():
    comparison_service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    groups = comparison_service._group_live_listings(
        "iphone 15",
        [
            _live_listing(
                vendor="Flipkart",
                name="Apple iPhone 15 (Black, 128 GB)",
                model_number="iphone-15-128-gb",
                price="59900",
            ),
            _live_listing(
                vendor="Reliance Digital",
                name="Apple iPhone 15 256 GB Blue",
                model_number="iphone-15-256-gb",
                price="69900",
            ),
        ],
    )

    assert len(groups) == 2


def test_comparison_prioritizes_hardware_sources_for_hardware_queries():
    class FakeScrapeService:
        primary_sources = [
            "amazon",
            "flipkart",
            "poorvika",
            "reliance-digital",
            "moglix",
            "robu",
            "electronicscomp",
            "ibo",
            "global-electronics",
        ]

    comparison_service = ComparisonService(
        FakeScrapeService(),
        None,
        None,
        None,
        None,
        None,
        None,
    )

    expected_hardware_sources = [
        "moglix",
        "robu",
        "electronicscomp",
        "ibo",
        "global-electronics",
        "amazon",
    ]
    expected_consumer_sources = [
        "amazon",
        "flipkart",
        "poorvika",
        "reliance-digital",
        "moglix",
        "robu",
        "electronicscomp",
        "ibo",
        "global-electronics",
    ]
    assert comparison_service._select_primary_source_names("arduino uno media carrier") == expected_hardware_sources
    assert comparison_service._select_primary_source_names("ESP 32 dev board") == expected_hardware_sources
    assert comparison_service._select_primary_source_names("iphone 15") == expected_consumer_sources


def test_comparison_does_not_require_hardcoded_hardware_coverage_buckets():
    class FakeScrapeService:
        primary_sources = ["moglix", "robu", "electronicscomp", "ibo", "global-electronics", "amazon"]
        scrapers_by_source = {}

    comparison_service = ComparisonService(
        FakeScrapeService(),
        None,
        None,
        None,
        None,
        None,
        None,
    )

    requirements = comparison_service._build_live_search_coverage_requirements(
        "esp32 development board",
        FakeScrapeService.primary_sources,
    )

    assert requirements == ()


def test_product_suggestions_select_query_appropriate_sources():
    class FakeScrapeService:
        primary_sources = [
            "amazon",
            "flipkart",
            "poorvika",
            "reliance-digital",
            "moglix",
            "robu",
            "ibo",
            "global-electronics",
        ]
        scrapers_by_source = {}

    product_service = ProductService(FakeScrapeService(), None, None)

    assert product_service._select_live_suggestion_sources("ESP 32", limit=5) == [
        "poorvika",
        "moglix",
        "ibo",
        "global-electronics",
    ]
    assert product_service._select_live_suggestion_sources("washing machine", limit=5) == [
        "poorvika",
        "moglix",
        "ibo",
        "global-electronics",
    ]


def test_hardware_live_suggestions_prefer_cheaper_close_matches():
    product_service = ProductService(None, None, None)

    suggestions = product_service.build_live_search_suggestions(
        "ESP 32",
        [
            _live_listing(
                vendor="Robu",
                name="Industrial Shields ESP32 PLC 14",
                brand="Industrial",
                category="PLC Controller",
                model_number=None,
                price="15350",
            ),
            _live_listing(
                vendor="Robu",
                name="ESP32-S3 GPIO Expension Board",
                brand="ESP32-S3",
                category="Advance Development Boards",
                model_number=None,
                price="879",
            ),
            _live_listing(
                vendor="Robu",
                name="VACUS ESP32-LAN8720 PoE-R1 Module",
                brand="VACUS",
                category="IoT Development Boards",
                model_number=None,
                price="8113",
            ),
        ],
        limit=3,
    )

    assert [suggestion.canonical_name for suggestion in suggestions] == [
        "ESP32-S3 GPIO Expension Board",
        "VACUS ESP32-LAN8720 PoE-R1 Module",
        "Industrial Shields ESP32 PLC 14",
    ]


def test_hardware_matcher_handles_spaced_and_compact_model_tokens():
    assert listing_matches_query("ESP 32", "ESP32 DevKit V1 Development Board")
    assert listing_matches_query("esp32", "ESP 32 DevKit V1 Development Board")
    assert listing_matches_query(
        "esp32 wroom dev board",
        "Black ESP32-DEVKITC Core Board, ESP32-WROOM-VE for Arduino",
    )
    assert listing_matches_query(
        "esp32 wroom dev board",
        "ESP32 WROOM 32 Development Board",
    )
    assert listing_matches_query("DT830D multimeter", "Haoyue DT-830D Digital Multimeter")
    assert listing_matches_query("capactior", "Electrolytic Capacitor 100uF 25V")
    assert not listing_matches_query(
        "HC-SR04 ultrasonic sensor",
        "Mounting Bracket for Ultrasonic Sensor Module - HC-SR04",
    )


def test_live_group_selection_uses_candidate_relation_validation_for_broad_query():
    comparison_service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    listings = [
        _live_listing(
            vendor="ElectronicsComp",
            name="ESP32 Development board WT32-SC01",
            model_number="wt32-sc01",
            price="2815",
            brand="ESP32",
            category="Electronics",
        ),
        _live_listing(
            vendor="Amazon",
            name="ESP32-WROOM-32 Development Board (ESP32 DevKit V1) - WiFi, Bluetooth, Dual Core",
            model_number="esp32-devkit-v1",
            price="476",
            brand="ESP32",
            category="Electronics",
        ),
        _live_listing(
            vendor="ElectronicsComp",
            name="30Pin ESP32 Expansion Board with Type-C USB",
            model_number="esp32-expansion-board",
            price="149",
            brand="ESP32",
            category="Electronics",
        ),
    ]
    groups = comparison_service._group_live_listings(
        "esp32 development board",
        listings,
        validation_results={
            0: CandidateValidationResult(
                index=0,
                relation="same_product_variant",
                confidence=0.72,
                canonical_product=listings[0].canonical_name,
            ),
            1: CandidateValidationResult(
                index=1,
                relation="exact_match",
                confidence=0.95,
                canonical_product=listings[1].canonical_name,
            ),
            2: CandidateValidationResult(
                index=2,
                relation="same_category_alternative",
                confidence=0.62,
                canonical_product=listings[2].canonical_name,
            ),
        },
    )

    selected_group = comparison_service._select_live_group(groups, "esp32 development board")

    assert selected_group.canonical_name == (
        "ESP32-WROOM-32 Development Board (ESP32 DevKit V1) - WiFi, Bluetooth, Dual Core"
    )


def test_live_group_selection_uses_relation_validation_for_hardware_variants():
    comparison_service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    listings = [
        _live_listing(
            vendor="Amazon",
            name="CPVC Elbow 3 Way 1 inch",
            model_number="cpvc-elbow-3-way-1-inch",
            price="299",
            brand="Generic",
            category="Hardware",
        ),
        _live_listing(
            vendor="Moglix",
            name="Crystal 1 inch CPVC 90 Degree Connection Pipe Elbow",
            model_number="cpvc-90-degree-elbow-1-inch",
            price="18",
            brand="Crystal",
            category="Hardware",
        ),
        _live_listing(
            vendor="Amazon",
            name="cpvc 45 degree elbow 25 mm (1 inch)",
            model_number="cpvc-45-degree-elbow-1-inch",
            price="229",
            brand="Generic",
            category="Hardware",
        ),
    ]
    groups = comparison_service._group_live_listings(
        "cpvc elbow 1 inch",
        listings,
        validation_results={
            0: CandidateValidationResult(
                index=0,
                relation="same_product_variant",
                confidence=0.68,
                canonical_product=listings[0].canonical_name,
            ),
            1: CandidateValidationResult(
                index=1,
                relation="exact_match",
                confidence=0.91,
                canonical_product=listings[1].canonical_name,
            ),
            2: CandidateValidationResult(
                index=2,
                relation="same_product_variant",
                confidence=0.66,
                canonical_product=listings[2].canonical_name,
            ),
        },
    )

    selected_group = comparison_service._select_live_group(groups, "cpvc elbow 1 inch")

    assert selected_group.canonical_name == "Crystal 1 inch CPVC 90 Degree Connection Pipe Elbow"


def test_live_grouping_excludes_accessories_from_main_product_queries():
    comparison_service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    listings = [
        _live_listing(
            vendor="Amazon",
            name="Daikin AC Remote",
            model_number="arc470a25",
            price="435",
            brand="Daikin",
            category="Remote Controls",
        ),
        _live_listing(
            vendor="Flipkart",
            name="Daikin 2026 Model 0.9 Ton 2 Star Split Fixed Speed AC",
            model_number="daikin-0-9-ton-2-star",
            price="24500",
            brand="Daikin",
            category="Air Conditioners",
        ),
    ]

    groups = comparison_service._group_live_listings(
        "daikin ac",
        listings,
        validation_results={
            0: CandidateValidationResult(
                index=0,
                relation="compatible_accessory_or_part",
                confidence=0.95,
                canonical_product=listings[0].canonical_name,
                product_family="Remote Controls",
            ),
            1: CandidateValidationResult(
                index=1,
                relation="exact_match",
                confidence=0.95,
                canonical_product=listings[1].canonical_name,
                product_family="Air Conditioners",
            ),
        },
    )

    grouped_names = {
        listing.vendor_product_name
        for group in groups
        for listing in group.listings
    }
    assert listings[0].vendor_product_name not in grouped_names
    assert listings[1].vendor_product_name in grouped_names


def test_live_grouping_honors_llm_non_match_confirmation():
    comparison_service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    listings = [
        _live_listing(
            vendor="IBO",
            name="Washing Machine Outlet Pipe - 1.5 Mtr - Watertec",
            model_number="washing-machine-outlet-pipe",
            price="168",
            brand="Watertec",
            category="Plumbing Accessories",
        ),
        _live_listing(
            vendor="Croma",
            name="Samsung 7 kg Fully Automatic Front Load Washing Machine",
            model_number="samsung-7kg-front-load",
            price="32990",
            brand="Samsung",
            category="Washing Machines",
        ),
    ]

    groups = comparison_service._group_live_listings(
        "washing machine",
        listings,
        validation_results={
            0: CandidateValidationResult(
                index=0,
                is_match=False,
                relation="compatible_accessory_or_part",
                confidence=0.96,
                canonical_product=listings[0].canonical_name,
                product_family="Washing Machine Accessories",
            ),
            1: CandidateValidationResult(
                index=1,
                is_match=True,
                relation="same_category_alternative",
                confidence=0.93,
                canonical_product=listings[1].canonical_name,
                product_family="Washing Machines",
            ),
        },
    )

    grouped_names = {
        listing.vendor_product_name
        for group in groups
        for listing in group.listings
    }
    assert listings[0].vendor_product_name not in grouped_names
    assert listings[1].vendor_product_name in grouped_names


def test_live_grouping_allows_accessories_when_query_requests_accessory():
    comparison_service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    remote = _live_listing(
        vendor="Amazon",
        name=(
            "7SEVEN Compatible Daikin AC Remote Original ARC470A25 ARC70A1 "
            "Suitable for Split and Window Air Conditioner"
        ),
        model_number="arc470a25",
        price="435",
        brand="Daikin",
        category="Remote Controls",
    )

    groups = comparison_service._group_live_listings(
        "daikin ac remote",
        [remote],
        validation_results={
            0: CandidateValidationResult(
                index=0,
                relation="compatible_accessory_or_part",
                confidence=0.95,
                canonical_product=remote.canonical_name,
                product_family="Remote Controls",
            ),
        },
    )

    assert len(groups) == 1
    assert groups[0].listings == [remote]


def test_live_result_limit_dedupes_duplicate_vendor_offers_before_capping():
    comparison_service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    duplicate_name = "Daikin 2026 Model 0.9 Ton 2 Star Split Fixed Speed AC"

    limited_items = comparison_service._limit_live_results_per_vendor(
        [
            _comparison_item(
                vendor="Flipkart",
                name=duplicate_name,
                price=26990,
                url="https://flipkart.example/daikin-a",
            ),
            _comparison_item(
                vendor="Flipkart",
                name=duplicate_name,
                price=26990,
                url="https://flipkart.example/daikin-b",
            ),
            _comparison_item(
                vendor="Flipkart",
                name="Daikin 2024 Model 1 Ton 3 Star Split Inverter AC",
                price=29490,
                url="https://flipkart.example/daikin-c",
            ),
        ]
    )

    assert [item.product_url for item in limited_items] == [
        "https://flipkart.example/daikin-a",
        "https://flipkart.example/daikin-c",
    ]


def test_hardware_query_variants_include_compact_model_forms():
    assert "ESP32" in query_variants("ESP 32")
    assert "capacitor" in [item.lower() for item in query_variants("capactior")]
    assert "esp wroom32" in [item.lower() for item in query_variants("esp wroom 32")]
    assert "DT830D digital multimeter" in query_variants("DT 830D digital multimeter")
    assert "bosch drill" in [item.lower() for item in query_variants("Bosch GSB 600 drill")]
    assert "drill" in [item.lower() for item in query_variants("Bosch GSB 600 drill")]
    assert "multimeter" in [item.lower() for item in query_variants("Fluke 101 Digital Multimeter")]
    assert "ultratech cement" in [item.lower() for item in query_variants("Ultratech PPC cement")]
    assert "cement" in [item.lower() for item in query_variants("Ultratech PPC cement")]
    assert "astral pipe" in [item.lower() for item in query_variants("Astral CPVC pipe")]
    assert "cpvc pipe" in [item.lower() for item in query_variants("Astral CPVC pipe")]
    assert "safety shoes" in [item.lower() for item in query_variants("Karam safety shoes")]
    assert query_variants("esp32 wroom dev board")[:3] == [
        "esp32 wroom dev board",
        "esp32",
        "wroom esp32",
    ]


def test_live_related_groups_reject_unselected_pro_variants():
    comparison_service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    groups = comparison_service._group_live_listings(
        "iphone 15",
        [
            _live_listing(
                vendor="Flipkart",
                name="Apple iPhone 15 (Black, 128 GB)",
                model_number="iphone-15-128-gb",
                price="59900",
            ),
            _live_listing(
                vendor="Reliance Digital",
                name="Apple iPhone 15 Pro 512 GB Black Titanium",
                model_number="iphone-15-pro-512-gb",
                price="65900",
            ),
        ],
    )

    selected_group = comparison_service._select_live_group(groups, "iphone 15")
    candidate_group = next(group for group in groups if group is not selected_group)

    assert comparison_service._live_group_has_variant_conflict(selected_group, candidate_group)


def test_degraded_hardware_sources_are_excluded_from_registry_and_vendor_links():
    settings = Settings(
        enabled_sources_raw="amazon,moglix,robu,electronicscomp,ibo,global-electronics",
        primary_sources_raw="moglix,robu,electronicscomp,ibo,global-electronics,amazon",
        degraded_sources_raw="robu",
    )
    scrapers_by_source = SourceRegistry(settings).build_scrapers_by_source()
    comparison_service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        degraded_source_names=("robu",),
    )

    preferred_vendors = comparison_service._preferred_mainstream_vendors(
        LiveProductDescriptor(
            canonical_name="ESP32 Development Board",
            brand="ESP32",
            category="Electronics",
        ),
        query="esp32 development board",
    )

    assert "robu" not in scrapers_by_source
    assert "Robu" not in preferred_vendors[:6]


def _live_listing(
    *,
    vendor: str,
    name: str,
    model_number: str | None,
    price: str,
    brand: str = "Apple",
    category: str = "Smartphones",
) -> ScrapedListing:
    price_value = Decimal(price)
    return ScrapedListing(
        vendor=vendor,
        base_url="https://example.com",
        scrape_strategy="test-double",
        canonical_name=name,
        brand=brand,
        category=category,
        model_number=model_number,
        image_url="",
        vendor_product_name=name,
        product_url=f"https://example.com/{vendor.lower().replace(' ', '-')}",
        price=price_value,
        raw_price=f"₹{int(price_value):,}",
        rating=None,
        review_count=0,
        delivery_info=None,
        price_history=[PriceHistoryEntry(scraped_at=utc_now(), price=price_value)],
    )


def _comparison_item(
    *,
    vendor: str,
    name: str,
    price: float,
    url: str,
) -> ComparisonItem:
    return ComparisonItem(
        vendor_product_id=1,
        vendor=vendor,
        product_name=name,
        price=price,
        displayed_price=price,
        raw_price=f"₹{int(price):,}",
        review_count=0,
        availability_status="In Stock",
        product_url=url,
        landed_price=price,
        source_type="online",
        price_verification_status="fresh_scrape",
        price_confidence=0.7,
        reasonability_label="fair",
    )


class _DelayScraper(BaseScraper):
    def __init__(
        self,
        vendor_name: str,
        base_url: str,
        listings: list[ScrapedListing],
        delay_seconds: float,
    ) -> None:
        self.vendor_name = vendor_name
        self.base_url = base_url
        self.scrape_strategy = "test-delay"
        self._listings = listings
        self._delay_seconds = delay_seconds

    async def search(
        self,
        query: str,
        context: SearchContext | None = None,
    ) -> list[ScrapedListing]:
        await asyncio.sleep(self._delay_seconds)
        return self._listings

    async def fetch_reviews(self, product_url: str) -> list[ScrapedReview]:
        return []
