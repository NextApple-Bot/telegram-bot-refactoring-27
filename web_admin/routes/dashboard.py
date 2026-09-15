"""Dashboard routes — restored via multipart load."""
from pathlib import Path
_p = Path(__file__).resolve().parent
_code = "".join((_p / f"dq{i}.py").read_text(encoding="utf-8") for i in range(21))
exec(_code, globals())
