"""Dashboard routes (multipart restore)."""
from pathlib import Path
_p = Path(__file__).resolve().parent
_code = "".join((_p / f"_d{i}.py").read_text(encoding="utf-8") for i in range(8))
exec(_code, globals())
