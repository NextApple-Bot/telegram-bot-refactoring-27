"""Samsung Galaxy line normalizer: Model, RAM/STORAGE, Color; Titanium → Ti."""
from __future__ import annotations

import re


def normalize_samsung_galaxy_line(s: str) -> str:
    """
    Samsung Galaxy → «Model, RAM/STORAGE, Color (SERIAL) …».
    Titanium * → Ti *; порядок: модель, память, цвет.
    """
    tails: list[str] = []
    body = s.rstrip()

    while True:
        m = re.search(r"(\s*\([^()]{1,100}\))\s*$", body)
        if not m:
            break
        tails.insert(0, m.group(1).strip())
        body = body[: m.start()].rstrip()

    body = re.sub(r"\bTitanium\s+Black\b", "Ti Black", body, flags=re.IGNORECASE)
    body = re.sub(r"\bTi\s*Black\b", "Ti Black", body, flags=re.IGNORECASE)
    body = re.sub(r"\bTitanium\s+Gr(?:a|e)y\b", "Ti Gray", body, flags=re.IGNORECASE)
    body = re.sub(r"\bTi\s*Gr(?:a|e)y\b", "Ti Gray", body, flags=re.IGNORECASE)
    body = re.sub(r"\bTiGray\b", "Ti Gray", body, flags=re.IGNORECASE)
    body = re.sub(r"\bTitanium\s+Whitesilver\b", "Ti Whitesilver", body, flags=re.IGNORECASE)
    body = re.sub(r"\bTi\s*Whitesilver\b", "Ti Whitesilver", body, flags=re.IGNORECASE)
    body = re.sub(r"\bTitanium\s+Silver\s*blue\b", "Ti Silverblue", body, flags=re.IGNORECASE)
    body = re.sub(r"\bTitanium\s+Silverblue\b", "Ti Silverblue", body, flags=re.IGNORECASE)
    body = re.sub(r"\bTi\s*Silverblue\b", "Ti Silverblue", body, flags=re.IGNORECASE)
    body = re.sub(r"\bTitanium\s+([A-Za-z]+)\b", r"Ti \1", body, flags=re.IGNORECASE)
    body = re.sub(r"\bTi([A-Z][a-z]+)\b", r"Ti \1", body)

    m_model = re.match(
        r"^(Samsung\s+Galaxy\s+"
        r"(?:"
        r"S\d+\s*Ultra|S\d+\s*FE|S\d+\+|S\d+|"
        r"Z\s*Fold\s*\d+|Z\s*Flip\s*\d+|A\d+"
        r"))\b",
        body,
        flags=re.IGNORECASE,
    )
    if not m_model:
        out = body
        if tails:
            out = out + " " + " ".join(tails)
        return out.strip()

    model = re.sub(r"\s+", " ", m_model.group(1)).strip()
    model = re.sub(r"\bZ\s*Fold\s*(\d+)\b", r"Z Fold \1", model, flags=re.IGNORECASE)
    model = re.sub(r"\bZ\s*Flip\s*(\d+)\b", r"Z Flip \1", model, flags=re.IGNORECASE)
    model = re.sub(r"\bS(\d+)\s*Ultra\b", r"S\1 Ultra", model, flags=re.IGNORECASE)
    model = re.sub(r"\bS(\d+)\s*FE\b", r"S\1 FE", model, flags=re.IGNORECASE)
    rest_body = body[m_model.end() :].strip(" ,;-")

    mem = None
    m_pair = re.search(
        r"\b(\d+)\s*/\s*(\d+(?:[.,]\d+)?)\s*(GB|TB|ГБ|ТБ)\b",
        rest_body,
        flags=re.IGNORECASE,
    )
    if m_pair:
        unit = m_pair.group(3).upper().replace("ГБ", "GB").replace("ТБ", "TB")
        num = m_pair.group(2).replace(",", ".")
        try:
            f = float(num)
            num = str(int(f)) if f == int(f) else num
        except ValueError:
            pass
        mem = f"{m_pair.group(1)}/{num}{unit}"
        rest_body = (rest_body[: m_pair.start()] + " " + rest_body[m_pair.end() :]).strip()

    rest_body = re.sub(
        r"\b\d+(?:[.,]\d+)?\s*(?:GB|TB|ГБ|ТБ)\b",
        " ",
        rest_body,
        flags=re.IGNORECASE,
    )
    rest_body = re.sub(r"\s+", " ", rest_body).strip(" ,;-")
    color = re.sub(r"\s*,\s*", " ", rest_body).strip() if rest_body else ""
    color = re.sub(r"\s+", " ", color)

    parts = [model]
    if mem:
        parts.append(mem)
    if color:
        parts.append(color)
    out = ", ".join(parts)
    if tails:
        out = out + " " + " ".join(tails)
    return out.strip()
