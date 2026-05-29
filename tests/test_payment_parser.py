import pytest

from bot.services.payment_parser import extract_payment_amounts


@pytest.mark.parametrize("text,expected", [
    ("Терминал - 2500", {'terminal': 2500.0}),
    ("Наличные 1000", {'cash': 1000.0}),
    ("Наличные 1500.50\nТерминал 2000", {'cash': 1500.5, 'terminal': 2000.0}),
    ("QR 3000 ₽", {'qr': 3000.0}),
    ("Перевод 5000", {'transfer': 5000.0}),
    ("Просто текст без цифр", {'cash': 0.0, 'terminal': 0.0, 'qr': 0.0,
                               'transfer': 0.0, 'invoice': 0.0, 'installment': 0.0}),
])
def test_extract_payment_amounts(text, expected):
    payments = extract_payment_amounts(text)
    for key, value in expected.items():
        assert abs(payments[key] - value) < 0.001
