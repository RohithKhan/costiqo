# Costiqo

Costiqo is a price benchmarking app for comparing electronics and hardware offers across Indian online vendors. It has a FastAPI backend, a React/Vite frontend, SQLAlchemy persistence, direct vendor scrapers, optional OpenRouter candidate validation, and account/admin workflows.

Demo: https://costiqo.vercel.app/

## Repository Layout

- `backend/` - FastAPI app, SQLAlchemy models, Alembic migrations, scraper and comparison services.
- `frontend/` - React/Vite client.
- `docker-compose.yml` - Postgres, Redis, backend, worker, and frontend stack for containerized runs.
- `render.yaml` - Render deployment blueprint.
- `start-local.sh` - Local development launcher for backend and frontend.
- `env.example` - Sanitized environment template. It intentionally leaves Neon, OpenRouter, Redis cloud URLs, and production CORS values blank or local-only.

## Local Setup

From this directory:

```bash
cp env.example .env

cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium

cd ../frontend
npm install

cd ..
./start-local.sh
```

Defaults:

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:7070`
- API base: `http://127.0.0.1:7070/api/v1`
- Local database: `backend/local-dev.db`

For containerized development, run `docker compose up --build`. The Docker stack exposes the backend on port `8000` and the frontend on port `5173`.

## Environment Notes

Do not commit real `.env` files. Use `env.example` as the starting point.

Important variables:

- `DATABASE_URL` - Local SQLite or non-Neon database URL.
- `NEON_DATABASE_URL` - Optional Neon Postgres URL. Leave blank locally unless deploying against Neon.
- `SECRET_KEY` - JWT signing secret. Replace before production deploys.
- `CORS_ORIGINS_RAW` - Comma-separated allowed frontend origins. The example only includes local dev origins.
- `VITE_API_BASE_URL` - Frontend API base URL.
- `OPENROUTER_KEY` - Optional OpenRouter API key for LLM-based candidate validation.
- `QUEUE_BACKEND` - `inline` for local development, `rq` when running worker/Redis.
- `REDIS_URL` - Required when `QUEUE_BACKEND=rq`.

## API

FastAPI generates the full OpenAPI docs at:

- Swagger UI: `/docs`
- OpenAPI JSON: `/openapi.json`
- Health check: `/health`

All application routes below use the `/api/v1` prefix.

| Method | Endpoint | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | Public | Create a user and return a bearer token. |
| `POST` | `/auth/login` | Public | Login with `username` and `password`. |
| `GET` | `/auth/me` | User | Return the current authenticated user. |
| `GET` | `/products/search?q=` | Public | Search products and vendor offers. |
| `GET` | `/products/suggestions?q=` | Public | Return autocomplete/search suggestions. |
| `GET` | `/products/{product_id}` | Public | Return product detail and ranked offers. |
| `GET` | `/products/{product_id}/vendors` | Public | List vendor listings for a product. |
| `GET` | `/products/{product_id}/reviews` | Public | List collected reviews. |
| `GET` | `/products/{product_id}/sentiment` | Public | Return sentiment summary. |
| `GET` | `/products/{product_id}/history` | Public | Return product price history. |
| `GET` | `/vendors/{vendor_product_id}/history` | Public | Return vendor listing price history. |
| `GET` | `/products/{product_id}/offline-quotes` | Public | List offline quotes for procurement comparison. |
| `GET` | `/products/{product_id}/purchases` | Public | List purchase records. |
| `GET` | `/comparisons?q=` | Optional user | Compare offers for a query. Supports `location`, `pincode`, `ranking_mode`, and `progress_id`. |
| `GET` | `/comparisons/progress/{progress_id}` | Public | Poll comparison search progress. |
| `GET` | `/locations/pincode?pincode=` | Public | Verify/resolve pincode context. |
| `GET` | `/vendors` | Public | List vendor status records. |
| `GET` | `/me/saved-products` | User | List saved products. |
| `POST` | `/me/saved-products` | User | Save a product link. |
| `DELETE` | `/me/saved-products/{id}` | User | Remove a saved product. |
| `GET` | `/me/saved-searches` | User | List saved searches. |
| `POST` | `/me/saved-searches` | User | Save a search query. |
| `DELETE` | `/me/saved-searches/{id}` | User | Remove a saved search. |
| `GET` | `/me/alerts` | User | List alert rules. |
| `POST` | `/me/alerts` | User | Create an alert rule. |
| `PATCH` | `/me/alerts/{id}` | User | Update alert status or target price. |
| `DELETE` | `/me/alerts/{id}` | User | Delete an alert. |
| `PATCH` | `/me/password` | User | Change account password. |
| `DELETE` | `/me/account` | User | Delete the current account. |
| `POST` | `/admin/scrape` | Admin | Trigger a scrape job. |
| `GET` | `/admin/jobs/{job_id}` | Admin | Read scrape job status. |
| `GET` | `/admin/vendors` | Admin | List vendor status records. |
| `POST` | `/admin/offline-quotes` | Admin | Create an offline quote. |
| `PATCH` | `/admin/offline-quotes/{quote_id}` | Admin | Update an offline quote. |
| `POST` | `/admin/purchases` | Admin | Create a purchase record. |
| `GET` | `/admin/procurement/summary?product_id=` | Admin | Return procurement summary for a product. |

Use `Authorization: Bearer <access_token>` for user and admin routes. `ranking_mode` accepts `recommended`, `cheapest`, `fastest_delivery`, `best_value`, and `best_reviewed`.

## Developer Notes

- Keep local secrets in `.env` only. The copied repo should not contain real Neon URLs, OpenRouter keys, or production CORS origins.
- `OPENROUTER_KEY` is optional. Without it, validation falls back to local heuristics.
- The backend reads environment files from `../.env` and `.env` relative to the backend process. Running from the repo root with `start-local.sh` uses the root `.env`.
- `AUTO_CREATE_SCHEMA=true` is convenient for local SQLite. For shared databases, prefer Alembic migrations.
- Some deployment files may include older provider variable names. Treat `backend/app/core/config.py` as the source of truth for active backend settings.
- Direct vendor scraping can be slow or brittle because it depends on vendor websites. Keep timeouts conservative and test scraper changes against representative product queries.
