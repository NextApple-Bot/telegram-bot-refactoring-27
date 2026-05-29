import pytest

from bot.utils.validators import extract_serials, normalize_serial


@pytest.mark.parametrize("text,expected", [
    ("iPhone 15 (ABC123)", ["ABC123"]),
    ("iPhone (ABC123) and iPad (DEF456)", ["ABC123", "DEF456"]),
    ("Check (1234567890)", ["1234567890"]),
    ("Check (123456789)", []),
    ("Some () text", []),
    ("( ABC 123 )", ["ABC 123"]),
])
def test_extract_serials(text, expected):
    assert extract_serials(text) == expected


def test_normalize_serial():
    assert normalize_serial(" AB C 123 ") == "ABC123"
    assert normalize_serial("abc123") == "ABC123"
    assert normalize_serial("") == ""
    assert normalize_serial(None) == ""
