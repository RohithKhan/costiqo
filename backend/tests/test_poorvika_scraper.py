from decimal import Decimal

from app.core.config import Settings
from app.scrapers.poorvika_scraper import PoorvikaScraper
from app.services.source_registry import SourceRegistry
from app.utils.vendor_links import build_vendor_search_url, canonicalize_vendor_product_url


def test_poorvika_scraper_builds_filtered_listings():
    scraper = PoorvikaScraper()

    payload = {
        "results": [
            {
                "grouped_hits": [
                    {
                        "hits": [
                            {
                                "document": {
                                    "name": "Nothing Phone 4a Pro (12GB 256GB White)",
                                    "brand_name": "Nothing",
                                    "model_code": "NOTHING4APRO256",
                                    "image": "/media/catalog/product/n/o/nothing-phone-4a-pro.jpg",
                                    "special_price": 37999,
                                    "price": 39999,
                                    "rating": "4.5",
                                    "review_count": "128",
                                    "stock_status": "In Stock",
                                    "slug": "nothing-phone-4a-pro-12gb-256gb-white",
                                    "sellable": 1,
                                    "variant_status": 1,
                                }
                            }
                        ]
                    }
                ]
            },
            {
                "hits": [
                    {
                        "document": {
                            "name": "Nothing Phone 4a Pro (12GB 256GB White)",
                            "brand_name": "Nothing",
                            "model_code": "NOTHING4APRO256",
                            "image": "/media/catalog/product/n/o/nothing-phone-4a-pro.jpg",
                            "special_price": 37999,
                            "price": 39999,
                            "rating": "4.5",
                            "review_count": "128",
                            "stock_status": "In Stock",
                            "slug": "nothing-phone-4a-pro-12gb-256gb-white",
                            "sellable": 1,
                            "variant_status": 1,
                        }
                    },
                    {
                        "document": {
                            "name": "Nothing Phone (4a) (White, 128 GB)",
                            "brand_name": "Nothing",
                            "model_code": "NOTHING4A128",
                            "image": "/media/catalog/product/n/o/nothing-phone-4a.jpg",
                            "special_price": 24999,
                            "price": 26999,
                            "rating": "4.4",
                            "review_count": "96",
                            "stock_status": "In Stock",
                            "slug": "nothing-phone-4a-white-128gb",
                            "sellable": 1,
                            "variant_status": 1,
                        }
                    },
                    {
                        "document": {
                            "name": "Nothing Phone 4a Pro (Black, 256 GB)",
                            "brand_name": "Nothing",
                            "model_code": "NOTHING4APRO256B",
                            "image": "/media/catalog/product/n/o/nothing-phone-4a-pro-black.jpg",
                            "special_price": 38999,
                            "price": 40999,
                            "rating": "4.6",
                            "review_count": "140",
                            "stock_status": "Out of Stock",
                            "products_slug": ["nothing-phone-4a-pro"],
                            "sellable": 1,
                            "variant_status": 1,
                        }
                    },
                ]
            },
        ]
    }

    listings = scraper._build_live_listings("nothing 4a pro", payload)

    assert len(listings) == 2
    assert listings[0].vendor == "Poorvika"
    assert listings[0].price == Decimal("37999.00")
    assert listings[0].review_count == 128
    assert listings[0].availability_status == "in_stock"
    assert listings[0].product_url == "https://www.poorvika.com/nothing-phone-4a-pro-12gb-256gb-white/p"
    assert listings[0].image_url == "https://www.poorvika.com/media/catalog/product/n/o/nothing-phone-4a-pro.jpg"
    assert listings[1].availability_status == "out_of_stock"
    assert listings[1].product_url == "https://www.poorvika.com/nothing-phone-4a-pro/s"
    assert all("4a pro" in listing.vendor_product_name.lower() for listing in listings)


def test_poorvika_registry_and_vendor_links():
    settings = Settings(
        database_url="sqlite:///./test.db",
        enabled_sources_raw="poorvika",
    )
    registry = SourceRegistry(settings)

    scrapers_by_source = registry.build_scrapers_by_source()

    assert "poorvika" in registry.available_sources()
    assert "poorvika" in scrapers_by_source
    assert scrapers_by_source["poorvika"].vendor_name == "Poorvika"
    assert build_vendor_search_url("Poorvika", "iphone 15") == (
        "https://www.google.com/search?q=site%3Apoorvika.com+iphone+15"
    )
    assert canonicalize_vendor_product_url(
        "Poorvika",
        "https://www.poorvika.com/apple-iphone-15-blue-128gb/p?source=test",
        "https://www.poorvika.com",
    ) == "https://www.poorvika.com/apple-iphone-15-blue-128gb/p"
