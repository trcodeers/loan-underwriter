# Loan Underwriting Assistant — Local Setup

This guide explains how to set up the backend after cloning the repository.

> **Project status:** This project is under active development. Follow the implemented setup steps below. Features that are still being built are identified separately.

## 1. Prerequisites

- macOS, Linux, or Windows with a terminal
- Git
- [uv](https://docs.astral.sh/uv/) installed
- Python 3.13 or newer (the project configuration specifies `requires-python = ">=3.13"`)

Check your tools:

```bash
git --version
uv --version
python3 --version
```

You do not need to create or activate a virtual environment manually. `uv` manages the project environment.

## 2. Clone the repository

Replace `<REPOSITORY_URL>` with the Git URL for this project:

```bash
git clone <REPOSITORY_URL>
cd loan-underwriting
```

Run all commands in this guide from the project root, where `pyproject.toml` and `alembic.ini` are located.

## 3. Install project dependencies

```bash
uv sync
```

`uv sync` creates the project's `.venv` environment if it does not exist and installs the dependencies declared in `pyproject.toml` and `uv.lock`.

Keep `uv.lock` committed to Git so other developers install the same resolved dependency versions.

## 4. Configure environment variables

Create your local environment file:

```bash
cp .env.example .env
```

If the repository does not yet contain `.env.example`, create `.env` in the project root and add:

```env
DATABASE_URL=sqlite:///./data/loan_underwriting.db
```

The database URL points to a local SQLite database file. The `.env` file is for local configuration and secrets; it should not be committed to Git.

### Gemini API key

The current application and database setup do not require a Gemini API key. Add your Gemini key only when running the AI functionality that uses Gemini. Never commit the key to the repository.

## 5. Create the local data directory

The SQLite database is stored under `data/`. Create the directory if it is not already present:

```bash
mkdir -p data/uploads
```

Uploaded documents will be stored here when the document upload feature is implemented. Treat this directory as local application data and do not commit real borrower documents.

## 6. Create or update database tables

The repository uses SQLAlchemy for database models and Alembic for database schema migrations.

After cloning, apply the migrations already included in the repository:

```bash
uv run alembic upgrade head
```

This creates or updates the local database tables to the latest committed migration.

**Important:** When setting up a clone, do not generate a new migration with `revision --autogenerate`. That command is for developers who have changed SQLAlchemy models and need to create a new migration. The migration file should be reviewed and committed by the developer who made the schema change.

If you are developing a new model or changing an existing model, the usual workflow is:

```bash
uv run alembic revision --autogenerate -m "describe the schema change"
```

Review the generated Python file in `migrations/versions/`, then apply it locally:

```bash
uv run alembic upgrade head
```

## 7. Start the API

From the project root:

```bash
uv run uvicorn app.main:app --reload
```

The `uv run` command runs Uvicorn inside the project's managed environment. The `--reload` option restarts the development server when code changes.

When the server starts, the application's startup hook checks that the configured database can be reached. Database tables are created by Alembic, not by starting FastAPI.

## 8. Open the API documentation

With the server running, open:

- API documentation (Swagger UI): <http://127.0.0.1:8000/docs>
- Alternative API documentation: <http://127.0.0.1:8000/redoc>
- Root endpoint: <http://127.0.0.1:8000/>
- Health endpoint: <http://127.0.0.1:8000/health>

Use Swagger UI to try the available endpoints.

### Test bank statement extraction

1. Use `POST /api/v1/applications/` to create an application, or use an existing application ID.
2. Use `POST /api/v1/applications/{application_id}/documents` to upload a PDF with `document_type` set to `bank_statement`.
3. Use the returned document ID with `POST /api/v1/applications/{application_id}/documents/{document_id}/analyze-bank-statement`.
4. Review the response for bank details and transactions. Account numbers are limited to their last four digits; unavailable values should be `null`.
5. Repeat the analysis request to exercise the cached result. Confirm the saved record locally with (replace `<document_id>` with the uploaded document ID):

   ```sql
   SELECT document_id, extraction_type, extracted_data
   FROM document_extractions
   WHERE document_id = <document_id>
     AND extraction_type = 'bank_statement';
   ```

The endpoint returns the saved extraction on subsequent requests rather than invoking the model again. The existing payslip endpoint, `POST /api/v1/applications/{application_id}/documents/{document_id}/analyze-payslip`, remains available.

## 9. Project structure

The backend uses a deliberately small structure:

```text
loan-underwriting/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application and router registration
│   ├── api/                    # HTTP endpoints
│   ├── db/                     # SQLAlchemy Base, engine, and DB sessions
│   ├── models/                 # SQLAlchemy database models
│   ├── schemas/                # Pydantic request and response schemas
│   ├── services/               # Business logic and document processing
│   └── ai/                     # LLM configuration and AI functionality
├── migrations/
│   ├── env.py                  # Alembic configuration and model metadata
│   └── versions/                # Versioned database migrations
├── data/
│   └── uploads/                # Local uploaded files (do not commit real data)
├── .env.example                # Example local configuration
├── .gitignore
├── alembic.ini
├── pyproject.toml              # Project metadata and dependencies
└── uv.lock                     # Locked dependency versions
```

Some folders may be mostly empty while the project is being developed.

## 10. Database configuration and PostgreSQL later

The application uses SQLAlchemy so its database models and most database operations are not tied to SQLite.

For local development, `.env` uses:

```env
DATABASE_URL=sqlite:///./data/loan_underwriting.db
```

To use PostgreSQL later, configure a PostgreSQL URL and install its driver. For example:

```bash
uv add "psycopg[binary]"
```

Then set `DATABASE_URL` to the connection string supplied for your PostgreSQL database, for example:

```env
DATABASE_URL=postgresql+psycopg://USERNAME:PASSWORD@HOST:5432/DATABASE_NAME
```

The PostgreSQL server must already be available and the database must exist. Apply the committed migrations against it with:

```bash
uv run alembic upgrade head
```

Changing the URL does not copy existing SQLite data into PostgreSQL. Data migration is a separate step if you need to preserve existing records.

## 11. Common commands

Run these from the project root:

| Task | Command |
|---|---|
| Install/synchronize dependencies | `uv sync` |
| Add a runtime dependency | `uv add package-name` |
| Run a Python command | `uv run python -c "print('hello')"` |
| Start the API | `uv run uvicorn app.main:app --reload` |
| Apply database migrations | `uv run alembic upgrade head` |
| Generate a migration after changing models | `uv run alembic revision --autogenerate -m "describe change"` |
| Check current migration revision | `uv run alembic current` |
| Show migration history | `uv run alembic history` |

There is no need to run `pip install`, manually activate `.venv`, or invoke a system Python for normal project work. Use `uv add` when adding dependencies and `uv run` when running project tools.

## 12. Troubleshooting

### `uv sync` reports a package/module build error

Check the build configuration in `pyproject.toml` and confirm that the configured Python module name matches the actual package directory `app/`. This project uses the `uv_build` backend and the Python package is named `app` even though the project/distribution is named `loan-underwriting`.

### `ModuleNotFoundError: No module named 'app'`

Make sure you are running the command from the repository root (the directory containing `pyproject.toml`) and that `app/__init__.py` exists.

### Alembic cannot find a model or generates an empty migration

Check that `migrations/env.py` imports the SQLAlchemy model modules before assigning `target_metadata = Base.metadata`. SQLAlchemy models must be imported so their tables are registered in `Base.metadata`.

### Alembic says there are no changes

That can be correct if the database already matches the models. Also confirm that the model was imported by `migrations/env.py` and that the intended migration has not already been generated.

### Database connection fails

Check the `DATABASE_URL` value in `.env`. For SQLite, confirm that the `data/` directory exists and is writable. For PostgreSQL, confirm the server is running, the database exists, and the connection credentials are correct.

## 13. Development and data safety notes

- Do not commit `.env`, API keys, database files, or uploaded borrower documents.
- Use synthetic or test documents during development. Do not upload real customer financial information to an external model or service without an approved data-protection and deployment arrangement.
- The project is an underwriting investigation assistant, not an autonomous lending decision system. A qualified human reviewer remains responsible for lending decisions.
- Before production use, add authentication, authorization, tenant isolation, secure file storage, encryption, malware scanning, audit logging, retention/deletion controls, and appropriate compliance reviews.

## Current implementation status

This repository is under active development. The setup, FastAPI foundation, SQLAlchemy database configuration, loan application model and CRUD APIs, and initial Alembic migration workflow are the current foundation. The document model has been introduced; the PDF upload and subsequent AI underwriting workflow are being developed incrementally. Consult the code and API documentation for the exact endpoints currently available.

---

For development, start the API with:

```bash
uv run uvicorn app.main:app --reload
```
