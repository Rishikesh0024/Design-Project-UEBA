# UEBA Platform

An authenticated, seven-page User and Entity Behaviour Analytics workspace. The React application uses the FastAPI API for all dataset, activity, profile, detection, alert, and evaluation data. PostgreSQL is the system of record.

## Run locally

### 1. Configure PostgreSQL and the API

Create a PostgreSQL database and user, then configure the backend:

```bash
cd backend
```

Create `.env` from `.env.example` if needed (do not overwrite an existing local configuration). Set `DATABASE_URL` to the PostgreSQL connection string and replace `SECRET_KEY` with a strong random value. For example, generate a key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Install dependencies, apply the schema migration, and start the API:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`; interactive API documentation is at `http://localhost:8000/docs`.

### 2. Start the frontend

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Development mode enables the temporary login bypass from `frontend/.env.development`, so the dashboard opens without credentials. Pages continue to use the configured API for their data; if the API is unavailable or requires authentication, the workspace shows an API error or empty state. Set `VITE_API_URL` if the API is hosted somewhere other than `http://localhost:8000/api/v1`.

To restore the normal login flow locally, set `VITE_DEV_AUTH_BYPASS=false` in `frontend/.env.development` (or remove that setting), then restart Vite. Login and registration routes remain available at `/login` and `/register`. The Vite configuration rejects this bypass in production builds; do not enable it outside local development.

## Application pages

The primary navigation contains exactly seven pages:

1. Dashboard
2. Dataset Upload
3. Activity Explorer
4. Behaviour Profiles
5. Anomaly Detection
6. Alerts
7. Evaluation

Settings and logout are in the profile menu. The pages share a selected dataset and authenticated API client. Dataset uploads, profiles, events, model runs, risk windows, alerts, and analyst reviews are persisted through the API.

The Alerts page starts with a date-filtered risk summary, then shows highest-risk alerts with search, status/severity filters, pagination, evidence, and analyst investigation history. Evaluation includes historical completed-run comparisons and an interactive graph of observed user/resource/device event relationships. The graph is not an HGT prediction; unimplemented models and unavailable metrics are identified as such.

### Dataset ingestion

Upload one or more CSV files for a selected CERT release. Logon, File, Email, HTTP/Web, Removable Device, and role metadata files are supported. Column aliases are normalized, original event identifiers are retained, and validation reports include schema, record counts, missing values, duplicates, and skipped rows.

The Dataset Upload page also includes three reproducible **SYNTHETIC DEMO** datasets. They are generated locally with fixed seeds, explicitly labelled as synthetic rather than genuine CERT records, and loaded through the same CSV validation and preprocessing pipeline as uploaded data. Demo previews include schema, column types, sample records, user/role summaries, and activity counts. Loading a demo selects it as the active dataset; demo records can be reset or removed without deleting uploaded datasets. Demo labels identify only the generated scenario examples and are not claims about real-world malicious activity.

The demo APIs are `GET /api/datasets/demo` (catalog; `/catalog` is also available), `GET /api/datasets/demo/{demo_id}/preview`, and `POST /api/datasets/demo/{demo_id}/load`. Equivalent versioned routes remain available under `/api/v1/datasets/demo`. Demo imports are idempotent by seed/version. Run `alembic upgrade head` after updating the backend, then restart Uvicorn; an already-running older API process will continue returning 404 for routes that were added later. Development CORS permits localhost Vite ports; production still uses only the explicitly configured origins.

### Detection and evaluation

The current backend calculates empirical next-event transition surprise, historical user-resource edge novelty, and user/role median-and-MAD context scores. Fusion weights and the training window are configurable. Role-aware empirical thresholds use a global fallback.

**Architecture limitation:** the Causal Transformer, HGT relation decoder, ADWIN drift detector, and controlled threshold-update gate from the proposed research design are not implemented. The UI identifies this limitation and does not present the empirical scorers as those models. Evaluation shows only completed runs with usable held-out labels; no placeholder or fabricated metrics are included. Additional completed configurations can be compared through experiment history.

Metrics include precision, recall, F1, PR-AUC, ROC-AUC and ROC/precision-recall curve points when both held-out classes are present, false-positive rate, top-K precision, detection delay, alert volume, processing time, and peak process memory. CSV export downloads the selected experiment metrics; PDF export opens the browser print dialog.

## Verification

Run the complete backend and pipeline test suite from the backend directory so
the `app` package resolves to the FastAPI application:

```bash
cd backend
python -m pytest tests ../tests -v
```

Run the frontend tests and production build:

```bash
cd frontend
npm test
npm run build
```

## Legacy prototype

`app.py` and `ueba_app/` contain the earlier Streamlit prototype. It remains available for reference, but it uses in-process session state and is not the React application's data path.
