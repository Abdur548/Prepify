# Prepify — Cambridge 9618 preparation workspace

Prepify turns an authorized collection of Cambridge International AS & A Level Computer Science (9618) question papers and their matching mark schemes into reviewed question records, real-question mock papers, answer surfaces, grading evidence, analytics, guided help, and learning-resource links.

The current ingestion boundary is intentionally small:

- ingest question papers (`qp`) and matching mark schemes (`ms`);
- do not ingest examiner reports (`er`), inserts (`in`), or syllabus PDFs;
- assemble full mock papers from reviewed real questions across multiple historical series;
- keep each selected question connected to reviewed evidence from its own matching mark scheme;
- exclude questions that require insert/data files until that dependency workflow is restored deliberately;
- keep generated MCQs as supplementary practice, never as hidden content inside a real-question mock.

The reference screenshots supplied during development were used only to identify feature categories. Prepify has its own dark terminal/document visual language and its own product logic.

## What exists now

The repository contains:

- a Python/FastAPI backend;
- PostgreSQL metadata storage through SQLAlchemy;
- Qdrant-backed retrieval for reviewed question and mark-scheme blocks;
- PDF text extraction plus Qwen3-VL OCR fallback;
- an OCR review queue for risky pseudocode/code extraction;
- real-question paper assembly with deterministic selection and multi-series diversity;
- a provisional Paper 4 execution grader with Docker isolation and a validation gate;
- separate MCQ, code/pseudocode, and structured-written frontend surfaces;
- a Prep-Panel with Dashboard, Analytics, Prep-bot, Resources, and Exam workspace;
- a server-side Gemini Prep-bot integration;
- device-local cross-surface attempt analytics.

MVP2 Phase 2 (pseudocode transpile-and-execute) and Phase 3 (written award-condition grading) remain gated and are not presented as complete.

## Important content and copyright boundary

Prepify does **not** contain a web scraper that downloads copyrighted exam papers from third-party sites. The supported flow starts with PDFs that the operator is legally allowed to use—such as files supplied by an authorized school, teacher, learner account, or other licensed source.

Do not crawl Cambridge or unofficial mirror sites without permission. Do not republish a bulk paper library publicly. Before production use, obtain legal review covering storage, display, retention, access control, and takedown procedures. Prepify is not affiliated with or endorsed by Cambridge International.

## How papers and answers enter the system

The phrase “scraping exams” is better understood here as a controlled ingestion job:

1. An operator places authorized QP/MS PDF pairs in a private source directory.
2. Filenames identify the syllabus, series, document type, paper, and variant.
3. Embedded PDF text is extracted when reliable; image pages use the configured vision OCR endpoint.
4. Text is segmented into question or mark-scheme blocks with question numbers and marks.
5. Risky OCR blocks enter a human review queue.
6. A question record is created from each reviewed question-paper block.
7. The matching mark-scheme PDF is located using `(syllabus, series, paper code)`.
8. Mark-scheme blocks with the same question number are attached to that question.
9. Only reviewed question and mark-scheme blocks are indexed for retrieval.
10. A separate reviewed presentation manifest authorizes question delivery and defines subparts/AO marks.
11. The assembler selects real questions across multiple series and stores the relevant mark-scheme block IDs privately with each assembled item.
12. Student answers are submitted through the surface designed for that answer type. The frontend sends raw code/pseudocode unchanged.

The matching convention is exact. For example:

```text
9618_s23_qp_21.pdf
9618_s23_ms_21.pdf
```

Both files resolve to the same link key: syllabus `9618`, series `s23`, paper code `21`.

Unsupported filenames, including `9618_s23_in_21.pdf` and examiner-report names, are rejected by the current ingestion contract. Keep those files outside the ingestion directory.

## Architecture

```mermaid
flowchart LR
    A["Authorized QP/MS PDFs"] --> B["Extract embedded text or OCR"]
    B --> C["Review queue"]
    C --> D["Question blocks"]
    C --> E["Matching mark-scheme blocks"]
    D --> F["Reviewed question pool"]
    E --> F
    F --> G["Multi-series exam assembler"]
    G --> H["MCQ / code / written surfaces"]
    H --> I["Grader-specific feedback"]
    I --> J["Device-local analytics"]
    K["Gemini Interactions API"] --> L["Server-side Prep-bot endpoint"]
    L --> H
```

