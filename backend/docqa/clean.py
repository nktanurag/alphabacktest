"""Clean the text pypdf extracts, before it is chunked.

Everything here is conservative: it only removes or rewrites things that are noise on almost every
page, and it never touches numbers or unit lines, since those carry meaning.
"""
import re

EDGE_LINES = 3          # a running header or footer is among the first or last few lines of a page
MIN_PAGES_REPEATED = 3
MIN_SHARE_REPEATED = 0.3

# Lines giving a unit or currency ("(in crore)"): context for the numbers below them, so they are kept.
_UNITS = re.compile(r"\b(in\s+(crore|lakh|million|billion|thousand)s?|crores?|lakhs?)\b|[₹$€£]|\b(rs|usd|inr)\b\.?", re.I)
# Some fonts map the rupee sign to a letter or a backtick, so it comes out as "(I in crore)" or "(H in crore)".
_RUPEE = re.compile(r"(?<![A-Za-z0-9])[IH`](?=\s+in\s+(?:crore|lakh)s?\b)")
_DOUBLED = re.compile(r"^(.{8,}?)\1$")      # "Consolidated Financial StatementsConsolidated Financial Statements"
_PAGE_NUMBER = re.compile(r"^\d{1,3}(\s*[/|]?\s*\d{1,3})?$")   # "278", "278 279", "12 / 340"


def _key(line: str) -> str:
    """Lines that differ only by a page number at the start or end count as the same line.
    Numbers inside a line are kept, so table rows and sentences with figures never look repeated."""
    text = re.sub(r"\s+", " ", line.strip().lower())
    text = re.sub(r"^\d{1,4}\s+|\s+\d{1,4}$", "", text)   # one number only
    return text


def _edge_number(line: str) -> int | None:
    """The number `_key` strips from the start or end of the line, if any."""
    m = re.search(r"^(\d{1,4})\s+|\s+(\d{1,4})$", re.sub(r"\s+", " ", line.strip().lower()))
    return int(m.group(1) or m.group(2)) if m else None


def _counts_like_page_numbers(numbers: list[int | None]) -> bool:
    """A real running header or footer has no number, the same number, or a number that grows from page to page.
    Table rows that merely end in different numbers ("Total revenue 2023", "Total revenue 1980") do not."""
    nums = [n for n in numbers if n is not None]
    if len(nums) < 2 or len(set(nums)) == 1:
        return True
    rising = sum(b >= a for a, b in zip(nums, nums[1:]))
    return rising >= 0.8 * (len(nums) - 1)


def _tidy(line: str) -> str:
    line = re.sub(r"[ \t ]+", " ", line).strip()
    line = _RUPEE.sub("₹", line)
    m = _DOUBLED.match(line)
    return m.group(1) if m else line


def clean_pages(pages: list[str]) -> list[str]:
    """The pages with running headers and footers, bare page numbers and doubled titles removed,
    whitespace collapsed, and the rupee sign repaired. The number of pages stays the same."""
    lines_by_page = [[_tidy(l) for l in text.splitlines()] for text in pages]
    lines_by_page = [[l for l in lines if l] for lines in lines_by_page]
    needed = max(MIN_PAGES_REPEATED, int(MIN_SHARE_REPEATED * len(pages)))

    # Running headers and footers: short lines near a page edge that repeat on many pages.
    seen: dict[str, list[int | None]] = {}   # line key -> the stripped number on each page that has it
    for lines in lines_by_page:
        found: dict[str, int | None] = {}
        for l in lines[:EDGE_LINES] + lines[-EDGE_LINES:]:
            if len(l) <= 150 and not _UNITS.search(l) and _key(l):
                found.setdefault(_key(l), _edge_number(l))
        for k, number in found.items():
            seen.setdefault(k, []).append(number)
    repeated = {k for k, numbers in seen.items() if len(numbers) >= needed and _counts_like_page_numbers(numbers)}

    # Page numbers: a number alone on the very first or very last line, but only if most pages have one
    # there. A stray figure at the edge of a single page (a table cell) is left alone.
    def has_number(lines: list[str], at: int) -> bool:
        return bool(lines) and bool(_PAGE_NUMBER.match(lines[at]))
    first_numbered = sum(has_number(l, 0) for l in lines_by_page) >= max(needed, len(pages) // 2)
    last_numbered = sum(has_number(l, -1) for l in lines_by_page) >= max(needed, len(pages) // 2)

    cleaned = []
    for lines in lines_by_page:
        keep = []
        for i, line in enumerate(lines):
            at_edge = i < EDGE_LINES or i >= len(lines) - EDGE_LINES
            is_header = at_edge and len(line) <= 150 and _key(line) in repeated and not _UNITS.search(line)
            is_page_number = bool(_PAGE_NUMBER.match(line)) and (
                (i == 0 and first_numbered) or (i == len(lines) - 1 and last_numbered))
            if is_header or is_page_number:
                continue
            keep.append(line)
        cleaned.append("\n".join(keep))
    return cleaned
