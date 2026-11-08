# Loan Underwriting Investigation Assistant
## Project handoff, current state, and future development plan

> **Purpose of this document:** Preserve the project's context and implementation plan so development can resume later, even in a new ChatGPT conversation or after this chat history is deleted.
>
> **Project status:** Backend MVP in development. Core application and document workflows exist. Payslip and bank-statement extraction have both been exercised successfully with synthetic PDFs. Cross-document verification and the underwriting workflow are not implemented yet.

---

## 1. Product summary

**Project name:** `loan-underwriting`  
**Product name:** AI Loan Underwriting Investigation Assistant

The product is intended for loan officers and underwriting analysts at lenders such as NBFCs, fintech lenders, and eventually banks.

A loan applicant submits documents such as:

- Payslips, to support employment and salary information.
- Bank statements, to show salary credits, other credits, expenses, transfers, and account balances.
- Existing loan statements, to show current loan obligations and repayment information.

The application helps an underwriting analyst review these documents. It extracts structured financial information, checks consistency across documents, calculates financial metrics deterministically, identifies missing or conflicting information, and prepares an evidence-backed investigation report for a human reviewer.

**Important product boundary:** This is an underwriting investigation assistant, not an autonomous loan approval system. The system can surface evidence, calculations, inconsistencies, and recommendations for review. A qualified lender/employee retains responsibility for the lending decision.

### Intended user journey

1. A loan officer creates a loan application.
2. The loan officer uploads the applicant's supporting PDF documents.
3. The application displays which document types have been received and which are missing.
4. The system extracts text from supported PDFs.
5. AI extracts structured information from each document.
6. The system saves extraction results so the same document does not need to be sent to the LLM repeatedly.
7. Deterministic Python services compare the extracted information and calculate financial metrics.
8. The system identifies discrepancies or missing evidence.
9. The loan officer can request additional documents or clarification.
10. The system produces an investigation report with evidence and findings.
11. A human reviewer examines the report and records the review outcome.

---

## 2. Product scope and positioning

The intended positioning is:

> **An AI investigation layer for lending institutions that turns financial documents into explainable, evidence-backed underwriting findings.**

The product is not intended to replace a lender's Loan Origination System (LOS), core banking platform, credit bureau, or final credit decision process. The more realistic initial product is a focused workflow that can complement existing lending systems.

### Initial customer hypothesis

Start by validating the workflow with people working in:

- Small and mid-sized NBFCs.
- Digital lending companies.
- Loan processing and underwriting service providers.
- Potentially lenders focused on personal loans or MSME loans.

Do not assume market demand based only on the quality of the prototype. Interview underwriting professionals and validate the actual workflow, pain points, integration requirements, purchasing process, and willingness to pay.

### Competitor context

RevRag was discussed during product research. Its broad focus is assistance during the loan application/customer journey, while this product is intended to focus on the lender-side investigation of submitted financial documents. This is a positioning distinction, not proof that no competitor offers similar underwriting capabilities. Perfios, FinBox, and other financial data/underwriting vendors are relevant competitors to research further before making market claims.

---

## 3. Technology decisions

The current stack and conventions are:

| Area | Technology | Purpose |
|---|---|---|
| Backend API | FastAPI | HTTP endpoints and request handling |
| Python environment/package management | `uv` | Project setup, dependencies, commands, server execution |
| Database | SQLite initially | Local development database |
| ORM | SQLAlchemy | Database models, sessions, queries |
| Migrations | Alembic | Version and apply database schema changes |
| Validation | Pydantic | API schemas and structured LLM output validation |
| Configuration | Pydantic Settings + `.env` | Environment-based configuration |
| PDF text extraction | PyMuPDF | Extract selectable text from PDF pages |
| LLM integration | LangChain | Provider-neutral model integration and structured output |
| Initial LLM provider | Gemini via `langchain-google-genai` | Payslip and bank-statement extraction |
| Agent orchestration | LangGraph | Planned multi-step underwriting workflow; not yet implemented |
| Frontend | Not started | To be built after backend workflow is usable |

