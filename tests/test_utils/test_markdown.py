from bot.utils.markdown import escape_markdown, escape_markdown_v1


def test_escape_markdown_special_chars():
    text = "Hello _world_ *test* [link]"
    escaped = escape_markdown(text)
    assert "\\_" in escaped and "\\*" in escaped


def test_escape_markdown_no_special_chars():
    assert escape_markdown("Plain text") == "Plain text"


def test_escape_markdown_v1():
    text = "Hello _world_ `code`"
    escaped = escape_markdown_v1(text)
    assert "\\_" in escaped and "\\`" in escaped


def test_escape_markdown_v1_no_special_chars():
    assert escape_markdown_v1("Plain text") == "Plain text"
