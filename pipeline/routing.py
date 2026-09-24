"""Decide how to send a PDF to the model.

This is the piece that gets the most attention in an interview, because it
is a cost decision rather than a capability decision. A vision call on a
two-page document costs several times what the same document costs as text,
so you pay that only when you have to.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from pypdf import PdfReader

# A one-page contract with a real text layer runs well over a thousand
# characters. The shortest digital invoice in the corpus is 177. So 100 sits
# comfortably below any legitimate document and comfortably above the stray
# artifacts a scanner sometimes leaves behind. It is a heuristic, not a
# truth, and it is worth saying so out loud.
MIN_CHARS = 100
RENDER_DPI = 150


def pdf_text(pdf_path: str | Path) -> str:
    return "".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)


def build_content_blocks(pdf_path: str | Path) -> tuple[list[dict], str, str]:
    """Return (content_blocks, path_taken, source_text).

    source_text is empty on the vision path, which is exactly why the
    grounding check returns None there. You cannot verify a value against a
    text layer that does not exist, and pretending otherwise would put a
    fake confidence number into the verdict.
    """
    text = pdf_text(pdf_path)
    if len(text.strip()) >= MIN_CHARS:
        return [{"type": "text", "text": text}], "text", text

    import pypdfium2 as pdfium

    blocks: list[dict] = []
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        for i in range(len(pdf)):
            image = pdf[i].render(scale=RENDER_DPI / 72).to_pil()
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.standard_b64encode(buf.getvalue()).decode(),
                },
            })
    finally:
        pdf.close()
    return blocks, "vision", ""