### Project naming and structure decisions

These decisions are final unless deliberately changed later:

- Root project directory/distribution name: `loan-underwriting`.
- Python import package: `app`.
- Python source directory: `app/` directly in the project root.
- **Do not introduce a `src/` directory.**
- Import paths use `app`, e.g. `from app.db.database import get_db`.
- Start the API with `uv run`, not a manually activated environment.
- Use `uv add` / `uv add --dev` to add dependencies.
- Do not use `pip install` or direct system Python commands for project operations.

### Expected current directory layout

The exact tree may have small differences as the project has evolved. Check the actual repository before moving or recreating files.

```text
loan-underwriting/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── applications.py
│   │   └── documents.py
│   ├── ai/
│   │   ├── __init__.py
│   │   └── model.py
│   ├── db/
│   │   ├── __init__.py
│   │   └── database.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── application.py
│   │   ├── document.py
│   │   └── extraction.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── application.py
│   │   ├── document.py
│   │   ├── financial.py
│   │   └── bank_statement.py
│   └── services/
│       ├── __init__.py
│       ├── document_service.py
│       ├── pdf_extraction.py
│       ├── payslip_extraction.py
│       └── bank_statement_extraction.py
├── migrations/
│   ├── env.py
│   └── versions/
├── data/
│   └── uploads/
├── .env                 # local secrets; never commit
├── .env.example         # safe placeholders; commit this
├── .gitignore
├── alembic.ini
├── pyproject.toml
├── uv.lock
├── README.md
└── SETUP.md              # if present in the repository
```

Some folders or modules listed above may not have been created yet or may have a slightly different name. Inspect the live repository before implementing a future task.

---

## 4. Current project setup and commands

All Python project commands should use `uv`.

### Install dependencies after cloning

```bash
uv sync
```

This installs the dependencies recorded in `pyproject.toml` and `uv.lock` into the project's environment.

### Configure environment

Create `.env` in the repository root. Never commit the real `.env` file.

Example shape (use a valid model ID and the provider identifier supported by the installed LangChain integration):

```env
DATABASE_URL=sqlite:///./data/loan_underwriting.db
UPLOAD_DIR=data/uploads
MAX_UPLOAD_SIZE_MB=10

LLM_PROVIDER=google_genai
LLM_MODEL=gemini-3.1-flash-lite
LLM_API_KEY=replace_with_a_new_secret_key
```

Notes:

- The exact setting names must match `app/config.py`.
- The exact provider string must match the value expected by the project's `init_chat_model` call. The currently working implementation used the Google Gemini LangChain integration. Verify the actual `app/ai/model.py` and `.env` rather than blindly changing a working value.
- `LLM_MODEL` is configurable. Do not hardcode it in services.
- A Gemini API key was accidentally shared in the previous chat. Treat that key as compromised if it has not already been revoked. Generate a replacement and put it only in `.env` or the secret manager used later.
- Never paste API keys into code, README files, screenshots, Git commits, logs, or public issue trackers.

### Run the API

From the project root:

