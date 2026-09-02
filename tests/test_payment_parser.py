"""
Юнит-тесты payment_parser на реальных форматах сообщений из топика продаж.

Покрывает:
  - QR / QR - code / QR-код
  - П/О без типа → cash
  - рассрочка «N мес» (не сумма)
  - «Общая сумма» vs Σ оплат (tolerance)
  - ignore_prepay для продажи
  - пробелы/неразрывные пробелы в тысячах
"""
from bot.services.payment_parser import (
    extract_declared_total,
    extract_payment_amounts,
    extract_prepayments,
    payments_sum,
    reconcile_sale_payments,
)


def test_terminal_priority():
    text = "Терминал - 2500"
    payments = extract_payment_amounts(text)
    assert payments["terminal"] == 2500.0
    assert payments["cash"] == 0.0


def test_cash_only():
    text = "Наличные 1000"
    payments = extract_payment_amounts(text)
    assert payments["cash"] == 1000.0
    assert payments["terminal"] == 0.0


def test_mixed_payments():
    text = "Наличные 1000\nТерминал 2000"
    payments = extract_payment_amounts(text)
    assert payments["cash"] == 1000.0
    assert payments["terminal"] == 2000.0


def test_no_payments():
    text = "Просто текст без цифр"
    payments = extract_payment_amounts(text)
    assert all(v == 0.0 for v in payments.values())


def test_qr_variants():
    cases = [
        ("QR-код — 15 000", 15000.0),
        ("QR - code 15000", 15000.0),
        ("QR code: 12 500", 12500.0),
        ("QRКод 8000", 8000.0),
        ("QRкод - 3 200", 3200.0),
    ]
    for text, expected in cases:
        payments = extract_payment_amounts(text)
        assert payments["qr"] == expected, f"failed on: {text!r} → {payments}"
        assert payments["cash"] == 0.0


def test_transfer_and_invoice():
    text = "Перевод 50 000\nПо счёту 120000"
    payments = extract_payment_amounts(text)
    assert payments["transfer"] == 50000.0
    assert payments["invoice"] == 120000.0


def test_installment_ignores_months():
    """«24 мес» не должно попадать в сумму рассрочки."""
    text = "Рассрочка 90 000 24 мес"
    payments = extract_payment_amounts(text)
    assert payments["installment"] == 90000.0

    text2 = "Рассрочка — 120000 (12 месяцев)"
    payments2 = extract_payment_amounts(text2)
    assert payments2["installment"] == 120000.0


def test_thousands_with_spaces_and_nbsp():
    text = "Терминал 1\u00a0234\u00a0567"
    payments = extract_payment_amounts(text)
    assert payments["terminal"] == 1234567.0

    text2 = "Наличные 697 000"
    payments2 = extract_payment_amounts(text2)
    assert payments2["cash"] == 697000.0


def test_declared_total_extraction():
    text = (
        "iPhone 15 Pro 256 (SN123)\n"
        "Терминал 400000\n"
        "Наличные 297000\n"
        "Общая сумма — 697 000"
    )
    assert extract_declared_total(text) == 697000.0

    text2 = "1. Общая сумма — 100000\nИтого: 100000"
    assert extract_declared_total(text2) == 100000.0


def test_reconcile_ok_within_tolerance():
    text = (
        "Терминал 50000\n"
        "Наличные 30\n"
        "Общая сумма 50030"
    )
    payments = extract_payment_amounts(text)
    recon = reconcile_sale_payments(payments, text, tolerance=50.0)
    assert recon["has_declared"] is True
    assert recon["ok"] is True
    assert recon["paid"] == 50030.0
    assert recon["declared"] == 50030.0
    assert recon["diff"] == 0.0


def test_reconcile_mismatch_over_tolerance():
    text = (
        "Терминал 400000\n"
        "Наличные 200000\n"
        "Общая сумма — 700000"
    )
    payments = extract_payment_amounts(text)
    recon = reconcile_sale_payments(payments, text, tolerance=50.0)
    assert recon["has_declared"] is True
    assert recon["ok"] is False
    assert recon["paid"] == 600000.0
    assert recon["declared"] == 700000.0
    assert recon["diff"] == 100000.0


def test_reconcile_no_declared_is_ok():
    text = "Терминал 10000"
    payments = extract_payment_amounts(text)
    recon = reconcile_sale_payments(payments, text, tolerance=50.0)
    assert recon["has_declared"] is False
    assert recon["ok"] is True


def test_ignore_prepay_on_sale():
    text = (
        "П/О терминал 5000\n"
        "Терминал 45000\n"
        "Наличные 10000"
    )
    with_prepay = extract_payment_amounts(text, ignore_prepay=False)
    assert with_prepay["terminal"] == 50000.0  # 5k + 45k

    sale_only = extract_payment_amounts(text, ignore_prepay=True)
    assert sale_only["terminal"] == 45000.0
    assert sale_only["cash"] == 10000.0


def test_prepay_without_type_defaults_to_cash():
    text = "П/О — 15 000\nП/О терминал 3000"
    pre = extract_prepayments(text)
    assert pre["cash"] == 15000.0
    assert pre["terminal"] == 3000.0


def test_prepay_only_lines():
    text = (
        "Клиент Иван\n"
        "П/О QR 8000\n"
        "просто комментарий"
    )
    pre = extract_prepayments(text)
    assert pre["qr"] == 8000.0
    assert payments_sum(pre) == 8000.0


def test_real_sale_message_sample():
    """Типичное сообщение из топика продаж (упрощённый снимок)."""
    text = """
iPhone 16 Pro 256GB Natural (F2LLLLLLL)
ФИО: Петров Пётр
+7 900 111-22-33

Терминал — 95 000
Наличные — 20 000
QR - code — 5 000

Общая сумма — 120 000
""".strip()
    payments = extract_payment_amounts(text, ignore_prepay=True)
    assert payments["terminal"] == 95000.0
    assert payments["cash"] == 20000.0
    assert payments["qr"] == 5000.0
    assert payments_sum(payments) == 120000.0

    recon = reconcile_sale_payments(payments, text, tolerance=50.0)
    assert recon["ok"] is True
    assert recon["declared"] == 120000.0


def test_real_sale_with_installment_and_declared():
    text = """
Samsung S24 Ultra 512 (SN999)
Рассрочка 80 000 12 мес
Нал 15 000
Общая сумма: 95000
""".strip()
    payments = extract_payment_amounts(text)
    assert payments["installment"] == 80000.0
    assert payments["cash"] == 15000.0
    recon = reconcile_sale_payments(payments, text, tolerance=50.0)
    assert recon["ok"] is True
    assert recon["declared"] == 95000.0


def test_declared_total_line_not_counted_as_payment():
    text = "Общая сумма — 50000\nТерминал 50000"
    payments = extract_payment_amounts(text)
    assert payments["terminal"] == 50000.0
    # строка «Общая сумма» сама по себе не добавляет cash/terminal
    assert payments_sum(payments) == 50000.0
