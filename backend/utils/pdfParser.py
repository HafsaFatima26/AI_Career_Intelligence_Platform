"""
Lightweight PDF → plain-text extractor using PyPDF2.
Enforces: max 3 pages, max 2 MB (checked at route level).
"""
import io
from PyPDF2 import PdfReader

MAX_PAGES = 3


def extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = reader.pages[:MAX_PAGES]
    text = "\n".join(page.extract_text() or "" for page in pages)
    if not text.strip():
        raise ValueError("Could not extract text from PDF. Ensure it is not scanned/image-only.")
    return text.strip()