For the complete stage-by-stage contract, read [pipeline.md](./pipeline.md). Current status is in [progress.md](./progress.md), and implementation recommendations are in [suggestions.md](./suggestions.md).

## Beginner setup on Windows

The commands below assume PowerShell and the repository at `E:\Prepify`.

### 1. Install prerequisites

Install:

- Git;
- Python 3.11 or newer;
- Node.js 22.13 or newer;
- Docker Desktop;
- PostgreSQL 16, either locally or in Docker.

Verify:

```powershell
git --version
py --version
node --version
docker --version
```

### 2. Start PostgreSQL

If you do not already have PostgreSQL, this Docker command creates a local development database:

```powershell
docker run --name prepify-postgres `
  -e POSTGRES_USER=prepify `
  -e POSTGRES_PASSWORD=prepify `
  -e POSTGRES_DB=prepify `
  -p 5432:5432 `
  -d postgres:16
```

On later days, start the same container with:

```powershell
docker start prepify-postgres
```

### 3. Create the Python environment

```powershell
Set-Location E:\Prepify
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, run this once in the current window and activate again:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### 4. Configure environment variables

```powershell
Copy-Item .env.example .env
notepad .env
```

Minimum local configuration:

```dotenv
DATABASE_URL=postgresql+psycopg://prepify:prepify@localhost:5432/prepify
QDRANT_URL=
QDRANT_STORAGE_PATH=./qdrant_storage
GEMINI_API_KEY=your-server-side-key
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Set `OCR_API_KEY` and `OCR_BASE_URL` only if scanned/image PDFs need OCR. Set `LLM_API_KEY` for generated practice MCQs and explanation services.

Never place `GEMINI_API_KEY`, `OCR_API_KEY`, or `LLM_API_KEY` in `frontend/.env`. Browser-exposed environment variables are public.

### 5. Initialize the database

```powershell
python -m prepify.ingestion.cli init-db
```

This project currently uses `SQLAlchemy.create_all`. If you ran an earlier schema containing `syllabus_document_id`, reset the development database or add a migration before using the new fields `source_document_ids`, `minimum_source_series`, and `source_series`.

For a disposable local Docker database, reset with:

```powershell
docker rm -f prepify-postgres
```

Then repeat the PostgreSQL creation command. Do not do this against a database containing important data.

### 6. Prepare authorized PDF pairs

Create a private folder outside the public frontend, for example:

```text
E:\PrepifyData\9618\
  9618_s23_qp_31.pdf
  9618_s23_ms_31.pdf
  9618_w24_qp_31.pdf
  9618_w24_ms_31.pdf
```

Use at least two historical series for a mock-paper pool. Do not put `er`, `in`, or other PDFs in this folder.

### 7. Ingest and review

```powershell
python -m prepify.ingestion.cli ingest E:\PrepifyData\9618
python -m prepify.ingestion.cli reviews
```

For each block that a human verifies against the source PDF:

```powershell
python -m prepify.ingestion.cli approve BLOCK_ID_FROM_REVIEW_OUTPUT
```

Approval triggers indexing for blocks that are ready.

### 8. Load the reviewed exam contracts

Ingestion creates source records; it does not automatically authorize every extracted block for student delivery. A reviewer must prepare two manifests:

- a paper specification derived from reviewed historical paper structures;
- a question-pool presentation manifest.

Templates:

- [paper_specification.example.json](./examples/paper_specification.example.json)
- [question_pool.example.json](./examples/question_pool.example.json)

Replace every placeholder ID with IDs from your database/review workflow, then run:

```powershell
python -m prepify.assembly.cli load-specification .\my-paper-3-spec.json
python -m prepify.assembly.cli load-pool .\my-paper-3-pool.json
```

The loader fails closed when:

- a cited source is not a question paper;
- source papers do not match the requested paper number;
- fewer than the required historical series are cited;
- a question or its matching mark-scheme block has not passed review;
- marks/AO totals do not reconcile;
- generated MCQs are requested inside a full assembled exam;
- the question depends on an insert/data file.

### 9. Start the API

```powershell
python -m uvicorn prepify.api.main:app --reload --host 127.0.0.1 --port 8000
```

Check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
Invoke-RestMethod http://127.0.0.1:8000/v1/topics
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

### 10. Start the frontend

Open a second PowerShell window:

```powershell
Set-Location E:\Prepify\frontend
Copy-Item .env.example .env.local -ErrorAction SilentlyContinue
```

Create or edit `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_SITE_URL=http://localhost:3000
```

Then:

```powershell
npm install
npm run dev
```

Open `http://localhost:3000`.

