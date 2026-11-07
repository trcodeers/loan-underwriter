from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import settings


async def save_document(
    file: UploadFile,
    application_id: int,
) -> dict:

    max_size = settings.max_upload_size_mb * 1024 * 1024

    # Check filename
    filename = (file.filename or "").replace("\\", "/")
    original_filename = Path(filename).name

    if not original_filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are allowed")

    # Read and validate file size
    content = await file.read(max_size + 1)

    if not content:
        raise ValueError("Uploaded file is empty")

    if len(content) > max_size:
        raise ValueError("File exceeds maximum allowed size")

    # Validate actual PDF signature
    if not content[:1024].lstrip().startswith(b"%PDF-"):
        raise ValueError("Invalid PDF file")

    # Generate unique filename
    stored_filename = f"{uuid4().hex}.pdf"

    # Create application-specific directory
    upload_path = settings.upload_dir / str(application_id)
    upload_path.mkdir(parents=True, exist_ok=True)

    file_path = upload_path / stored_filename

    # Save PDF
    file_path.write_bytes(content)

    return {
        "original_filename": original_filename[:255],
        "storage_path": str(file_path),
        "file_size": len(content),
    }