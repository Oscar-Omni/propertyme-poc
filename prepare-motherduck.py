"""Prepare and validate a local upload file; never sign in or execute cloud SQL."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--duckdb", default="duckdb", help="Installed MotherDuck-compatible DuckDB CLI")
parser.add_argument("--database-name", default="propertyme_synthetic_demo")
parser.add_argument("--validate-existing", action="store_true", help="Validate an existing local upload file without modifying it")
args = parser.parse_args()
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.database_name):
    raise ValueError("Database name must be a simple SQL identifier")
manifest = json.loads((root / "manifest.json").read_text())
counts = manifest["row_counts"]
if len(counts) != 16 or sum(counts.values()) != 9252 or manifest["repair_spend_cents"] != 6308589:
    raise ValueError("Unexpected source manifest; inspect before proceeding")
local = root / "motherduck-local.duckdb"
if local.exists() and not args.validate_existing:
    raise FileExistsError("Upload file already exists; inspect it instead of overwriting")
if args.validate_existing and not local.exists():
    raise FileNotFoundError("There is no existing local upload file to validate")
version = subprocess.check_output([args.duckdb, "--version"], text=True).strip()
if not args.validate_existing:
    subprocess.run([args.duckdb, "-bail", str(local), "-f", str(root / "load-duckdb.sql")], check=True)

def query(sql):
    return json.loads(subprocess.check_output(
        [args.duckdb, "-readonly", "-json", str(local), "-c", sql], text=True))

expected = {"PROPERTYME_DEMO_" + name.upper(): n for name, n in counts.items()}
actual_names = {row["table_name"] for row in query(
    "SELECT table_name FROM information_schema.tables WHERE table_schema='main'")}
if actual_names != set(expected):
    raise ValueError("Upload database contains missing or unexpected tables")
for name, count in expected.items():
    result = query(f"SELECT COUNT(*) AS rows, COUNT(*) FILTER (WHERE synthetic_label IS NULL OR synthetic_label != 'ILLUSTRATIVE SYNTHETIC DATA') AS invalid_labels FROM main.{name}")[0]
    if result != {"rows": count, "invalid_labels": 0}:
        raise ValueError((name, result))
sql = (root / "validate-duckdb.sql").read_text().replace("DEMO_DATABASE.DEMO_SCHEMA.", "main.")
checks = query(sql)
if len(checks) != 74 or any(Decimal(str(row["VIOLATIONS"])) != 0 for row in checks):
    raise ValueError("Local validation failed; inspect results")
golden = (root / "golden-queries.sql").read_text().replace("DEMO_DATABASE.DEMO_SCHEMA.", "main.")
for statement in golden.split(";"):
    if statement.strip():
        query(statement)
# CREATE without replacement fails if a destination already exists. Cloud execution
# and its authentication require a separate explicit approval and state inspection.
quoted_path = str(local).replace("'", "''")
(root / "motherduck-upload.sql").write_text(
    "-- PREPARED ONLY. Inspect cloud database names and obtain authentication approval first.\n"
    f"CREATE DATABASE {args.database_name} FROM '{quoted_path}';\n")
report = {"synthetic": True, "cli_version": version, "tables": expected,
          "rows": sum(expected.values()), "repair_spend_cents": 6308589,
          "validation_checks": len(checks), "violations": 0,
          "local_sha256": hashlib.sha256(local.read_bytes()).hexdigest(),
          "cloud_uploaded": False, "connection_created": False}
(root / "motherduck-local-validation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
