from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.db.database import engine

from app.api.applications import router as applications_router
from app.api.documents import router as documents_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect to the database when application starts
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    print("DB connected successfully")

    yield

    # Cleanup when application shuts down
    engine.dispose()


app = FastAPI(
    title="Loan Underwriting API",
    description="AI-powered Loan Underwriting Investigation Assistant",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(
    applications_router,
    prefix="/api/v1",
)
app.include_router(
    documents_router,
    prefix="/api/v1",
)


@app.get("/")
def root():
    return {"message": "Loan Underwriting API is running"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}