
from bot.handlers.topics.arrival import determine_category_for_item


def test_determine_category_exact_match():
    categories = [{"header": "iPhone 17:"}, {"header": "Б/У:"}]
    result = determine_category_for_item("iPhone 17 256GB", categories)
    assert result == "iPhone 17:"

    result = determine_category_for_item("Б/У - iPhone 13", categories)
    assert result == "Б/У:"


def test_determine_category_fallback():
    categories = [{"header": "iPad:"}]
    result = determine_category_for_item("iPhone 15 Pro", categories)
    assert result == "iPhone 15 Pro:"


def test_determine_category_with_whitespace():
    categories = [{"header": "Apple Watch S10:"}]
    result = determine_category_for_item("Apple Watch S10 45mm", categories)
    assert result == "Apple Watch S10:"