```bash
uv run uvicorn app.main:app --reload
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

Health endpoint, if the current `main.py` retains it:

```text
http://127.0.0.1:8000/health
```

### Alembic commands

Generate a migration after changing SQLAlchemy model structure:

```bash
uv run alembic revision --autogenerate -m "describe the schema change"
```

Inspect the generated Python migration file before applying it. Then apply:

```bash
uv run alembic upgrade head
```

Do not run `alembic init` again if the `migrations/` directory and `alembic.ini` already exist.

### Database concepts to remember

- **SQLAlchemy model:** Python class describing a database table and its columns.
- **Pydantic schema:** Defines and validates API input/output or structured LLM output.
- **Database schema:** The actual tables and columns inside SQLite/PostgreSQL.
- **Alembic migration:** A versioned instruction that changes the actual database structure.
- **Engine:** SQLAlchemy's database connection manager.
- **Session factory (`SessionLocal`):** Creates individual SQLAlchemy sessions.
- **Session:** A unit of work used to query and change database records. It is not the engine or the database itself.
- **`get_db()`:** FastAPI dependency that creates a session for a request and closes it afterwards.

Generating an Alembic migration and applying it are two different actions: `revision --autogenerate` creates the migration file; `upgrade head` executes it against the database.

---

## 5. What has been implemented

The following reflects the work completed and reported during the previous development session. Verify against the current repository before assuming every line is still present.

### 5.1 FastAPI foundation

- FastAPI application entry point exists at `app/main.py`.
- The application has been run with Uvicorn through `uv run`.
- Swagger UI has been used to exercise endpoints.

### 5.2 Database foundation

- SQLite configured using a `DATABASE_URL` environment variable.
- SQLAlchemy engine and session factory implemented in `app/db/database.py`.
- A `Base` declarative class is used for SQLAlchemy models.
- FastAPI database dependency `get_db()` creates and closes sessions.
- Alembic configured for migrations.
- PostgreSQL migration is intended to require a database URL and driver change, not a rewrite of normal CRUD/model code. This has not yet been validated against a real PostgreSQL instance.

### 5.3 Loan application CRUD

A `LoanApplication` model exists with fields including:

- `id`
- `applicant_name`
- `requested_loan_amount`
- `loan_purpose`
- `status`
- `created_at`

Implemented API operations:

- Create application (`POST`).
- List applications (`GET`).
- Get one application by ID (`GET`).
- Partially update an application (`PATCH`).
- Delete an application (`DELETE`).

The exact route prefix used during development was `/api/v1/applications`.

### 5.4 Document upload and management

A `Document` model exists with information including:

- `id`
- `application_id` foreign key
- `document_type`
- `original_filename`
- `storage_path`
- `file_size`
- `created_at`

Implemented/reported working capabilities:

- Upload PDF against an existing application.
- Validate file extension, PDF signature, and configured file-size limit.
- Generate a random stored filename rather than trusting the original filename as the storage path.
- Save the PDF under `data/uploads/<application_id>/`.
- Save document metadata in SQLite.
- List documents for an application.
- Return a document checklist for the application.

Supported document types used in the API:

- `payslip`
- `bank_statement`
- `existing_loan_statement`

The checklist currently checks whether at least one file of a required type has been uploaded. It does **not** verify whether a payslip actually covers three months, whether a bank statement covers six months, or whether the document content is genuine.

### 5.5 PDF text extraction

- `app/services/pdf_extraction.py` uses PyMuPDF to read text from PDF pages.
- It returns page count, extracted text, and whether extractable text exists.
- This handles text-based PDFs.
- Scanned/image-only PDFs need OCR and are not supported by the current extraction path.

### 5.6 LLM/model integration

- `app/ai/model.py` contains a reusable model factory using LangChain's `init_chat_model`.
- The service should read provider, model, and API key from configuration.
- Gemini has been used successfully for extraction.
- The intention is to keep model-specific initialization inside the factory, not scattered through services or API routes.

### 5.7 Payslip extraction — tested successfully

- `app/schemas/financial.py` defines a Pydantic extraction structure.
- `app/services/payslip_extraction.py` sends extracted PDF text to the configured chat model using structured output.
- The API endpoint used during development:

```http
POST /api/v1/applications/{application_id}/documents/{document_id}/analyze-payslip
```

- The endpoint checks that the document exists and is a payslip, extracts PDF text, calls the LLM, validates structured output, and returns the result.
- A `DocumentExtraction` model/table was subsequently added to store extracted results as JSON.
- The payslip endpoint was updated to check for an existing extraction and return the stored result rather than calling the model again.

A successful synthetic payslip extraction returned values such as:

- Employee: Alex Morgan
- Employer: APEX TECHNOLOGIES INDIA PVT. LTD.
- Period: October 2026
- Gross salary: ₹150,000
- Total deductions: ₹29,200
- Net salary: ₹120,800

### 5.8 Bank statement extraction — tested successfully

- A bank-statement Pydantic schema was added.
- A bank-statement extraction service uses the same model factory and structured output approach.
- An endpoint was added:

```http
POST /api/v1/applications/{application_id}/documents/{document_id}/analyze-bank-statement
```

- It checks application/document association and document type, extracts text, calls the LLM, validates output, and stores/reuses an extraction record.
- A synthetic bank statement was generated for testing and uploaded.
- The extraction successfully returned account-holder name, bank name, last four account digits, statement period, opening/closing balance, and transaction rows with date, description, debit, credit, and balance.

The tested synthetic statement contained:

- Account holder: Alex Morgan
- Bank: Sample National Bank (fictional)
- Statement period: 1–31 October 2026
- Opening balance: ₹80,000
- Salary credit: ₹120,800
- Existing loan EMI: ₹18,500
- Closing balance: ₹115,877

The transaction arithmetic reconciled for the sample:

```text
Opening balance + total credits - total debits = closing balance
₹80,000 + ₹136,275 - ₹100,398 = ₹115,877
```

The salary credit amount and employer description aligned with the synthetic payslip. This is only a successful test on constructed sample data, not proof of general extraction accuracy.

### 5.9 Extraction persistence

A `DocumentExtraction` model/table was added. Its purpose is to associate structured extracted JSON with a document and extraction type, for example:

- `payslip`
- `bank_statement`
- Future: `existing_loan_statement`

A uniqueness constraint was intended on `(document_id, extraction_type)` so the same extraction type is not stored twice for the same document. Verify the actual model and migration in the repository.

---

## 6. Current state: what is NOT implemented yet

The project is not yet a full underwriting agent. In particular, these capabilities remain future work:

- Deterministic cross-document verification.
- Transaction categorization/classification.
- Existing loan statement extraction.
- Financial calculations and repayment capacity metrics.
- Additional document request workflow.
- LangGraph orchestration.
- Final underwriting investigation report.
- Complete application review/status lifecycle.
- Authentication, authorization, and multi-tenant data isolation.
- Production-grade document storage/security.
- Comprehensive automated tests and extraction evaluation.
- Frontend.
- Real LOS/bank/NBFC integrations.

Do not describe these capabilities as implemented until they actually exist and have been tested.

---

## 7. Recommended future implementation plan

Implement the following in order. Keep each feature small and test it before moving to the next one.

### Step 1 — Cross-document financial verification

**Goal:** Compare saved payslip and bank-statement extractions belonging to the same loan application.

Create a deterministic service, suggested file:

```text
app/services/financial_verification.py
```

Add a Pydantic schema for a finding with fields along these lines:

- `check_name`
- `status`: `matched`, `mismatch`, or `needs_review`
- `expected_value`
- `actual_value`
- `difference`
- `explanation`
- `supporting_evidence`

Add an endpoint, for example:

```http
POST /api/v1/applications/{application_id}/verify-finances
```

Checks to implement:

1. Compare payslip net salary with candidate salary credits in the bank statement.
2. Compare applicant/employee name with bank account-holder name, allowing for safe normalization and flagging ambiguity.
3. Compare employer name with salary credit description as a heuristic, not as absolute proof.
4. Verify bank statement closing balance against opening balance plus credits minus debits.
5. Verify running balance from one transaction to the next wherever the statement data supports it.
6. Return `needs_review` when the system cannot confidently identify the relevant salary transaction or data is incomplete.

Important design decisions:

- Use Python `Decimal` for all financial arithmetic; never use binary floats for currency calculations.
- Do not use an LLM for arithmetic or deterministic comparisons.
- Do not assume the largest credit is salary.
- Identify possible salary transactions using description, employer information, pay period, amount, and other context; preserve the candidate evidence and flag ambiguity.
- One bank statement month is not enough to prove stable monthly income. Report the period and data limitations.
- This feature should report findings, not make loan approval/rejection decisions.

### Step 2 — Bank transaction classification

**Goal:** Classify bank statement transactions into useful categories.

Initial categories:

- Salary/income.
- Reimbursement.
- Interest/other income.
- Existing loan EMI.
- Rent.
- Utilities.
- Groceries/retail.
- Healthcare.
- Insurance.
- Cash withdrawal.
- Internal account transfer.
- Refund/reversal.
- Other/uncertain.

Start with explainable deterministic rules using transaction description, debit/credit direction, recurrence, and available context. Use `uncertain` or `needs_review` rather than forcing a category. An LLM may assist with ambiguous descriptions later, but the system must preserve the original transaction and record the basis for each classification.

Important: internal transfers should not automatically be counted as income or expenses; refunds and reversals should be treated carefully; a debit should not automatically be classified as a loan EMI.

### Step 3 — Existing loan statement extraction

**Goal:** Extract information about a borrower's current liabilities.

Create a schema, service, and API endpoint following the same patterns as payslip and bank statement extraction.

Potential fields:

- Lender name.
- Loan account last four digits only, if present.
- Loan type.
- Original principal/loan amount.
- Current outstanding principal.
- EMI amount.
- Interest rate, if stated.
- Tenure and remaining instalments, if stated.
- Due date.
- Repayment history or overdue amount, if the statement contains it.
- Statement period and evidence.

Do not infer a missing interest rate, EMI, balance, or repayment history. Retain evidence. Store the extraction through the existing `DocumentExtraction` model using a distinct extraction type.

### Step 4 — Financial calculation engine

**Goal:** Calculate financial metrics using Python from persisted, validated extraction records and categorized transactions.

Possible outputs:

- Verified salary credit by month.
- Average monthly income across the actual available period.
- Other recurring income, kept separate from salary.
- Monthly expenses by category.
- Existing EMI obligations.
- Total fixed monthly obligations.
- Estimated disposable income.
- FOIR (Fixed Obligation to Income Ratio), with the formula and included obligations clearly shown.
- Debt-to-income ratio where the necessary debt/income definitions are available.
- Proposed EMI scenarios, only when the assumptions (loan amount, interest rate, tenure) are explicit.

Rules:

- Use `Decimal` for money.
- Record the calculation inputs, formula, period, and assumptions.
- Handle missing months and partial statements explicitly.
- Do not annualize a single month as though it proves stable income.
- Clearly distinguish actual observed values from estimates.
- Avoid using a universal approval threshold; lender policies vary.
- Do not ask the LLM to perform financial calculations.

### Step 5 — Additional document request workflow

**Goal:** Let the system identify missing evidence and allow a loan officer to request it.

Example:

- Payslip reports net salary of ₹60,000.
- Bank statement shows a salary credit of ₹48,000.
- The system flags the discrepancy and suggests clarification or a supporting salary revision letter.
- The loan officer reviews and sends the request.
- The applicant/employee uploads the new document.
- The application is reprocessed and the previous finding is updated or resolved with an audit trail.

Keep human control over issuing requests. Do not let an LLM autonomously send requests externally without authorization.

Potential future entities/tables may be required for document requests and review history. Introduce them only when implementing the workflow and create Alembic migrations for genuine schema changes.

### Step 6 — LangGraph underwriting workflow

**Goal:** Orchestrate the individual capabilities into a stateful investigation process.

Possible high-level graph:

```text
Loan application
    -> document/checklist validation
    -> extract available documents
    -> validate extraction completeness
    -> classify transactions
    -> calculate financial metrics
    -> cross-document verification
    -> missing information decision
         -> request human-approved additional documents
         -> wait for upload / resume investigation
    -> generate investigation report
    -> human review