## Prep-Panel behavior

### Dashboard

Shows evidenced scores, topic signals, grader readiness, and direct routes into the rest of Prepify. It does not fabricate progress when no real attempt exists.

### Analytics

Tracks more than MCQs:

- evidenced marks;
- MCQ accuracy;
- Paper 4 test-case pass rate;
- written award-condition hit rate when that grader becomes available;
- completion, topics, and attempt history.

Gated or ungraded responses are excluded, not treated as zero. MVP analytics are stored in browser `localStorage` under `prepify.attempts.v1`; they are device-local, not account-synced.

### Prep-bot

The browser calls `POST /v1/prep-bot/chat`. The backend then calls Gemini’s Interactions API with `store: false`, a short bounded history, and a 9618 tutoring system instruction. The bot helps with concepts, debugging strategy, study planning, and product navigation; it cannot issue official marks.

Current Gemini implementation references:

- [Interactions API overview](https://ai.google.dev/gemini-api/docs/interactions-overview)
- [Interactions API reference](https://ai.google.dev/api/interactions-api-v1)
- [API key guidance](https://ai.google.dev/gemini-api/docs/generate-content/api-key)

### Resources

The frontend contains a small curated catalog linking to Cambridge’s subject/learner pages, Harvard CS50x, the official Python tutorial, freeCodeCamp, and Craig ’n’ Dave. These are links, not copied course content. Review the catalog periodically for changed URLs and suitability.

### Exam workspace

Full-paper assembly uses only `past_paper` sources. Supplementary generated MCQs remain available as a separately labeled practice demo/path. Strict exam mode removes the Prep-Panel to avoid distraction and does not allow timer pause.

## API summary

| Method | Route | Purpose |
|---|---|---|
| GET | `/healthz` | Service health |
| GET | `/v1/topics` | Supported topic tags |
| GET | `/v1/capabilities` | Grader and Prep-bot readiness |
| POST | `/v1/mcq/generate` | Supplementary grounded MCQ practice |
| POST | `/v1/questions/{id}/explain` | Non-scoring explanation/check |
| POST | `/v1/prep-bot/chat` | Stateless Gemini tutoring |
| POST | `/v1/exams/assemble` | Assemble a reviewed real-question paper |
| GET | `/v1/exams/{id}` | Reload an assembled paper without private answers/evidence |
| POST | `/v1/phase1/questions/{id}/grade-code` | Provisional Paper 4 execution grading |

## Verification

Backend:

```powershell
Set-Location E:\Prepify
python -m pytest -q
```

Frontend:

```powershell
Set-Location E:\Prepify\frontend
npm run lint
npm test
```

`npm test` performs a production Vinext build and checks server-rendered HTML plus source-level surface separation.

## Current limitations

- No automated Cambridge downloader or public paper redistribution.
- No insert/data-file ingestion; dependent questions are excluded.
- Paper specifications and presentation manifests require human review.
- Paper 4 grading remains provisional until the held-out validation gate passes.
- Paper 2 transpilation and Paper 1/3 award-condition grading are not implemented.
- Analytics are device-local and have no login/account sync.
- Prep-bot needs a configured server-side Gemini key and network access.
- Production deployment still needs a hosted API/database/vector store, secret management, backups, and an allowed frontend origin.

## Repository map

```text
prepify/
  api/                 FastAPI routes
  assembly/            reviewed manifests and multi-series selection
  generation/          supplementary MCQs and explanations
  ingestion/           filename contracts, PDF extraction, OCR, review
  phase1/              Paper 4 sandbox grading and validation
  prepbot/             Gemini Interactions API client
  retrieval/           Qdrant indexing, retrieval, reranking
  storage/             SQLAlchemy models and repositories
frontend/
  app/ExamWorkspace.tsx  strict exam and distinct answer surfaces
  app/PrepPortal.tsx     Prep-Panel, analytics, bot, resources
examples/               manifest and validation templates
tests/                  backend contract tests
```
