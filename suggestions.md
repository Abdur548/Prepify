# Prepify suggestions and next decisions

These recommendations are ordered by integrity and delivery value, not by visual novelty.

## P0 — settle before a real pilot

### 1. Establish lawful content operations

Document where every paper came from, who may access it, how long it may be stored, and what happens when access is revoked. Keep the source library private. Obtain legal review before serving copyrighted exam text beyond a controlled pilot.

Why this is integral: technical accuracy does not create redistribution permission.

### 2. Build a QP/MS pair audit screen

Create an administrator view showing, for every question:

- QP document, series, paper code, question number, page, and text preview;
- linked MS document and matching point previews;
- review status;
- marks/topic/AO metadata;
- delivery authorization;
- reasons the question is ineligible.

Allow a reviewer to correct a false match explicitly. This will be more valuable than adding another student feature because all downstream grading depends on the pair being right.

### 3. Introduce database migrations

Replace `create_all`-only evolution with Alembic before any persistent environment. The current QP/MS redesign changes paper-specification and assembly columns. A repeatable migration plus backup/rollback procedure is mandatory before real data accumulates.

### 4. Validate one paper end to end

Choose one paper with at least two authorized historical series. Manually verify every selected question and its marking evidence after assembly. Measure:

- correct question-number segmentation;
- correct QP/MS attachment;
- marks accuracy;
- topic/AO accuracy;
- series diversity;
- duplicate or near-duplicate selection;
- public/private field redaction.

Do this before broad ingestion.

### 5. Add authentication and authorization

At minimum, separate:

- student;
- reviewer/teacher;
- content administrator.

Review approval, manifest loading, source previews, and mark-scheme evidence must not be available to ordinary students.

## P1 — highest product value after the pilot

### 6. Move analytics to server-side attempt records

Current browser storage is useful for a demo but fragile. Add authenticated attempt and response tables with:

- assembly/version ID;
- start/finish timestamps;
- answer completion;
- grader result and certification state;
- topic/AO labels;
- explicit null for ungraded work;
- deletion/export support.

Keep raw student answers under a defined retention policy. Do not log them in ordinary application telemetry.

### 7. Create an analytics evidence model

Avoid a single percentage as the canonical fact. Store observations separately:

- MCQ selection outcome;
- execution test-case outcome;
- pseudocode transpilation outcome;
- pseudocode logic-test outcome;
- written award-condition outcome;
- ungraded/gated status.

The UI can aggregate these, but the database should preserve why each number exists.

### 8. Add question exposure controls

Real-question assembly can repeatedly reveal a limited pool. Track exposure and allow administrators to define:

- cooldown after use;
- maximum use count;
- retired questions;
- practice-only questions;
- secure mock pools.

This is selection hygiene, not adaptive learning.

### 9. Add duplicate and overlap detection

Across years, questions may be very similar. Use embeddings plus reviewer confirmation to form duplicate groups. The assembler should avoid selecting two near-duplicates in one paper unless the specification explicitly permits it.

### 10. Add structured source provenance to resources

For each learning-resource link, store:

- owner/publisher;
- link type;
- last-checked date;
- syllabus topics;
- third-party disclaimer;
- age/access restrictions where relevant.

Run a scheduled link check, but keep human approval for additions. Do not embed arbitrary YouTube pages in the app without reviewing privacy/cookie behavior.

## P1 — grading roadmap

### 11. Finish Paper 4 validation before calling it certified

Use a teacher-scored held-out dataset covering:

- correct solutions in all supported languages;
- partially correct solutions;
- timeouts and infinite loops;
- malformed output;
- empty/edge inputs;
- file access attempts;
- memory/process abuse attempts.

Pin sandbox image digests. Any test manifest or runtime-profile change should invalidate certification and require rerunning the dataset.

### 12. Design Paper 2 as a real language implementation

Do not treat Cambridge pseudocode as informal Python. Define:

- grammar and AST;
- source locations;
- type rules;
- array bounds/indexing;
- procedure/function semantics;
- file operations in the supported subset;
- deterministic diagnostics;
- transpiled source mapping.

Then show two separate student states:

- transpilation failure: the submitted language could not be interpreted;
- logic failure: transpilation succeeded but tests failed.

### 13. Represent written mark schemes structurally

Phase 3 needs data more precise than raw mark-scheme text. Define conditions with:

- condition ID and subpart;
- marks;
- accepted concepts/paraphrases;
- required links or comparisons;
- exclusions and maximums;
- dependency/alternative groups;
- source mark-scheme block ID;
- reviewer/version.

Return hit/miss/uncertain per condition with evidence and a reason. Route uncertain cases to human review rather than forcing a mark.

### 14. Prevent mark-scheme leakage

Students may ask Prep-bot to reveal answers during a live mock. The bot currently has no mark-scheme retrieval, which is a good boundary. Keep it disconnected from private mark-scheme content during strict exam mode, and consider disabling the Prep-bot route entirely while an exam is active in an authenticated session.

## P2 — Prep-bot improvements

### 15. Ground navigation separately from tutoring

Give Prep-bot a small, versioned product-help knowledge base for “where do I find…” questions. Keep this distinct from academic tutoring and from private marking evidence.

### 16. Add safety and quality evaluation

Before wider release, evaluate a fixed set of prompts for:

- factual 9618 errors;
- invented exam rules;
- answer/mark-scheme leakage;
- overly direct homework completion;
- failure to admit uncertainty;
- prompt injection attempts;
- attempts to extract the system instruction or API secrets.

Store evaluation outcomes, not student chat content, unless users have consented to a defined retention policy.

### 17. Make model choice configurable and observable

The current default is `gemini-3.5-flash`. Record model name, request latency, token use where available, and safe error category. Do not record the API key or full student message in general logs.

### 18. Add rate and cost controls

Introduce per-user quotas, maximum message length, concurrency limits, and upstream timeouts. Cache only content that is safe and useful to cache; do not accidentally merge one student’s conversation into another’s.

## P2 — frontend and usability

### 19. Code-split the editor

The production build warns about a large client chunk. Dynamically import CodeMirror and its language packages only when a code/pseudocode question is opened. Dashboard, Analytics, Prep-bot, and Resources should not pay the editor bundle cost.

### 20. Add accessibility verification

Test keyboard-only navigation, visible focus, screen-reader labels, zoom, reduced motion, and color contrast. Pay special attention to:

- mobile Prep-Panel drawer;
- exam timer urgency;
- MCQ selection/correction state;
- CodeMirror accessibility;
- test-case and condition feedback;
- chat live-region behavior.

### 21. Add resumable practice separately from strict mode

Keep strict mocks no-pause. If users need interruptions, add a separate practice mode with explicit save/resume semantics. Do not weaken strict mode invisibly.

### 22. Preserve original design ownership

Continue using the reference screenshots only as product-category inspiration. Maintain Prepify’s terminal-ledger design tokens, information hierarchy, labels, and behaviors. Perform originality review before public launch.

## P2 — observability and operations

### 23. Define privacy-safe telemetry

Measure:

- ingestion counts and failures;
- review-queue age;
- unmatched QP/MS counts;
- assembly conflicts;
- grader error categories;
- Gemini latency/error categories;
- frontend route usage.

Exclude raw PDFs, mark-scheme text, code submissions, written answers, chat messages, and secrets from normal logs.

### 24. Back up both metadata and source evidence

PostgreSQL, the authorized source store, and Qdrant have different recovery roles. Back up PostgreSQL and the source files first; Qdrant can be rebuilt from reviewed blocks if necessary. Test restoration rather than assuming it works.

### 25. Add content/version immutability

An assembly should point to exact reviewed versions. If a question presentation, topic tag, AO allocation, or mark-scheme condition changes, create a new version instead of rewriting the evidence behind a completed attempt.

## Deferred on purpose

Do not prioritize these until the core evidence pipeline is proven:

- adaptive difficulty;
- leaderboards;
- social/gamification features;
- a large generated-question marketplace;
- examiner-report ingestion;
- insert/data-file ingestion;
- analytics dashboards for teachers/cohorts;
- automated high-stakes grading claims.

## Recommended execution order

1. Legal/content-source policy.
2. Alembic migration and QP/MS audit screen.
3. One-paper multi-series pilot with manual evidence verification.
4. Paper 4 held-out validation.
5. Authentication and server-side attempt analytics.
6. Paper 2 language implementation.
7. Paper 1/3 structured condition engine.
8. Prep-bot evaluation and cost controls.
9. Accessibility and performance hardening.
10. Reconsider deferred source types only with a clear dependency model.
