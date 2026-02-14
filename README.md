# Reconciliation Finance Platform (Phase 1)

Monorepo containing:
- `apps/web`: Next.js + shadcn frontend (BFF API routes)
- `services/agno_api`: FastAPI service for ingestion, reconciliation, and AI review chain
- `services/agno_worker`: worker entrypoint for async queue execution
- `packages/shared-types`: shared TypeScript domain types
- `infra`: docker compose and PocketBase bootstrap artifacts

## Quick start (local)

1. Frontend
```bash
pnpm --dir apps/web install
pnpm --dir apps/web dev
```

2. Agno API
```bash
cd services/agno_api
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8001
```

3. Worker
```bash
cd services/agno_worker
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m app.worker
```

## Docker
```bash
docker compose -f infra/docker-compose.yml up --build
```

## Docker Ready Setup (Recommended)

1. Create environment file:
```bash
cp .env.example .env
```

2. Set your OpenRouter key in `.env`:
```bash
OPENROUTER_API_KEY=your_key_here
```

3. Start all services:
```bash
docker compose -f infra/docker-compose.yml up -d
```

4. Open the app:
- Web: `http://localhost:3000`
- API: `http://localhost:8001/health`
- PocketBase: `http://localhost:8090`

## Scenario 3 acceptance
Dataset used:
- `/Users/skyjuice/Downloads/Dataset-1/scenario 3/scenario3_internal_10.csv`
- `/Users/skyjuice/Downloads/Dataset-1/scenario 3/scenario3_erp_10.csv`
- `/Users/skyjuice/Downloads/Dataset-1/scenario 3/scenario3_psp_10.csv`

Expected reconciliation outcome:
- `8` good transactions
- `2` doubtful transactions (`SCENARIO3-REF-001`, `SCENARIO3-REF-010`)
