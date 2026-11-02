"""Render non-secret environment placeholders into model definitions."""
import os
import re
from pathlib import Path

root = Path(__file__).resolve().parent
values = {k: os.environ[k] for k in ("DEMO_DATABASE", "DEMO_SCHEMA")}
if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v) for v in values.values()):
    raise ValueError("Database and schema must be simple SQL identifiers")
out = root / "rendered-model"
out.mkdir(exist_ok=True)
for source in (root / "model").iterdir():
    text = source.read_text()
    for key, value in values.items():
        text = text.replace(key, value)
    (out / source.name).write_text(text)
print("Rendered", len(list(out.iterdir())), "model files locally")
