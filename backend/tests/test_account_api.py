import pytest
from sqlalchemy import create_engine, text


@pytest.fixture
def user_headers(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Saved Items User",
            "email": "saved@example.com",
            "password": "supersecure",
        },
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_saved_products_searches_and_alerts_crud(client, user_headers):
    search_response = client.get("/api/v1/products/search", params={"q": "iphone 15"})
    assert search_response.status_code == 200
    product = search_response.json()["results"][0]
    product_id = product["id"]

    save_product_response = client.post(
        "/api/v1/me/saved-products",
        headers=user_headers,
        json={
            "product_name": product["canonical_name"],
            "product_url": product["best_product_url"],
        },
    )
    assert save_product_response.status_code == 201
    saved_product = save_product_response.json()
    assert saved_product["product_name"] == "Apple iPhone 15 128 GB"
    assert saved_product["product_url"] == product["best_product_url"]

    duplicate_product_response = client.post(
        "/api/v1/me/saved-products",
        headers=user_headers,
        json={
            "product_name": product["canonical_name"],
            "product_url": product["best_product_url"],
        },
    )
    assert duplicate_product_response.status_code == 409

    save_search_response = client.post(
        "/api/v1/me/saved-searches",
        headers=user_headers,
        json={
            "query": "iphone 15",
            "location": "Bengaluru",
            "pincode": "560001",
        },
    )
    assert save_search_response.status_code == 201
    saved_search = save_search_response.json()
    assert saved_search["query"] == "iphone 15"
    assert saved_search["pincode"] == "560001"

    alert_response = client.post(
        "/api/v1/me/alerts",
        headers=user_headers,
        json={
            "product_id": product_id,
            "target_price": 68000,
        },
    )
    assert alert_response.status_code == 201
    alert_rule = alert_response.json()
    assert alert_rule["product"]["id"] == product_id
    assert alert_rule["target_price"] == 68000
    assert alert_rule["is_active"] is True

    query_alert_response = client.post(
        "/api/v1/me/alerts",
        headers=user_headers,
        json={
            "query": "redmi note 13 pro",
            "location": "Bengaluru",
            "pincode": "560001",
            "target_price": 23000,
        },
    )
    assert query_alert_response.status_code == 201
    query_alert = query_alert_response.json()
    assert query_alert["query"] == "redmi note 13 pro"
    assert query_alert["product"] is None

    list_products_response = client.get("/api/v1/me/saved-products", headers=user_headers)
    list_searches_response = client.get("/api/v1/me/saved-searches", headers=user_headers)
    list_alerts_response = client.get("/api/v1/me/alerts", headers=user_headers)

    assert list_products_response.status_code == 200
    assert list_searches_response.status_code == 200
    assert list_alerts_response.status_code == 200
    assert len(list_products_response.json()) == 1
    assert len(list_searches_response.json()) == 1
    assert len(list_alerts_response.json()) == 2

    update_alert_response = client.patch(
        f"/api/v1/me/alerts/{alert_rule['id']}",
        headers=user_headers,
        json={"is_active": False, "target_price": 67000},
    )
    assert update_alert_response.status_code == 200
    updated_alert = update_alert_response.json()
    assert updated_alert["is_active"] is False
    assert updated_alert["target_price"] == 67000

    delete_query_alert_response = client.delete(
        f"/api/v1/me/alerts/{query_alert['id']}",
        headers=user_headers,
    )
    delete_alert_response = client.delete(
        f"/api/v1/me/alerts/{alert_rule['id']}",
        headers=user_headers,
    )
    delete_search_response = client.delete(
        f"/api/v1/me/saved-searches/{saved_search['id']}",
        headers=user_headers,
    )
    delete_product_response = client.delete(
        f"/api/v1/me/saved-products/{saved_product['id']}",
        headers=user_headers,
    )

    assert delete_query_alert_response.status_code == 204
    assert delete_alert_response.status_code == 204
    assert delete_search_response.status_code == 204
    assert delete_product_response.status_code == 204

    final_alerts_response = client.get("/api/v1/me/alerts", headers=user_headers)
    assert final_alerts_response.status_code == 200
    assert final_alerts_response.json() == []


def test_account_routes_require_authentication(client):
    response = client.get("/api/v1/me/saved-products")

    assert response.status_code == 401


def test_change_password_and_delete_account(client):
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Password User",
            "email": "password@example.com",
            "password": "supersecure",
        },
    )
    assert register_response.status_code == 201
    token = register_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    bad_change_response = client.patch(
        "/api/v1/me/password",
        headers=headers,
        json={
            "current_password": "wrongsecure",
            "new_password": "newsecurepass",
        },
    )
    assert bad_change_response.status_code == 400

    change_response = client.patch(
        "/api/v1/me/password",
        headers=headers,
        json={
            "current_password": "supersecure",
            "new_password": "newsecurepass",
        },
    )
    assert change_response.status_code == 204

    old_login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "password@example.com", "password": "supersecure"},
    )
    assert old_login_response.status_code == 401

    new_login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "password@example.com", "password": "newsecurepass"},
    )
    assert new_login_response.status_code == 200

    delete_response = client.delete("/api/v1/me/account", headers=headers)
    assert delete_response.status_code == 204

    me_response = client.get("/api/v1/auth/me", headers=headers)
    assert me_response.status_code == 401


def test_legacy_saved_product_schema_self_heals(client):
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Legacy User",
            "email": "legacy@example.com",
            "password": "supersecure",
        },
    )
    assert register_response.status_code == 201
    user = register_response.json()["user"]
    headers = {"Authorization": f"Bearer {register_response.json()['access_token']}"}

    search_response = client.get("/api/v1/products/search", params={"q": "iphone 15"})
    assert search_response.status_code == 200
    product = search_response.json()["results"][0]

    engine = create_engine(client.app.state.settings.database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE saved_products"))
        connection.execute(
            text(
                """
                CREATE TABLE saved_products (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    CONSTRAINT uq_saved_product_user_product UNIQUE (user_id, product_id)
                )
                """
            )
        )
        connection.execute(text("CREATE INDEX ix_saved_products_user_id ON saved_products (user_id)"))
        connection.execute(text("CREATE INDEX ix_saved_products_product_id ON saved_products (product_id)"))
        connection.execute(
            text(
                """
                INSERT INTO saved_products (id, user_id, product_id, created_at)
                VALUES (1, :user_id, :product_id, '2026-06-09 00:00:00')
                """
            ),
            {"user_id": user["id"], "product_id": product["id"]},
        )

    list_response = client.get("/api/v1/me/saved-products", headers=headers)
    assert list_response.status_code == 200
    saved_products = list_response.json()
    assert saved_products[0]["product_name"] == "Apple iPhone 15 128 GB"
    assert saved_products[0]["product_url"] == product["best_product_url"]

    save_response = client.post(
        "/api/v1/me/saved-products",
        headers=headers,
        json={
            "product_name": "External bookmark",
            "product_url": "https://example.com/external-bookmark",
        },
    )
    assert save_response.status_code == 201
