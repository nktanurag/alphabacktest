from . import config


def chunk_pages(pages: list[str], size: int = config.CHUNK_WORDS,
                overlap: int = config.CHUNK_OVERLAP_WORDS) -> list[tuple[int, str]]:
    """Split page text into overlapping word windows. A chunk never crosses a page, so its page is exact.

    Returns (page_number starting at 1, text) in document order.
    """
    step = max(size - overlap, 1)
    out: list[tuple[int, str]] = []
    for number, text in enumerate(pages, start=1):
        words = text.split()
        for start in range(0, len(words), step):
            window = words[start:start + size]
            if window:
                out.append((number, " ".join(window)))
            if start + size >= len(words):
                break
    return out


def page_label(bookmarks: str | None, heading: str | None) -> str | None:
    """Where a page sits: its bookmark path and the heading found on the page itself, whichever exist."""
    if bookmarks and heading and heading.lower() not in bookmarks.lower():
        return f"{bookmarks} > {heading}"[:500]
    return bookmarks or heading


def with_context(title: str | None, section: str | None, text: str) -> str:
    """The text the models see: a one-line header (document title and section) above the passage.

    Used for embedding and reranking only; the stored and displayed passage stays as it is in the PDF.
    """
    header = " | ".join(part[:200] for part in (title, section) if part)
    return f"{header}\n\n{text}" if header else text
