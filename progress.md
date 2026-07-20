# Prepify implementation progress

Status date: 15 July 2026

## Product decision now in force

The active pipeline has been simplified to question papers and their matching mark schemes.

Deferred:

- examiner-report ingestion;
- insert/data-file ingestion;
- syllabus-document ingestion;
- resource-dependent questions in assembled papers;
- generated questions inside full mock papers.

Full paper assembly now means reviewed real questions across historical series, with corresponding reviewed mark-scheme evidence attached privately to every selected item.

## Completed in the current revision

### Ingestion boundary

- Filename parsing accepts only `9618_{series}_qp_{paper}.pdf` and matching `ms` names.
- ER/IN names are explicitly rejected.
- OCR block typing is limited to question and mark-scheme content.
- Document linking attaches matching mark schemes and clears insert links.
- Qdrant creates only question and mark-scheme collections.
- Supplementary MCQ grounding now retrieves reviewed question-paper chunks instead of syllabus/examiner-report chunks.

### Assembly integrity

- Paper specifications cite reviewed historical question-paper documents rather than an ingested syllabus document.
- A specification sets a minimum number of source series; the minimum allowed value is two.
- Full-paper slots reject `validated_mcq` sources.
- Slot count must be capable of meeting the source-series requirement.
- The question-pool loader requires a reviewed question block.
- The question-pool loader also requires a matching mark-scheme document and reviewed matching mark-scheme block.
- Insert/data-file dependent presentations are rejected.
- The assembler excludes candidates without reviewed matching marking evidence.
- Selection gives a strong diversity priority until the required number of series has been reached.
- Assembly fails if final historical-series diversity is insufficient.
- Public questions include source series, paper code, and source question number.
- Internal assembly items retain `mark_scheme_chunk_ids`.
- Public assembly responses redact those private evidence IDs.
- Example specification and question-pool manifests were added.

### Prep-bot backend

- Added `GEMINI_API_KEY`, base URL, and model configuration.
- Added bounded request/response schemas.
- Added `GeminiPrepBotService` using the Gemini Interactions API.
- Requests use `store: false` and a limited eight-turn history.
- The Gemini key stays in the FastAPI service.
- Added `POST /v1/prep-bot/chat`.
- `/v1/capabilities` now reports Prep-bot configuration status.
- Added safe missing-key/network/empty-response failures.
- Added CORS configuration for local frontend development and hosted-origin setup.

### Original Prep-Panel frontend

The screenshots were treated as feature references only. No Parhlai layout, visual system, branding, or business logic was copied.

Implemented an original Prepify terminal-ledger interface with:

- a left Prep-Panel rail;
- responsive mobile navigation;
- Dashboard;
- Analytics;
- Prep-bot;
- Resources;
- Exam workspace.

Dashboard now shows:

- evidenced-score readout;
- true empty state before attempts;
- topic signals;
- grader readiness;
- next-action routing.

Analytics now covers:

- evidenced marks;
- MCQ accuracy;
- code test-case pass rate;
- written award-condition hit rate;
- attempt completion;
- topics and attempt history.

Gated/ungraded responses are excluded from denominators. Attempt summaries are device-local and capped at 50 records.

Prep-bot UI now provides:

- starter prompts;
- multi-turn chat;
- server-side API calls;
- loading/error states;
- a clear non-official-grading notice.

Resources now provides:

- source/type labeling;
- search and filters;
- official Cambridge links;
- free third-party course/reference links;
- safe external-link behavior.

The exam workspace retains three distinct input surfaces. Strict mode hides the Prep-Panel and keeps the no-pause timer behavior.

### Documentation

- Replaced the README with a no-prior-knowledge installation and operation guide.
- Replaced `pipeline.md` with the QP/MS end-to-end contract.
- Updated this progress record.
- Updated `suggestions.md` with prioritized technical/product recommendations.
- Added current Gemini official-documentation links and clear copyright/source-acquisition boundaries.

## Previously completed and retained

### MVP1 foundation

- PDF extraction with embedded-text and vision-OCR paths.
- Pseudocode-sensitive review queue.
- PostgreSQL source-of-truth records.
- Qdrant embeddings and reranking.
- Topic taxonomy.
- Supplementary MCQ generation with source chunk IDs and paraphrase enforcement.
- Non-scoring question explanation with private evidence citations.

### MVP2 Phase 1

- Paper 4 manifest loading.
- Docker-isolated execution for Python, Java, and Visual Basic profiles.
- Resource/test-case contracts from the earlier implementation.
- Per-test-case feedback.
- Provisional/certified distinction.
- Held-out validation runner and stored validation status.
- Fail-closed validation behavior when manifests or sandbox profiles change.

Although Phase 1 still contains earlier resource-file models, new QP/MS-only assembly does not select questions needing inserts/data files.

### MVP3 exam frontend

- Deterministic assembly API.
- Strict timer.
- Question index.
- CodeMirror editor.
- Structured subpart inputs.
- Inline review mode.
- Visually distinct pseudocode transpilation/logic states for the future grader contract.
- Demo-only paths clearly labeled as demo data.

## Verification completed

Backend result:

```text
33 passed
```

Coverage includes:

- QP/MS filename and linkage contracts;
- ER/IN filename rejection;
- review behavior;
- Paper 4 manifest/sandbox/grading logic;
- real-only assembly sources;
- multi-series selection;
- private mark-scheme evidence redaction;
- insert-dependent pool rejection;
- Prep-bot API and stateless request payload.

Frontend result:

```text
npm run lint: passed
npm test: 3 passed
production Vinext build: passed
```

The production build emits a non-blocking large-chunk advisory because CodeMirror and language support are bundled into the main client chunk.

## Gated or incomplete

### MVP2 Phase 1 certification

Paper 4 execution code exists, but certification requires the configured minimum held-out submissions and exact-mark validation under the same sandbox profile used in production.

### MVP2 Phase 2

Not implemented:

- 9618 pseudocode parser/transpiler;
- syntax diagnostic taxonomy;
- execution harness for transpiled programs;
- held-out validation.

The frontend remains gated and does not score pseudocode.

### MVP2 Phase 3

Not implemented:

- structured mark-scheme award-condition representation;
- evidence matching;
- per-condition decision engine;
- human-graded validation dataset.

The frontend preserves subparts but does not score written answers.

### Account analytics

Current analytics use browser storage. There is no authentication, cross-device synchronization, server-side history, deletion UI, or cohort reporting.

### Production backend

The frontend can be hosted independently, but useful real operation requires a deployed FastAPI API plus PostgreSQL/Qdrant, configured secrets, and exact CORS origins.

### Legal/content operations

No automated source downloader is implemented. Authorization, access control, retention, and redistribution policy require organizational decisions and legal review.

## Known migration note

The SQLAlchemy models changed:

- removed `PaperSpecification.syllabus_document_id`;
- added `PaperSpecification.minimum_source_series`;
- added `PaperSpecification.source_document_ids`;
- added `ExamAssembly.source_series`.

Development databases created with the previous model must be reset or migrated. Production must use a real migration tool before deployment.

## Recommended next milestone

Prepare a small, legally authorized pilot corpus:

1. two or more series for one paper;
2. verified question numbers, marks, topics, and AO allocations;
3. reviewed question/mark-scheme block matches;
4. reviewed presentation manifest;
5. one assembly run inspected question-by-question against the source PDFs.

This pilot will validate the most important premise—accurate QP/MS pairing and multi-series assembly—before effort expands into account analytics or additional graders.
