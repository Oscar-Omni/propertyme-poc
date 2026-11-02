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

The generator produces a local DuckDB, CSV files, a validation manifest and Snowflake load.sql. It runs 57 checks on unique keys, agency relationships, chronology, incomplete stages, bill-line reconciliation and exact spend invariance before emitting load SQL.

## Load and model

Use an authorized Snowflake connection with access to an isolated demonstration namespace. Review load.sql and verify the PROPERTYME_DEMO_ prefix does not already exist. SQL uses CREATE TABLE rather than replacing existing objects. Do not blindly replay a partial load; inspect existing object counts and finish only missing work. This repository neither creates credentials nor grants access.

Run the reviewed SQL through your approved Snowflake client. The six files in rendered-model are Omni view/topic definitions. Create a model branch, author through the supported YAML API, validate, and query all three marts before any explicit merge decision. Do not hand-edit a git-connected model behind Omni.

The model templates use DEMO_DATABASE and DEMO_SCHEMA placeholders; no environment account, connection, organization, model or credential identifiers are included. golden-queries.sql uses the same placeholders. Replace them locally before running.

## Evaluation

Compare counts and repair spend across the job, inspection and agency-month marts. Separate approval delay from completed cycle time and open age. Normalize jobs by properties managed before comparing manager workload. Keep accepted quotes separate from invoiced spend.

The AI context requests clarification of ambiguous metrics such as worst contractor before querying. Context is guidance, not a guarantee; verify actual behavior and retain failing cases. Role isolation, model promotion and performance should be tested separately in your approved environment.

## Git integration

This repository is a public source artifact. It does not itself grant an Omni instance GitHub access. Connect only an approved model path and repository-scoped integration after reviewing its requested permissions. Publish model/setup code only; keep credentials, generated data, customer notes, transcripts and internal material out of this repository.
