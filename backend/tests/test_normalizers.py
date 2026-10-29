from app.scrapers.normalizers import has_identifier_conflict, listing_matches_query
from app.utils.product_identity import are_model_keys_compatible


def test_listing_matches_query_allows_compact_brand_model_queries():
    assert listing_matches_query("hpvictus", "HP Victus 15")
    assert listing_matches_query("hpvictus", "HP Victus 16 Gaming Laptop")


def test_listing_matches_query_still_rejects_unrelated_titles():
    assert not listing_matches_query("hpvictus", "Dell Inspiron 15")


def test_identifier_conflict_rejects_wrong_model_variant():
    assert has_identifier_conflict("nothing 4a", "Nothing Phone (3a)")
    assert not has_identifier_conflict("macbook air", "Apple MacBook Air M2")
    assert has_identifier_conflict("nothing 4a pro", "Nothing Phone (4a)")
    assert not has_identifier_conflict("iphone 17", "Apple iPhone 17 Pro 256 GB")


def test_variant_conflict_ignores_display_terminology():
    title = "SONY BRAVIA 5 138.8 cm (55 inch) Ultra HD (4K) Mini LED Smart Google TV"
    assert listing_matches_query("sony bravia 55 inch", title)


def test_model_keys_ignore_brand_and_trailing_color_but_reject_wrong_variants():
    assert are_model_keys_compatible("apple-iphone-17-512-gb", "iphone-17-512-gb-sage")
    assert not are_model_keys_compatible("iphone-17-pro-256-gb", "iphone-17-pro-max-256-gb")
    assert not are_model_keys_compatible("iphone-17-256-gb", "iphone-17-512-gb")


def test_listing_matches_query_allows_variant_results_when_query_is_broad():
    assert listing_matches_query("iphone 17", "Apple iPhone 17 Pro 256 GB")
    assert listing_matches_query("boat airdopes 311", "boAt Airdopes 311 Pro")
    assert not listing_matches_query("iphone 17 plus", "Apple iPhone 17 256 GB")


def test_listing_matches_query_handles_aliases_ordinals_and_size_queries():
    assert listing_matches_query("airpods pro 2", "Apple AirPods Pro (2nd Generation)")
    assert listing_matches_query("ps5", "Sony PlayStation 5 Slim Disc Edition")
    assert listing_matches_query(
        "tv 55",
        "SONY BRAVIA 5 138.8 cm (55 inch) Ultra HD (4K) Mini LED Smart Google TV",
    )


def test_listing_matches_query_allows_omitted_parent_brand_when_product_family_matches():
    assert listing_matches_query(
        "Samsung Galaxy S25 Ultra 5G",
        "Galaxy S25 Ultra 5G (Titanium Whitesilver, 12GB RAM, 256GB Storage)",
    )
    assert not listing_matches_query(
        "Samsung washing machine",
        "LG 7 Kg 5 Star Fully Automatic Top Load Washing Machine",
    )


def test_listing_matches_query_rejects_accessories_even_when_full_query_is_in_title():
    assert not listing_matches_query(
        "Samsung Galaxy S25 Ultra 5G",
        "Heiger Crystal Camera Lens 5 in1 Protection Tempered Glass For Samsung Galaxy S25 Ultra 5G",
    )


def test_listing_matches_query_treats_construction_modifiers_as_generic():
    assert listing_matches_query(
        "Asian Paints wall putty",
        "Asian Paints Acrylic White 20 kg Putty",
    )
