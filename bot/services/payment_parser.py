# Файл: bot/services/payment_parser.py
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

PAYMENT_KEYWORDS = {
    'terminal': re.compile(r'Терминал|Терминалом|терминал|терминалом|Terminal|terminal|Терм\.?', re.IGNORECASE),
    'qr': re.compile(r'QR[- ]?код|QRCode|QrCode|QR\s*код|Qrкод|QRCODE|Qrcode|Qrcod|Qr-код|Qr-Код|Qr-code|QR-code', re.IGNORECASE),
    'transfer': re.compile(r'Перевод|перевод|Переводом|переводом|Пер\.?', re.IGNORECASE),
    'invoice': re.compile(r'Оплата по счету|Оплата По Счету|по счету|По счёту|Счёт|Счет|Инвойс', re.IGNORECASE),
    'installment': re.compile(r'Рассрочка|рассрочка|Рассрочкой|рассрочкой|Расср\.?', re.IGNORECASE),
    'cash': re.compile(r'\bНаличными\b|\bНаличные\b|\bналичными\b|\bнал\.?\b|\bнал\b|\bНал\b|\bНаличка\b', re.IGNORECASE),
}
PREPAY_PATTERN = re.compile(r'П[/\\]О|предоплата', re.IGNORECASE)
NUMBER_PATTERN = re.compile(r'(\d[\d\s]*(?:[.,]\d+)?)')
# «24 мес», «12 месяцев», «6 мес.» — не сумма платежа
MONTHS_SPAN_PATTERN = re.compile(
    r'\b\d{1,2}\s*мес(?:яц(?:а|ев)?|\.)?',
    re.IGNORECASE,
)
# «Общая сумма — 697 000», «1. Общая сумма — 697000», «Итого: 100000»
DECLARED_TOTAL_PATTERN = re.compile(
    r'(?:\d+\.\s*)?(?:общая\s*сумма|общая|итого|всего)\s*[:\-—]?\s*([\d\s\u00a0.,]+)',
    re.IGNORECASE,
)


def is_likely_phone_or_serial(num_str: str) -> bool:
    """Проверяет, похоже ли число на телефонный номер или серийный номер."""
    return num_str.isdigit() and len(num_str) >= 10


def _parse_money_token(raw: str) -> float | None:
    num_str = (
        raw.replace(' ', '')
        .replace('\u00a0', '')
        .replace(',', '.')
    )
    # убрать лишние точки-разделители тысяч: 1.234.567 → 1234567
    if num_str.count('.') > 1:
        parts = num_str.split('.')
        if all(len(p) == 3 for p in parts[1:]) and len(parts[-1]) == 3:
            num_str = ''.join(parts)
        else:
            num_str = ''.join(parts[:-1]) + '.' + parts[-1]
    try:
        amount = float(num_str)
    except ValueError:
        return None
    if amount > 10_000_000 or is_likely_phone_or_serial(num_str.replace('.', '')):
        return None
    return amount


def _extract_amounts_from_line(line: str) -> list[float]:
    """Достаёт денежные суммы из строки, игнорируя срок рассрочки (N мес)."""
    cleaned = MONTHS_SPAN_PATTERN.sub(' ', line)
    numbers: list[float] = []
    for match in NUMBER_PATTERN.finditer(cleaned):
        amount = _parse_money_token(match.group(1))
        if amount is None:
            continue
        num_str = match.group(1).replace(' ', '').replace(',', '.')
        # Слишком мелкие «голые» числа (1–31) без копеек чаще даты/срок, не деньги.
        if amount < 50 and '.' not in num_str and amount == int(amount):
            continue
        numbers.append(amount)
    return numbers


def extract_payment_amounts(text: str, ignore_prepay: bool = False) -> dict[str, float]:
    if ignore_prepay:
        lines = [line for line in text.splitlines() if not PREPAY_PATTERN.search(line)]
        text = '\n'.join(lines)

    lines = text.splitlines()
    results = dict.fromkeys(PAYMENT_KEYWORDS, 0.0)

    for line in lines:
        # Строки «Общая сумма» не являются способом оплаты
        if DECLARED_TOTAL_PATTERN.search(line) and not any(
            kw.search(line) for kw in PAYMENT_KEYWORDS.values()
        ):
            continue

        found_types = {pt: kw.search(line) for pt, kw in PAYMENT_KEYWORDS.items()}
        line_pay_types = [pt for pt, match in found_types.items() if match]
        if not line_pay_types:
            continue

        specific_types = [pt for pt in line_pay_types if pt != 'cash']
        if specific_types:
            line_pay_types = specific_types

        numbers = _extract_amounts_from_line(line)
        if not numbers:
            continue

        # Один способ оплаты + несколько чисел → берём максимум (сумма, не «24 мес»).
        if len(line_pay_types) == 1:
            results[line_pay_types[0]] += max(numbers)
            continue

        for i, pt in enumerate(line_pay_types):
            if i < len(numbers):
                results[pt] += numbers[i]
            else:
                break
    return results


def extract_prepayments(text: str) -> dict[str, float]:
    lines = [line for line in text.splitlines() if PREPAY_PATTERN.search(line)]
    if not lines:
        return dict.fromkeys(PAYMENT_KEYWORDS, 0.0)

    prepay_text = '\n'.join(lines)
    return extract_payment_amounts(prepay_text, ignore_prepay=False)


def extract_declared_total(text: str) -> float | None:
    """
    Ищет объявленную «Общую сумму» / «Итого» в тексте продажи.
    Берёт последнее совпадение (часто в конце сообщения).
    """
    found: float | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = DECLARED_TOTAL_PATTERN.search(line)
        if not m:
            continue
        amount = _parse_money_token(m.group(1))
        if amount is not None and amount >= 50:
            found = amount
    return found


def payments_sum(payments: dict[str, float] | None) -> float:
    if not payments:
        return 0.0
    return float(sum(float(v or 0) for v in payments.values()))


def reconcile_sale_payments(
    payments: dict[str, float] | None,
    text: str,
    tolerance: float = 1.0,
) -> dict[str, Any]:
    """
    Сверяет Σ способов оплаты с «Общей суммой» из текста.

    Returns:
        has_declared, ok, paid, declared, diff
    """
    paid = round(payments_sum(payments), 2)
    declared = extract_declared_total(text)
    if declared is None:
        return {
            "has_declared": False,
            "ok": True,
            "paid": paid,
            "declared": None,
            "diff": 0.0,
        }
    declared = round(float(declared), 2)
    diff = round(abs(paid - declared), 2)
    ok = diff <= float(tolerance)
    return {
        "has_declared": True,
        "ok": ok,
        "paid": paid,
        "declared": declared,
        "diff": diff,
    }
