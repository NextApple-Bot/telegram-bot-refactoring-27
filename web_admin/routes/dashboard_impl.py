"""Dashboard route implementation (split restore)."""
from pathlib import Path

_p = Path(__file__).resolve().parent
_code = (
    (_p / "_dash_a.py").read_text(encoding="utf-8")
    + (_p / "_dash_b.py").read_text(encoding="utf-8")
    + (_p / "_dash_c.py").read_text(encoding="utf-8")
)
exec(_code, globals())
