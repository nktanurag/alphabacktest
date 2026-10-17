from docqa import docmatch

DOCS = [(1, "AMERICANEXPRESS_2022_10K"), (2, "BESTBUY_2023_10K"), (3, "3M_2022_10K"), (4, "Reliance Industries Integrated Annual Report 2025-26")]


def test_names_in_the_question_pick_documents():
    assert docmatch.named_documents("What was the largest liability in American Express's Balance Sheet?", DOCS) == {1}
    assert docmatch.named_documents("Are Best Buy's gross margins consistent?", DOCS) == {2}
    assert docmatch.named_documents("Does 3M have a healthy quick ratio?", DOCS) == {3}
    assert docmatch.named_documents("What did Reliance report for CBG output?", DOCS) == {4}


def test_no_name_means_no_match_and_generic_words_do_not_count():
    assert docmatch.named_documents("What is the quick ratio?", DOCS) == set()
    assert docmatch.named_documents("Summarise the annual report and financial statements", DOCS) == set()


def test_a_year_in_the_question_must_agree_with_the_document():
    docs = [(1, "ACME_2021_10K"), (2, "ACME_2022_10K")]
    assert docmatch.named_documents("ACME revenue in FY2022", docs) == {2}
    assert docmatch.named_documents("ACME revenue in FY22", docs) == {2}
    assert docmatch.named_documents("ACME revenue", docs) == {1, 2}   # no year asked: both stay


def test_name_keys_ignore_forms_years_and_generic_words():
    assert docmatch.name_keys("AMD_2022_10K") == {"amd"} or docmatch.name_keys("AMD_2022_10K") == set()
    assert "10k" not in docmatch.name_keys("Acme_10K_2022") and "2022" not in docmatch.name_keys("Acme_10K_2022")
