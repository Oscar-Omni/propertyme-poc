# PropertyMe synthetic inspection-to-repair demo

Illustrative synthetic demo model and setup code. This is not PropertyMe customer data, its actual database schema, or confirmed evaluation requirements. Names are fictional and no real PII is included.

The public product context is property management, inspections and maintenance. Sources: https://www.propertyme.com.au/manage-pm and https://www.propertyme.com.au/features .

## Dataset

Fixed seed 68542. Horizon 1 November 2024 through 31 October 2026. All rows are labeled ILLUSTRATIVE SYNTHETIC DATA. Agency means the fictional SaaS tenant; tenancy means renter occupancy. Repair spend is AUD invoiced repair expenditure, not vendor revenue or agency profit. Target hours are illustrative policy, not legal obligations or customer SLAs.

The generator creates 13 source tables with 7,500 rows, plus three marts with 1,752 rows. It includes 180 properties, 1,080 inspections, 1,620 findings, 600 jobs, 900 quotes and 327 bills. Synthetic repair spend totals AUD 63,085.89. There are 33 completed jobs without invoices. Other scenarios cover approval delay, repeated repairs, multiple quotes/bill lines, unequal manager portfolios, and open-job ageing versus completed averages.

Marts have job, inspection and agency-month grains. Child records are aggregated before joining to avoid fanout. Source relationships include agency_id. These keys help validate boundaries; they do not implement row-level access controls.

## Generate locally

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DEMO_DATABASE=YOUR_DEMO_DATABASE
export DEMO_SCHEMA=YOUR_ISOLATED_SCHEMA
python generate.py
python render-model.py
```

The generator produces a local DuckDB, CSV files, a validation manifest, portable DuckDB load SQL, and an optional Snowflake load.sql. It runs 57 checks on unique keys, agency relationships, chronology, incomplete stages, bill-line reconciliation and exact spend invariance before emitting load SQL. Generated files stay local and are excluded from Git.

## Prepare for MotherDuck

Use an already installed MotherDuck-compatible DuckDB CLI. A newer Python DuckDB can write a storage version that the cloud-compatible CLI cannot open. The preparation script rebuilds a separate upload file using that CLI, without modifying the generator's database:

```sh
python prepare-motherduck.py --duckdb /path/to/installed/duckdb --database-name YOUR_ISOLATED_DEMO_DATABASE
```

It creates motherduck-local.duckdb with exactly 16 PROPERTYME_DEMO_ tables, checks all row labels and counts, runs 74 zero-violation checks and six golden SQL queries, and writes a local validation report. It refuses to overwrite an existing upload database. To inspect a previous preparation without changing its data, add --validate-existing. If preparation fails, inspect the existing file and error before any retry.

motherduck-upload.sql contains one CREATE DATABASE ... FROM statement using the local file. It is prepared only: the script does not sign in, create tokens, attach MotherDuck, upload data, or grant access. After separate authentication approval and inspection of existing cloud databases, use the supported DuckDB/MotherDuck workflow to run that statement. It intentionally omits OR REPLACE and IF NOT EXISTS so a duplicate destination fails. Do not replay an uncertain cloud outcome; inspect the destination first.

Use only the dedicated demonstration database and main schema in Omni. Leave other databases and upload schemas empty and select No Access as base member access. These connection settings constrain discovery; they do not reduce permissions granted to the authentication identity. Omni's documented MotherDuck setup uses an access token, so review the identity, actual token scope, expiry and destination before entering a credential. Do not assume an unrelated warehouse approval applies.

After cloud upload, rerun validate-duckdb.sql and the golden queries against the actual target, confirm exactly 16 tables and 9,252 rows, and reconcile all three marts to AUD 63,085.89. Local validation is not proof of a remote load or Omni connection.

Sources: [MotherDuck database import](https://motherduck.com/docs/sql-reference/motherduck-sql-reference/create-database/), [Omni MotherDuck setup](https://docs.omni.co/connect-data/setup/motherduck).

## Model

The six files in rendered-model are Omni view/topic definitions. Set DEMO_DATABASE to the actual approved dedicated database and DEMO_SCHEMA to main, then render locally. The query-view SQL uses portable selections and integer repair cents. Create a model branch, author through the supported YAML API, validate, and query all three marts before any explicit merge decision. Do not hand-edit a git-connected model behind Omni.

The model templates use DEMO_DATABASE and DEMO_SCHEMA placeholders; no environment account, connection, organization, model or credential identifiers are included. golden-queries.sql uses the same placeholders. Replace them locally before running.

## Evaluation

Compare counts and repair spend across the job, inspection and agency-month marts. Separate approval delay from completed cycle time and open age. Normalize jobs by properties managed before comparing manager workload. Keep accepted quotes separate from invoiced spend.

The AI context requests clarification of ambiguous metrics such as worst contractor before querying. Context is guidance, not a guarantee; verify actual behavior and retain failing cases. Role isolation, model promotion and performance should be tested separately in your approved environment.

## Git integration

This repository is a public source artifact. It does not itself grant an Omni instance GitHub access. Connect only an approved model path and repository-scoped integration after reviewing its requested permissions. Publish model/setup code only; keep credentials, generated data, customer notes, transcripts and internal material out of this repository.
