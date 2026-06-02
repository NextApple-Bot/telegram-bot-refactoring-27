from bot.services.payment_parser import extract_payment_amounts, extract_prepayments
from bot.utils.parser import parse_birth_date, parse_client_data


def test_extract_payment_amounts_basic():
    text = "Наличные - 1000\nтерминал 500"
    payments = extract_payment_amounts(text)
    assert payments['cash'] == 1000.0
    assert payments['terminal'] == 500.0


def test_extract_prepayments():
    text = "П/О 2000 (нал)"
    payments = extract_prepayments(text)
    assert payments['cash'] == 2000.0


def test_ignore_prepay_flag():
    text = "П/О 2000\nНаличные 1000"
    payments = extract_payment_amounts(text, ignore_prepay=True)
    assert payments['cash'] == 1000.0


class TestParseBirthDate:
    def test_full_date(self):
        assert parse_birth_date("01.03.1970") == "01.03.1970"

    def test_short_date(self):
        assert parse_birth_date("01.03") == "01.03"

    def test_invalid_date(self):
        assert parse_birth_date("32.13.2020") is None

    def test_no_date(self):
        assert parse_birth_date("Привет мир") is None


class TestParseClientData:
    def test_phone_and_name(self):
        text = "Иван Иванов +79991234567"
        data = parse_client_data(text)
        assert data['full_name'] == "Иван Иванов"
        assert data['main_phone'] == "+79991234567"

    def test_telegram_and_social(self):
        text = "@telegram_username Соцсети: Instagram"
        data = parse_client_data(text)
        assert data['telegram_username'] == "telegram_username"
        assert data['social_network'] == "Instagram"

    def test_birth_date_from_text(self):
        text = "01.03.1970"
        data = parse_client_data(text)
        assert data['birth_date'] == "01.03.1970"

    def test_no_relevant_info(self):
        text = "Какой-то текст без данных"
        data = parse_client_data(text)
        assert data['full_name'] is None
        assert data['phones'] == []
