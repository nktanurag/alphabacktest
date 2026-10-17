"""Experimental page text with the table grid kept: words are grouped into rows by their vertical position, and a
" | " marks every wide horizontal gap, so `Revenue | 9,583 | 10,329` keeps its columns. Not used by the app; the
evaluation harness swaps it in with `--extractor plumber` to measure whether it helps retrieval."""
import io

import pdfplumber

ROW_TOLERANCE = 3     # points: words whose tops differ by less than this share a row
COLUMN_GAP = 14       # points: a wider gap between two words starts a new cell


def page_text(page) -> str:
    words = page.extract_words(x_tolerance=1.5)
    rows: list[list[dict]] = []
    top = None
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and top is not None and abs(top - w["top"]) <= ROW_TOLERANCE:
            rows[-1].append(w)
        else:
            rows.append([w])
            top = w["top"]
    lines = []
    for ws in rows:
        ws.sort(key=lambda w: w["x0"])
        cells, cur = [], [ws[0]]
        for a, b in zip(ws, ws[1:]):
            if b["x0"] - a["x1"] > COLUMN_GAP:
                cells.append(cur)
                cur = [b]
            else:
                cur.append(b)
        cells.append(cur)
        lines.append(" | ".join(" ".join(w["text"] for w in c) for c in cells))
    return "\n".join(lines)


def extract_pages(data: bytes) -> list[str]:
    with pdfplumber.open(io.BytesIO(data), password="") as pdf:
        return [page_text(p).replace("\x00", " ").strip() for p in pdf.pages]
