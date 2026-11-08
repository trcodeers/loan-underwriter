from pathlib import Path

import pymupdf


def extract_pdf_text(file_path: str) -> dict:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError("PDF document not found")

    try:
        with pymupdf.open(str(path)) as pdf:
            page_texts = []

            for page_number, page in enumerate(pdf, start=1):
                text = page.get_text("text").strip()

                if text:
                    page_texts.append(
                        f"[Page {page_number}]\n{text}"
                    )

            extracted_text = "\n\n".join(page_texts)

            return {
                "page_count": len(pdf),
                "extracted_text": extracted_text,
                "has_extractable_text": bool(extracted_text),
            }

    except Exception as exc:
        raise ValueError(
            "Unable to read the PDF document"
        ) from exc