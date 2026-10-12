import pytest

from alphabacktest.db import normalize_database_url


@pytest.mark.parametrize("url, expected", [
    ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("sqlite:///./x.db", "sqlite:///./x.db"),
])
def test_normalize_database_url(url, expected):
    assert normalize_database_url(url) == expected
