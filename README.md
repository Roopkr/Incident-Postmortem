# AI Incident Postmortem Copilot

## What this project does
This project helps SRE and platform teams reconstruct incidents faster by combining logs, alerts, deployment events, and incident metadata. It returns a structured postmortem with timeline, hypotheses, selected root cause, confidence score, and action items.

## How to run the project locally


### Python virtual environment
1. From project root, create a venv:
  python -m venv venv
2. Activate venv:
  .\venv\Scripts\Activate.ps1
3. Install dependencies:
  pip install -r backend/requirements.txt
4. Create `.env` in project root (see Environment Variables section below).
5. Run API:
  python -m backend.app
6. Test health:
  curl.exe http://127.0.0.1:5000/health, ** The IP may differ on your System.

### Run FE
1. Check the localhost's IP once flask app runs.
2. Copy the entire URL and open script.js file inside frontend folder.
3. Replace line no 13 with your localhost URL. Check existing for reference.
4. You can double click on the index.html file and open it in a browser.
5. You can upload the sample files provided in the sample_data and then Generate report from it.

### Required
- `OPENAI_API_KEY`: OpenAI API key used by `ChatOpenAI` and embeddings.

### Optional
- `LOG_LEVEL`: default `INFO`
- `FLASK_DEBUG`: `1` enables Flask debug mode locally
- `PORT`: default `5000`
- `OPENAI_EMBEDDING_MODEL`: default `text-embedding-3-small`

## GenAI workflow overview

### End-to-end flow
1. Client calls `POST /api/incidents/reconstruct` with uploaded files or JSON payload.
2. `routes.py` delegates to `IncidentService`.
3. `IncidentService` loads input (or defaults from `sample_data`), sanitizes logs, and retrieves optional RAG context from `rag_data`.
4. `LLMFactory` builds the chat model client.
5. `IncidentGraph` executes a 5-node workflow:
   - `incident_understanding`
   - `timeline_reconstruction`
   - `hypothesis_generation`
   - `evidence_evaluation`
   - `report_generation`
6. API returns structured postmortem JSON.

### How components connect
- API layer: `backend/app.py`, `backend/routes.py`
- Orchestration: `backend/services/incident_service.py`, `backend/graph/incident_graph.py`
- LLM and prompts: `backend/llm/llm_factory.py`, `backend/llm/prompts.py`
- Tools and preprocessing: `backend/tools/*.py`, `backend/preprocessing/parser.py`
- Validation and output shape: `backend/models/dtos.py`
- Safety/reliability: `backend/utils/sanitization.py` + parser/DTO fallbacks

## API quick reference

### `GET /health`
Basic health endpoint.

### `POST /api/logs/validate`
Validates log schema and timestamps.

### `POST /api/incidents/reconstruct`
Accepts:
- `multipart/form-data` files:
  - `logs_file` (CSV)
  - `alerts_file` (CSV)
  - `deployments_file` (CSV)
  - `ticket_file` (JSON)
- or JSON body:
```json
{
  "logs": [],
  "alerts": [],
  "deployments": [],
  "incident_ticket": {}
}
```

If no data is sent, sample files under `sample_data/` are used.