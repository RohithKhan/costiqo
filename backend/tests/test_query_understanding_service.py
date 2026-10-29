from app.services.query_understanding_service import assess_query_clarity, understand_query


def test_known_appliance_brand_query_is_clear():
    clarity = assess_query_clarity("daikin", understand_query("daikin"))

    assert clarity.is_clear


def test_single_category_query_is_allowed_through_to_scrapers():
    clarity = assess_query_clarity("foobar", understand_query("foobar"))

    assert clarity.is_clear
