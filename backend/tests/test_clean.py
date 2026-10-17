from docqa.clean import clean_pages


def pages(n, header="Acme Ltd Annual Report 2025-26", footer="Confidential", body=lambda i: f"Body text of page {i} with revenue 4.2 bn."):
    return [f"{header}\n{body(i)}\n{footer}" for i in range(1, n + 1)]


def test_running_header_and_footer_are_removed_but_body_is_kept():
    out = clean_pages(pages(10))
    assert len(out) == 10
    assert all("Acme Ltd" not in p and "Confidential" not in p for p in out)
    assert out[3] == "Body text of page 4 with revenue 4.2 bn."


def test_headers_that_differ_only_by_page_number_are_removed():
    raw = [f"Annual Report 2025 | {i}\nSome real content here {'x' * i}." for i in range(1, 9)]
    assert all("Annual Report" not in p for p in clean_pages(raw))


def test_page_numbers_are_removed_when_most_pages_have_one():
    raw = [f"Text of page {i}.\n{270 + i} {271 + i}" for i in range(1, 9)]
    assert all(p == f"Text of page {i}." for i, p in enumerate(clean_pages(raw), start=1))


def test_a_stray_number_on_one_page_is_not_mistaken_for_a_page_number():
    raw = ["Revenue was\n4200\nin total.\n12"] + [f"Plain page {i}." for i in range(2, 9)]
    out = clean_pages(raw)
    assert "4200" in out[0] and out[0].endswith("12")


def test_repeating_body_lines_with_figures_are_not_removed_as_headers():
    raw = [f"Intro {i}.\nTotal {i * 100} 200" for i in range(1, 9)]
    assert all("Total" in p for p in clean_pages(raw))


def test_unit_lines_are_kept_even_when_they_repeat_at_the_top():
    raw = [f"(in crore)\nRow {i} 100 200" for i in range(1, 9)]
    assert all(p.startswith("(in crore)") for p in clean_pages(raw))


def test_short_documents_are_left_alone():
    raw = ["Header\nPage one text.", "Header\nPage two text."]
    assert clean_pages(raw) == raw


def test_rupee_sign_is_repaired_in_unit_lines_only():
    out = clean_pages(["(I in crore)\nTotal I 5", "(H in crore)", "( ` in crore)", "He said I in lakhs. but I think so"])
    assert out[0].startswith("(₹ in crore)") and "Total I 5" in out[0]
    assert out[1] == "(₹ in crore)"
    assert out[2] == "( ₹ in crore)"
    assert "I think" in out[3]


def test_doubled_titles_and_whitespace_are_collapsed():
    out = clean_pages(["Consolidated Financial StatementsConsolidated Financial Statements\nProfit\t  after   tax"])
    assert out[0] == "Consolidated Financial Statements\nProfit after tax"


def test_no_text_stays_no_text():
    assert clean_pages(["", "   \n  "]) == ["", ""]


def test_table_rows_ending_in_different_numbers_are_not_taken_for_a_running_footer():
    pages = [f"Section text for page {i} with some words\nbody line of the page number {i}\nTotal revenue {v}"
             for i, v in enumerate([2023, 1980, 1744, 2101, 1390, 2290, 1805, 1667, 2412, 1956], start=1)]
    cleaned = clean_pages(pages)
    assert all("Total revenue" in c for c in cleaned)          # figures survive


def test_a_footer_with_growing_page_numbers_is_still_removed():
    pages = [f"body text of page {i} here\nmore body words follow\nAnnual Report 2025 {i + 40}" for i in range(1, 11)]
    assert all("Annual Report" not in c for c in clean_pages(pages))
