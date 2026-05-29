# Файл: bot/services/payment_parser.py
import logging
import re

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


def is_likely_phone_or_serial(num_str: str) -> bool:
    """Проверяет, похоже ли число на телефонный номер или серийный номер."""
    return num_str.isdigit() and len(num_str) >= 10


def extract_payment_amounts(text: str, ignore_prepay: bool = False) -> dict[str, float]:
    if ignore_prepay:
        lines = [line for line in text.splitlines() if not PREPAY_PATTERN.search(line)]
        text = '\n'.join(lines)

    lines = text.splitlines()
    results = dict.fromkeys(PAYMENT_KEYWORDS, 0.0)

    for line in lines:
        found_types = {pt: kw.search(line) for pt, kw in PAYMENT_KEYWORDS.items()}
        line_pay_types = [pt for pt, match in found_types.items() if match]
        if not line_pay_types:
            continue

        specific_types = [pt for pt in line_pay_types if pt != 'cash']
        if specific_types:
            line_pay_types = specific_types

        numbers = []
        for match in NUMBER_PATTERN.finditer(line):
            num_str = match.group(1).replace(' ', '').replace(',', '.')
            try:
                amount = float(num_str)
            except ValueError:
                continue
            if amount > 10_000_000 or is_likely_phone_or_serial(num_str):
                continue
            numbers.append(amount)

        if not numbers:
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
