from datetime import date, timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select

from app.db.models.offline_quote import OfflineQuote
from app.db.models.purchase_record import PurchaseRecord
from app.db.models.purchase_record_quote import PurchaseRecordQuote
from app.db.models.user import User
from app.db.session import get_session_factory


@pytest.fixture
def admin_headers(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Admin User",
            "email": "admin@example.com",
            "password": "supersecure",
        },
    )
    assert response.status_code == 201
    token = response.json()["access_token"]

    with get_session_factory()() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert user is not None
        user.role = "admin"
        db.commit()

    return {"Authorization": f"Bearer {token}"}


def _create_approved_quote(client, admin_headers, product_id, supplier_name="Test Supplier", price=50000):
    quote_resp = client.post(
        "/api/v1/admin/offline-quotes",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": supplier_name,
            "quoted_price": price,
            "shipping_cost": 200,
            "seller_location": "Bengaluru",
            "pincode": "560001",
            "estimated_delivery_days": 3,
            "contact_name": "Test Agent",
            "contact_phone": "9876543210",
        },
    )
    assert quote_resp.status_code == 201
    quote = quote_resp.json()

    # Move to approved
    approve_resp = client.patch(
        f"/api/v1/admin/offline-quotes/{quote['id']}",
        headers=admin_headers,
        json={"status": "approved"},
    )
    assert approve_resp.status_code == 200
    return approve_resp.json()


def test_create_and_retrieve_purchase_with_associated_quotes(client, admin_headers):
    # 1. Get a product
    search_resp = client.get("/api/v1/products/search", params={"q": "iphone 15"})
    assert search_resp.status_code == 200
    product_id = search_resp.json()["results"][0]["id"]

    # 2. Create two approved quotes
    quote1 = _create_approved_quote(client, admin_headers, product_id, "Supplier Alpha", 62000)
    quote2 = _create_approved_quote(client, admin_headers, product_id, "Supplier Beta", 61500)

    # 3. Create a purchase associating both quotes
    purchase_resp = client.post(
        "/api/v1/admin/purchases",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": "Supplier Beta",
            "unit_price": 61500,
            "quantity": 1,
            "shipping_cost": 200,
            "related_quote_ids": [quote1["id"], quote2["id"]],
            "reference_number": "PO-PERSIST-1",
        },
    )
    assert purchase_resp.status_code == 201
    created_purchase = purchase_resp.json()
    assert set(created_purchase["related_quote_ids"]) == {quote1["id"], quote2["id"]}

    # 4. Verify quotes have moved to purchased
    quotes_resp = client.get(f"/api/v1/products/{product_id}/offline-quotes")
    assert quotes_resp.status_code == 200
    quotes_by_id = {q["id"]: q for q in quotes_resp.json()}
    assert quotes_by_id[quote1["id"]]["status"] == "purchased"
    assert quotes_by_id[quote1["id"]]["is_active"] is False
    assert quotes_by_id[quote2["id"]]["status"] == "purchased"
    assert quotes_by_id[quote2["id"]]["is_active"] is False

    # 5. Retrieve purchases and verify persisted related_quote_ids
    purchases_resp = client.get(f"/api/v1/products/{product_id}/purchases")
    assert purchases_resp.status_code == 200
    purchases = purchases_resp.json()
    matching = [p for p in purchases if p["id"] == created_purchase["id"]]
    assert len(matching) == 1
    assert set(matching[0]["related_quote_ids"]) == {quote1["id"], quote2["id"]}

    # 6. Verify directly in the database via association table
    db = get_session_factory()()
    try:
        associations = list(
            db.scalars(
                select(PurchaseRecordQuote).where(
                    PurchaseRecordQuote.purchase_record_id == created_purchase["id"]
                )
            ).all()
        )
        assert len(associations) == 2
        assert {a.offline_quote_id for a in associations} == {quote1["id"], quote2["id"]}
    finally:
        db.close()


def test_create_and_retrieve_purchase_without_quotes(client, admin_headers):
    search_resp = client.get("/api/v1/products/search", params={"q": "iphone 15"})
    assert search_resp.status_code == 200
    product_id = search_resp.json()["results"][0]["id"]

    purchase_resp = client.post(
        "/api/v1/admin/purchases",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": "Direct Purchase",
            "unit_price": 70000,
            "quantity": 1,
            "shipping_cost": 0,
            "related_quote_ids": [],
            "reference_number": "PO-NO-QUOTES",
        },
    )
    assert purchase_resp.status_code == 201
    created_purchase = purchase_resp.json()
    assert created_purchase["related_quote_ids"] == []

    purchases_resp = client.get(f"/api/v1/products/{product_id}/purchases")
    assert purchases_resp.status_code == 200
    matching = [p for p in purchases_resp.json() if p["id"] == created_purchase["id"]]
    assert len(matching) == 1
    assert matching[0]["related_quote_ids"] == []


