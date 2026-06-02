from bot.services.payment_parser import extract_payment_amounts


def test_terminal_priority():
    text = "Терминал - 2500"
    payments = extract_payment_amounts(text)
    assert payments['terminal'] == 2500.0
    assert payments['cash'] == 0.0


def test_cash_only():
    text = "Наличные 1000"
    payments = extract_payment_amounts(text)
    assert payments['cash'] == 1000.0
    assert payments['terminal'] == 0.0


def test_mixed_payments():
    text = "Наличные 1000\nТерминал 2000"
    payments = extract_payment_amounts(text)
    assert payments['cash'] == 1000.0
    assert payments['terminal'] == 2000.0


def test_no_payments():
    text = "Просто текст без цифр"
    payments = extract_payment_amounts(text)
    assert all(v == 0.0 for v in payments.values())
