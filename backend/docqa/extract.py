import io
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from . import clean, config


class ExtractError(Exception):
    """The file can't be used; the message is shown to the user."""


@dataclass
class Extracted:
    pages: list[str]
    sections: list[str | None]          # heading path for each page, from the PDF's bookmarks (None if it has none)
    title: str | None = None
    author: str | None = None
    created: str | None = None
    headings: list[str | None] = field(default_factory=list)   # heading found on each page from the layout (None if none)


def _clean(value) -> str | None:
    text = str(value).strip() if value else ""
    return text[:500] or None


def _title(value) -> str | None:
    """The PDF's title, unless it is the placeholder that authoring tools leave behind."""
    text = _clean(value)
    if text is None:
        return None
    low = text.lower()
    if low in ("untitled", "document", "title") or low.startswith(("microsoft word -", "microsoft powerpoint -")) \
            or low.endswith((".docx", ".doc", ".indd", ".pptx", ".tex")):
        return None
    if sum(c.isalpha() for c in text) < 0.4 * len(text):   # "0000764478-23-000041": a filing number, not a title
        return None
    return text


def _created(meta) -> str | None:
    try:
        d = meta.creation_date
        return d.date().isoformat() if d else None
    except Exception:
        return _clean(getattr(meta, "creation_date_raw", None))


def _flatten(items, reader, depth=0, out=None):
    """Bookmarks as (page index, depth, title) in document order."""
    out = [] if out is None else out
    for item in items:
        if isinstance(item, list):
            _flatten(item, reader, depth + 1, out)
            continue
        try:
            out.append((reader.get_destination_page_number(item), depth, str(item.title).strip()[:200]))
        except Exception:
            continue
    return out


def _sections(reader, page_count: int) -> list[str | None]:
    """For each page, the bookmark path (for example "Risk Factors > Suppliers") in force at that page."""
    try:
        entries = [e for e in _flatten(reader.outline, reader) if e[2] and e[0] is not None and 0 <= e[0] < page_count]
    except Exception:
        return [None] * page_count
    stack: list[str] = []
    path_at: list[tuple[int, str]] = []
    for page, depth, title in entries:
        stack = stack[:depth] + [title]
        path_at.append((page, " > ".join(stack)[:500]))
    result: list[str | None] = []
    for p in range(page_count):
        current = None
        for page, path in path_at:      # the last bookmark at or before this page wins
            if page <= p:
                current = path
        result.append(current)
    return result


_BOLD = re.compile(r"bold|black|heavy|semibold|demi|\bbd\b|-bd", re.I)
_TOP_OF_PAGE = 0.65          # a heading is searched for in the top 35 percent of the page
_MAX_HEADING_WORDS = 12


def _page_lines(frags: list[tuple[float, str, float, bool]]) -> list[tuple[float, str, float, bool]]:
    """Text fragments (y, text, font size, bold) joined into lines: (y, text, size, bold)."""
    lines: list[list] = []
    for y, text, size, bold in frags:
        if lines and abs(lines[-1][0] - y) <= 2:
            lines[-1][1].append(text.strip())
            lines[-1][2] = max(lines[-1][2], size)
            lines[-1][3] = lines[-1][3] and bold
        else:
            lines.append([y, [text.strip()], size, bold])
    return [(y, " ".join(t for t in texts if t), size, bold) for y, texts, size, bold in lines]


def _headings(per_page: list[tuple[float, list]]) -> list[str | None]:
    """The heading of each page, found from the layout and not from word lists: the first one or two short lines in
    the top of the page that are bold, set larger than the body text, or all capitals. Lines that repeat on many
    pages (running headers such as "Table of Contents") and lines that are mostly numbers or dates are skipped."""
    candidates: list[list[str]] = []
    for height, frags in per_page:
        lines = _page_lines(frags)
        sizes = [size for _, text, size, _ in lines for _ in text if size]
        body = statistics.median(sizes) if sizes else 0
        found = []
        for y, text, size, bold in sorted(lines, key=lambda l: -l[0]):
            words = text.split()
            if y < _TOP_OF_PAGE * height or not 1 <= len(words) <= _MAX_HEADING_WORDS or len(text) < 4:
                continue
            if sum(c.isdigit() for c in text) > 0.3 * len(text) or not any(c.isalpha() for c in text):
                continue
            if bold or (body and size >= 1.15 * body) or (text.isupper() and len(words) >= 2):
                found.append(text)
            if len(found) == 2:
                break
        candidates.append(found)
    repeats = Counter(t.lower() for page in candidates for t in set(page))
    limit = max(3, int(0.3 * len(candidates)))
    out = []
    for found in candidates:
        keep = [t for t in found if repeats[t.lower()] < limit]
        out.append(" - ".join(keep)[:200] or None)
    return out


def extract_pdf(data: bytes) -> Extracted:
    """Text of each page, in order, plus section headings and the PDF's own metadata.
    Scanned (image-only) PDFs are rejected."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # Many reports are only permission-locked (an owner password) and open with an empty password.
            try:
                opened = reader.decrypt("")
            except Exception:   # e.g. an encryption method pypdf cannot handle here
                opened = 0
            if not opened:
                raise ExtractError("This PDF is password protected.")
        if len(reader.pages) > config.MAX_PAGES:
            raise ExtractError(f"This PDF has {len(reader.pages)} pages; the limit is {config.MAX_PAGES}.")
        # Checkbox glyphs can extract as NUL bytes, which Postgres text columns refuse to store.
        pages, layout = [], []
        for page in reader.pages:
            frags: list[tuple[float, str, float, bool]] = []

            def see(text, cm, tm, font, size, _frags=frags):
                if text.strip():
                    name = str((font or {}).get("/BaseFont", "")) if font else ""
                    _frags.append((tm[5] * cm[3] + cm[5], text.replace("\x00", " "), float(size or 0),
                                   bool(_BOLD.search(name))))
            pages.append((page.extract_text(visitor_text=see) or "").replace("\x00", " ").strip())
            try:
                layout.append((float(page.mediabox.height), frags))
            except Exception:
                layout.append((792.0, frags))
        meta = reader.metadata
        sections = _sections(reader, len(pages))
        try:
            headings = _headings(layout)
        except Exception:   # layout guessing must never make a readable file unreadable
            headings = [None] * len(pages)
    except ExtractError:
        raise
    except (PyPdfError, ValueError, KeyError, OSError):
        raise ExtractError("This file could not be read as a PDF.")
    if not pages:
        raise ExtractError("This PDF has no pages.")
    if sum(len(p) for p in pages) < 20 * len(pages):  # under ~20 characters per page
        raise ExtractError("This PDF has no readable text (it looks scanned). Scanned PDFs are not supported.")
    return Extracted(clean.clean_pages(pages), sections, _title(meta.title) if meta else None,
                     _clean(meta.author) if meta else None, _created(meta) if meta else None, headings)
