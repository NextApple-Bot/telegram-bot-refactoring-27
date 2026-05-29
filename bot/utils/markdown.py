def escape_markdown(text: str) -> str:
    """Alias for escape_markdown_v1 (for backward compatibility)"""
    return escape_markdown_v1(text)


def escape_markdown_v1(text: str) -> str:
    """Экранирование для MarkdownV1 (используется в aiogram)."""
    if not text:
        return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text


def bold(text: str) -> str:
    """Жирный текст."""
    return f"<b>{text}</b>"


def italic(text: str) -> str:
    """Курсив."""
    return f"<i>{text}</i>"


def code(text: str) -> str:
    """Моноширинный текст."""
    return f"<code>{text}</code>"


def pre(text: str) -> str:
    """Блок кода."""
    return f"<pre>{text}</pre>"


def link(text: str, url: str) -> str:
    """Ссылка."""
    return f'<a href="{url}">{text}</a>'


def escape_for_html(text: str) -> str:
    """Экранирование HTML-символов."""
    return (text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def format_price_html(price: int) -> str:
    """Красивое форматирование цены в HTML."""
    if price is None:
        return "0 ₽"
    return f"{price:,}".replace(",", " ") + " ₽"
