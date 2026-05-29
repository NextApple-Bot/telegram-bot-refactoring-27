# Файл: bot/utils/validators.py
import re


def extract_serials(text: str) -> list[str]:
    if not isinstance(text, str):
        return []
    serials = set()
    matches = re.finditer(r'\(([^)]+)\)', text)
    for match in matches:
        candidate = match.group(1).strip()
        if not candidate:
            continue
        if '№' in candidate or re.fullmatch(r'[A-Za-z0-9]{5,30}', candidate):
            serials.add(candidate.upper())
        elif candidate.isdigit() and len(candidate) >= 10:
            serials.add(candidate)
        elif '-' in candidate and re.fullmatch(r'[A-Za-z0-9\-]{5,30}', candidate):
            serials.add(candidate.upper())
    return list(serials)

def normalize_serial(serial: str) -> str:
    if not serial:
        return ""
    return re.sub(r'\s+', '', serial).upper()