```

Use LangGraph for orchestration, conditional routing, state/checkpointing, resumability, and human-in-the-loop interruption. Do not add agents simply for the sake of calling the architecture multi-agent. Separate tool/service responsibilities and use a simple graph unless multiple specialized agents provide a real benefit.

Use a persistent checkpointer appropriate to the deployment. Do not rely on in-memory state for a workflow that must survive process restarts.

### Step 7 — Underwriting investigation report

**Goal:** Produce a readable, auditable report for the loan officer.

Suggested report sections:

1. Application summary.
2. Documents received and missing.
3. Extracted applicant/employment details.
4. Verified income and period observed.
5. Existing liabilities and EMI obligations.
6. Expense and cash-flow summary.
7. Cross-document checks and discrepancies.
8. Missing or ambiguous information.
9. Supporting document evidence for each finding.
10. Calculation details and assumptions.
11. Suggested follow-up questions.
12. Human reviewer notes and outcome.

Report findings should distinguish `matched`, `mismatch`, `needs_review`, and `not_enough_data`. Never convert the report into an autonomous approve/reject decision.

### Step 8 — Application lifecycle/status management

Introduce explicit, validated application statuses as the workflow becomes real. Potential statuses:

```text
documents_pending
ready_for_analysis
analysis_in_progress
additional_information_required
analysis_completed
under_review
review_completed
```

Define which events can change a status. Avoid arbitrary status updates from clients. Preserve status history/audit records as needed.

### Step 9 — Evaluation and testing

There are no comprehensive automated tests yet. Add tests when the core behavior is more stable.

Create synthetic test cases for:

1. Payslip net salary equals bank salary credit.
2. Payslip salary differs from bank salary credit.
3. Multiple possible salary credits.
4. Reimbursement or interest incorrectly resembling salary.
5. Existing EMI identified from bank transactions.
6. Internal transfer not counted as income/expense.
7. Refund/reversal handling.
8. Bank statement closing balance mismatch.
9. Running balance mismatch in an individual transaction.
10. Missing statement period or incomplete transaction rows.
11. Scanned PDF with no extractable text.
12. Corrupted or malformed PDF.
13. LLM timeout/provider error.
14. Repeated request returns cached extraction without another LLM call.
15. Application/document ID mismatch.

Evaluate extraction quality against known expected values. Track field-level accuracy, transaction completeness, false classifications, reconciliation accuracy, model cost, latency, and failure rate. A valid Pydantic response does not guarantee that the extracted financial values are factually correct.

### Step 10 — Security and production readiness

Before real borrower data or any lender pilot, address at least:

- Employee authentication.
- Role-based access control.
- Strict application/customer data authorization.
- Multi-tenant isolation if serving multiple lenders.
- Encryption in transit and at rest.
- Secure document storage; avoid exposing local storage paths.
- Malware scanning and PDF safety limits.
- File size, page count, and processing resource limits.
- Secret management; no API keys in Git.
- Redacted logs and traces; do not log full bank statements, account numbers, PAN, or sensitive prompts.
- Retention and deletion policies.
- Audit trail for document access, extractions, changes, requests, and human decisions.
- Consent and appropriate legal/regulatory review for the deployment model.
- Provider contract and data-retention review before sending any real financial document content to an external model API.
- Human review of model-generated findings.

For the current prototype, use synthetic data only. The current local filesystem upload implementation is not production-grade secure document storage.

### Step 11 — Frontend

Start frontend development after the backend can complete one reliable application investigation and return a report.

Suggested screens:

1. Application dashboard.
2. Create application form.
3. Application detail page.
4. Fixed document upload cards (payslip, bank statement, existing loan statement) with status.
5. Document checklist.
6. AI investigation progress and findings.
7. Additional document request panel.
8. Financial metrics and discrepancy view.
9. Final report with supporting evidence.
10. Human review and notes.

The UI should use conventional forms and upload controls for the standard workflow. AI should request additional documents only when findings indicate they are needed. Do not make the entire product a chatbot.

---

## 8. Suggested next coding task when resuming

**The immediate next feature is Step 1: deterministic cross-document financial verification.**

At the end of the previous session, the synthetic payslip and bank statement had both been extracted successfully. No cross-document comparison service had yet been implemented.

Start by inspecting the actual repository and confirming:

- The current structure and exact filenames.
- The `DocumentExtraction` model and uniqueness constraint.
- How payslip and bank statement JSON are serialized and stored.
- The actual extraction type strings used (`payslip` and `bank_statement`).
- How document records are linked to an application.
- The current response schemas and API router registration.

Then implement a small deterministic service that reads the saved extraction results and returns structured verification findings. Add an endpoint such as:

```http
POST /api/v1/applications/{application_id}/verify-finances
```

Use the synthetic sample as the first fixture:

- Payslip net salary: ₹120,800.
- Bank statement salary credit: ₹120,800.
- Employer on payslip: APEX TECHNOLOGIES INDIA PVT. LTD.
- Salary transaction description contains the same employer name.
- Bank opening balance: ₹80,000.
- Bank closing balance: ₹115,877.
- Credits: ₹136,275.
- Debits: ₹100,398.

Expected findings for this synthetic sample:

- Net salary and identified salary credit amount: matched.
- Employer/payee description: likely matched based on text evidence, but use a transparent normalization/matching method and do not treat this alone as proof of employment.
- Statement arithmetic: matched.
- No final credit decision.

Do not assume that sample IDs `application_id=1`, `payslip document_id=1`, or `bank statement document_id=2` will be the same in a new database. Query records by application and extraction type.

---

## 9. Development preferences and collaboration rules

These preferences are important for future coding sessions:

1. Work incrementally, one feature at a time.
2. Explain briefly what a file or code change is responsible for. The developer wants to understand the implementation, not just paste code.
3. Avoid dumping many files or a large architecture redesign in one response.
4. Do not introduce unnecessary abstractions, folders, agents, or dependencies.
5. Preserve the project naming and structure: root `loan-underwriting`, Python package `app/` directly in the root, no `src/` directory.
6. Use `uv` for all Python dependency management, Python execution, migrations, and server execution.
7. Use commands such as `uv add`, `uv sync`, `uv run python`, `uv run alembic`, and `uv run uvicorn`.
8. Do not use `pip install` or ask the developer to manually activate `.venv`.
9. Prefer prompts for the user's coding agent when explicitly requested. Otherwise give a focused implementation step.
10. Do not assume a feature works because code was written. Ask for or provide a concrete Swagger/manual verification step.
11. Do not change working features without a reason.
12. Keep financial arithmetic deterministic in Python using `Decimal`; use LLMs for document interpretation and language-based synthesis, not arithmetic.
13. Do not claim the project is production-ready or compliant. It is currently a prototype.

---

## 10. How to resume in a new chat

When starting a new ChatGPT conversation, upload this handoff file and (ideally) the current repository ZIP or relevant source files. Then use this instruction:

> We are continuing the `loan-underwriting` project. Read the attached handoff document first, then inspect the current source files before suggesting code. Keep the existing architecture and naming: FastAPI, SQLAlchemy, SQLite, Alembic, Pydantic, LangChain, Gemini through the model factory, PyMuPDF, and `uv`. The Python package is `app/` directly in the repository root; there is no `src/` directory. Work one small step at a time and explain each change. The next task is deterministic cross-document financial verification using the already persisted payslip and bank-statement extraction results. Do not rebuild the project from scratch.

---

## 11. Definition of the first complete MVP

The first meaningful end-to-end MVP is complete when a loan officer can:

1. Create a loan application.
2. Upload a payslip, bank statement, and (when applicable) existing loan statement.
3. See which documents are missing.
4. Extract and persist structured data from the documents.
5. Reuse saved extraction results without unnecessarily calling the LLM again.
6. Compare data across documents and identify discrepancies with evidence.
7. Calculate income, existing obligations, and cash-flow metrics deterministically.
8. Request additional documents or clarification with human approval.
9. Run/resume the investigation workflow.
10. Review a clear report containing evidence, calculations, uncertainties, and limitations.
11. Record the human review outcome.

The MVP should use synthetic data for demos and should not independently approve or reject loan applications.

**Current stopping point:** Both payslip and bank-statement extraction have been tested successfully. The next task is cross-document financial verification. The frontend has not yet been started.
