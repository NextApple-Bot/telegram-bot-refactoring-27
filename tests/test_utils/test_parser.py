
from bot.services.payment_parser import extract_payment_amounts, extract_prepayments
from bot.utils.parser import parse_birth_date, parse_client_data


def test_extract_payment_amounts():
    assert extract_payment_amounts("Наличные - 1000\nтерминал 500")['cash'] == 1000.0
    assert extract_payment_amounts("Просто текст")['cash'] == 0.0


def test_extract_prepayments():
    result = extract_prepayments("П/О 2000 (нал)")
    assert result['cash'] == 2000.0


def test_parse_birth_date():
    assert parse_birth_date("01.03.1970") == "01.03.1970"
    assert parse_birth_date("01.03") == "01.03"
    assert parse_birth_date("32.13.2020") is None
    assert parse_birth_date("Привет") is None


def test_parse_client_data():
    data = parse_client_data("Иван Иванов +79991234567")
    assert data['full_name'] == "Иван Иванов"
    assert data['main_phone'] == "+79991234567"

    data = parse_client_data("@telegram_username Соцсети: Instagram")
    assert data['telegram_username'] == "telegram_username"
    assert data['social_network'] == "Instagram"
