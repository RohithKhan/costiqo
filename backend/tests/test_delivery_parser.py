from app.utils.delivery_parser import infer_delivery_days, infer_shipping_cost


def test_infer_delivery_days_handles_relative_phrases():
    assert infer_delivery_days("Delivery by tomorrow") == 1
    assert infer_delivery_days("Free next-day delivery") == 1
    assert infer_delivery_days("same-day shipping available") == 0
    assert infer_delivery_days("Estimated delivery in 4 days") == 4


def test_infer_shipping_cost_handles_free_and_paid_delivery():
    assert infer_shipping_cost("Free delivery tomorrow") == 0.0
    assert infer_shipping_cost("Delivery ₹40 | In stock online") == 40.0
    assert infer_shipping_cost("Shipping INR 199 extra") == 199.0
    assert infer_shipping_cost("Estimated delivery in 4 days") is None
