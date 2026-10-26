"""Isolated PDF parser process: bounded memory, CPU time and extracted text."""

import io
import json
import sys


def main():
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    except ImportError:
        pass  # Linux containers enforce these limits; Windows is not a validated deployment.
    from pypdf import PdfReader

    try:
        limit = int(sys.argv[1])
        content = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise ValueError("PDF exceeds the upload limit")
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("Upload an unencrypted PDF")
        if len(reader.pages) > 200:
            raise ValueError("PDFs are limited to 200 pages")
        pages, total = [], 0
        for index, page in enumerate(reader.pages):
            value = page.extract_text() or ""
            total += len(value)
            if total > limit:
                raise ValueError("Document text exceeds this workspace's ingestion limit")
            if value.strip():
                pages.append([index + 1, value])
        if not pages:
            raise ValueError("No selectable text found. Run OCR on scanned PDFs before uploading")
        print(json.dumps({"pages": pages}))
    except (ValueError, MemoryError) as error:
        print(json.dumps({"error": str(error) or "PDF exceeded the parser memory budget"}))
    except Exception:
        print(json.dumps({"error": "This PDF could not be parsed safely"}))


if __name__ == "__main__":
    main()
