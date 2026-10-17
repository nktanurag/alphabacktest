from docqa import extract


class _Page:
    def __init__(self, text):
        self._text = text

    def extract_text(self, visitor_text=None):
        return self._text


class _Reader:
    is_encrypted = False
    metadata = None
    outline = []

    def __init__(self, _data):
        self.pages = [_Page("The registrant is a shell company. Yes \x00 No x and some more words to reach the length limit.")]


def test_nul_bytes_are_removed_from_extracted_text(monkeypatch):
    monkeypatch.setattr(extract, "PdfReader", _Reader)
    out = extract.extract_pdf(b"%PDF-fake")
    assert all("\x00" not in text for text in out.pages) and "Yes" in out.pages[0] and "No x" in out.pages[0]


def _layout_pdf(pages: list[list[tuple[str, int, str]]]) -> bytes:
    """pages: per page, lines of (font, size, text) drawn from the top down."""
    import io

    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for lines in pages:
        y = 780
        for font, size, text in lines:
            c.setFont(font, size)
            c.drawString(72, y, text)
            y -= size + 8
        c.showPage()
    c.save()
    return buf.getvalue()


BODY = ("Helvetica", 10, "ordinary body text goes here and carries on for a good while across the page width")


def test_heading_is_found_from_the_layout_not_from_word_lists():
    running = ("Helvetica-Bold", 12, "Quarterly Filing Header")        # bold, but on every page: not a heading
    pdf = _layout_pdf([
        [running, ("Helvetica-Bold", 16, "CONSOLIDATED BALANCE SHEETS"), BODY, BODY],
        [running, ("Helvetica-Bold", 16, "Zorblat Quantum Flux Ledger"), BODY, BODY],     # any wording works
        [running, BODY, BODY, BODY],                                                       # no heading on this page
        [running, ("Helvetica-Bold", 16, "Another Section Title"), BODY, BODY],
    ])
    out = extract.extract_pdf(pdf)
    assert out.headings[0] == "CONSOLIDATED BALANCE SHEETS"
    assert out.headings[1] == "Zorblat Quantum Flux Ledger"
    assert out.headings[2] is None
    assert out.headings[3] == "Another Section Title"


def test_numbers_and_dates_are_not_headings():
    pdf = _layout_pdf([[("Helvetica-Bold", 12, "December 31, 2022"), ("Helvetica-Bold", 12, "1,234 5,678"), BODY, BODY]] * 1
                      + [[BODY, BODY, BODY]] * 2)
    assert extract.extract_pdf(pdf).headings[0] is None


def test_filing_numbers_are_not_used_as_titles():
    assert extract._title("0000764478-23-000041") is None
    assert extract._title("10-K - 02/27/2023 - Advanced Micro Devices, Inc.") == "10-K - 02/27/2023 - Advanced Micro Devices, Inc."
    assert extract._title("Annual Report 2025") == "Annual Report 2025"


def test_nul_bytes_never_reach_headings(monkeypatch):
    class Page:
        mediabox = type("Box", (), {"height": 792})()

        def extract_text(self, visitor_text=None):
            visitor_text("CONSOLIDATED \x00 BALANCE SHEETS", [1, 0, 0, 1, 0, 0], [1, 0, 0, 1, 72, 760], {"/BaseFont": "/Helvetica-Bold"}, 14)
            visitor_text("body text " * 4, [1, 0, 0, 1, 0, 0], [1, 0, 0, 1, 72, 500], {"/BaseFont": "/Helvetica"}, 10)
            return "CONSOLIDATED BALANCE SHEETS body text body text body text body text"

    class Reader(_Reader):
        def __init__(self, _data):
            self.pages = [Page(), Page(), Page(), Page()]
    monkeypatch.setattr(extract, "PdfReader", Reader)
    out = extract.extract_pdf(b"%PDF-fake")
    assert out.headings and all(h is None or "\x00" not in h for h in out.headings)