def test_purchase_with_invalid_or_nonexistent_quote_ids(client, admin_headers):
    search_resp = client.get("/api/v1/products/search", params={"q": "iphone 15"})
    product_id_1 = search_resp.json()["results"][0]["id"]
    search_resp_2 = client.get("/api/v1/products/search", params={"q": "redmi"})
    product_id_2 = search_resp_2.json()["results"][0]["id"]

    # Quote belongs to product 2
    quote_p2 = _create_approved_quote(client, admin_headers, product_id_2, "P2 Supplier", 22000)

    # 1. Nonexistent quote ID -> 404
    resp = client.post(
        "/api/v1/admin/purchases",
        headers=admin_headers,
        json={
            "product_id": product_id_1,
            "supplier_name": "Invalid Test",
            "unit_price": 65000,
            "related_quote_ids": [999999],
        },
    )
    assert resp.status_code == 404
    assert "not found for this product" in resp.json()["detail"]

    # 2. Quote for another product -> 404 (avoid cross-product quote association)
    resp = client.post(
        "/api/v1/admin/purchases",
        headers=admin_headers,
        json={
            "product_id": product_id_1,
            "supplier_name": "Cross Product Test",
            "unit_price": 65000,
            "related_quote_ids": [quote_p2["id"]],
        },
    )
    assert resp.status_code == 404
    assert "not found for this product" in resp.json()["detail"]

    # 3. Quote in 'submitted' status (not approved) -> 400
    unapproved_resp = client.post(
        "/api/v1/admin/offline-quotes",
        headers=admin_headers,
        json={
            "product_id": product_id_1,
            "supplier_name": "Unapproved Supplier",
            "quoted_price": 63000,
        },
    )
    assert unapproved_resp.status_code == 201
    unapproved_id = unapproved_resp.json()["id"]

    resp = client.post(
        "/api/v1/admin/purchases",
        headers=admin_headers,
        json={
            "product_id": product_id_1,
            "supplier_name": "Unapproved Purchase",
            "unit_price": 63000,
            "related_quote_ids": [unapproved_id],
        },
    )
    assert resp.status_code == 400
    assert "cannot move from submitted to purchased" in resp.json()["detail"]


def test_purchase_duplicate_quote_associations(client, admin_headers):
    search_resp = client.get("/api/v1/products/search", params={"q": "iphone 15"})
    product_id = search_resp.json()["results"][0]["id"]
    quote = _create_approved_quote(client, admin_headers, product_id, "Dupe Supplier", 64000)

    # 1. Duplicate IDs in the same request payload -> 400
    dupe_resp = client.post(
        "/api/v1/admin/purchases",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": "Dupe Supplier",
            "unit_price": 64000,
            "related_quote_ids": [quote["id"], quote["id"]],
        },
    )
    assert dupe_resp.status_code == 400
    assert "Duplicate related quote IDs are not allowed" in dupe_resp.json()["detail"]

    # 2. Purchase 1 succeeds
    p1_resp = client.post(
        "/api/v1/admin/purchases",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": "Dupe Supplier",
            "unit_price": 64000,
            "related_quote_ids": [quote["id"]],
            "reference_number": "PO-DUPE-1",
        },
    )
    assert p1_resp.status_code == 201

    # 3. Attempting to associate the same already-associated quote to Purchase 2 -> 400
    p2_resp = client.post(
        "/api/v1/admin/purchases",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": "Dupe Supplier",
            "unit_price": 64000,
            "related_quote_ids": [quote["id"]],
            "reference_number": "PO-DUPE-2",
        },
    )
    assert p2_resp.status_code == 400
    assert "already associated" in p2_resp.json()["detail"] or "already been purchased" in p2_resp.json()["detail"]


def test_transaction_rollback_when_association_fails(client, admin_headers):
    search_resp = client.get("/api/v1/products/search", params={"q": "iphone 15"})
    product_id = search_resp.json()["results"][0]["id"]

    # Create approved quote
    quote = _create_approved_quote(client, admin_headers, product_id, "Rollback Supplier", 62500)

    # Count existing purchases
    db = get_session_factory()()
    initial_purchases_count = len(list(db.scalars(select(PurchaseRecord)).all()))
    initial_associations_count = len(list(db.scalars(select(PurchaseRecordQuote)).all()))
    db.close()

    # Attempt purchase with 1 valid quote and 1 invalid quote ID (99999)
    fail_resp = client.post(
        "/api/v1/admin/purchases",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": "Rollback Supplier",
            "unit_price": 62500,
            "related_quote_ids": [quote["id"], 99999],
            "reference_number": "PO-SHOULD-FAIL",
        },
    )
    assert fail_resp.status_code == 404

    # Verify transaction rollback in database:
    db = get_session_factory()()
    try:
        # No new purchase record was created
        current_purchases = list(db.scalars(select(PurchaseRecord)).all())
        assert len(current_purchases) == initial_purchases_count

        # No new association was created
        current_associations = list(db.scalars(select(PurchaseRecordQuote)).all())
        assert len(current_associations) == initial_associations_count

        # The valid quote's status is still "approved" and was NOT marked "purchased"
        refreshed_quote = db.get(OfflineQuote, quote["id"])
        assert refreshed_quote.status == "approved"
        assert refreshed_quote.is_active is True
        assert refreshed_quote.closed_at is None
    finally:
        db.close()


def test_existing_procurement_api_compatibility(client, admin_headers):
    # Verify summary, list, and quote endpoints continue to work as expected
    search_resp = client.get("/api/v1/products/search", params={"q": "iphone 15"})
    product_id = search_resp.json()["results"][0]["id"]

    summary_resp = client.get(
        "/api/v1/admin/procurement/summary",
        headers=admin_headers,
        params={"product_id": product_id},
    )
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert "quote_status_breakdown" in summary
    assert "active_quotes" in summary
    assert "supplier_competitiveness" in summary
    assert summary["product_id"] == product_id

    purchases_resp = client.get(f"/api/v1/products/{product_id}/purchases")
    assert purchases_resp.status_code == 200
    assert isinstance(purchases_resp.json(), list)
