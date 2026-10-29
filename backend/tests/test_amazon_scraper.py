from decimal import Decimal

from app.scrapers.amazon_scraper import AmazonScraper


def test_amazon_scraper_uses_asin_product_url_when_search_link_is_missing():
    scraper = AmazonScraper()

    listings = scraper._build_live_listings(
        "digital multimeter",
        [
            {
                "asin": "B097RS212G",
                "title": "Themisto TH-M98 Digital Multimeter (Black 2000 Counts)",
                "href": None,
                "image": "https://example.com/multimeter.jpg",
                "price": "₹798",
                "rating": "4.2 out of 5 stars",
                "reviews": "1,234",
            }
        ],
    )

    assert len(listings) == 1
    assert listings[0].product_url == "https://www.amazon.in/dp/B097RS212G"
    assert listings[0].price == Decimal("798.00")
