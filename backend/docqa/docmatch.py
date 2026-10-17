"""Which documents does a question name? Matches the question's words against each document's title or file name
(company, report, year), so a search over many documents can also look inside the ones the question mentions.
Metadata matching only: nothing is added to the question and no word lists are used."""
import re

_GENERIC = frozenset("""annual report reports form integrated financial statements statement earnings results quarter quarterly
inc corp corporation company limited ltd plc llc co the and for pdf final draft version copy""".split())
_FORM = re.compile(r"^\d{1,2}[kq]$", re.I)          # 10K, 10Q, 8K
_YEAR = re.compile(r"^(19|20)\d{2}$")


def _pieces(text: str) -> list[str]:
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)          # SomeCompany -> Some Company
    return [p.lower() for p in re.findall(r"[A-Za-z0-9]+", spaced)]


def name_keys(title: str) -> set[str]:
    """Words of the title that name something: not a form type, a year, a number or a generic report word."""
    return {p for p in _pieces(title)
            if p not in _GENERIC and not _FORM.match(p) and not _YEAR.match(p) and not p.isdigit()
            and (len(p) >= 4 or re.search(r"\d", p) and re.search(r"[a-z]", p))}   # "3m" counts, "ab" does not


def years(text: str) -> set[str]:
    found = {p for p in _pieces(text) if _YEAR.match(p)}
    for m in re.findall(r"\bfy\s?(\d{4}|\d{2})\b", text.lower()):   # "FY22" and "FY2022" -> 2022
        found.add(m if len(m) == 4 else "20" + m)
    return found


def named_documents(question: str, docs: list[tuple[int, str]]) -> set[int]:
    """Ids of the documents (id, title) whose name appears in the question, and whose year does not contradict it."""
    q_tokens = set(_pieces(question))
    q_joined = "".join(_pieces(question))     # "Best Buy's" -> "bestbuys", which contains the file-name word "bestbuy"
    q_years = years(question)
    out = set()
    for doc_id, title in docs:
        keys = name_keys(title)
        if not keys or not any(k in q_tokens or (len(k) >= 6 and k in q_joined) for k in keys):
            continue
        d_years = years(title)
        if q_years and d_years and not (q_years & d_years):
            continue
        out.add(doc_id)
    return out
