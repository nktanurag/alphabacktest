from docqa import bm25


def ids(query, chunks, limit=10):
    return [cid for cid, _ in bm25.rank(query, chunks, limit)]


def test_rare_term_outweighs_common_terms():
    chunks = [(1, "india production india production"), (2, "india production overview"),
              (3, "the cbg plants"), (4, "india india production production")]
    assert ids("What share of India's CBG production?", chunks)[0] == 3   # "cbg" is in one chunk only
    assert ids("CBG", chunks) == [3]


def test_no_shared_terms_returns_nothing_and_limit_applies():
    assert ids("zebra", [(1, "alpha beta")]) == []
    assert ids("the of", [(1, "the of")]) == []   # only stop words
    assert len(ids("alpha", [(i, "alpha") for i in range(10)], 3)) == 3


def test_plurals_fold_and_numbers_match():
    assert ids("plant", [(1, "35 operating plants"), (2, "unrelated")]) == [1]
    assert ids("30%", [(1, "over 30% of output"), (2, "over 40% of output")]) == [1]
