"""Build an illustrative inspection-to-repair dataset. No customer data."""
import csv
import datetime as dt
import hashlib
import json
import random
import os
import re
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
CUTOFF = dt.datetime(2026, 10, 31, 23, 59, 59)
START = dt.datetime(2024, 11, 1)
PREFIX = "PROPERTYME_DEMO_"
DATABASE = os.environ.get("DEMO_DATABASE", "DEMO_DATABASE")
SCHEMA = os.environ.get("DEMO_SCHEMA", "DEMO_SCHEMA")
if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x) for x in (DATABASE, SCHEMA)):
    raise ValueError("Use simple SQL identifiers for DEMO_DATABASE and DEMO_SCHEMA")
rng = random.Random(68542)
tables = {}


def table(name, columns, rows):
    columns = [("synthetic_label", "VARCHAR"), *columns]
    rows = [("ILLUSTRATIVE SYNTHETIC DATA", *r) for r in rows]
    tables[name] = {"columns": columns, "rows": rows}


def agency(n):
    return (n - 1) % 3 + 1


def manager(prop):
    portfolio_index = (prop - 1) // 3
    group = 0 if portfolio_index < 30 else 1 if portfolio_index < 45 else 2 if portfolio_index < 55 else 3
    return agency(prop) + 3 * group


table("agencies", [("agency_id", "INTEGER"), ("agency_name", "VARCHAR")],
      [(i, f"Illustrative Agency {i}") for i in range(1, 4)])
table("managers", [("agency_id", "INTEGER"), ("manager_id", "INTEGER"), ("manager_name", "VARCHAR")],
      [(agency(i), i, f"Synthetic Manager {i:02}") for i in range(1, 13)])
table("properties", [("agency_id", "INTEGER"), ("property_id", "INTEGER"), ("manager_id", "INTEGER"),
                     ("property_label", "VARCHAR"), ("state", "VARCHAR")],
      [(agency(i), i, manager(i), f"Synthetic Property {i:03}",
        ["NSW", "VIC", "QLD"][agency(i) - 1]) for i in range(1, 181)])
table("tenancies", [("agency_id", "INTEGER"), ("tenancy_id", "INTEGER"), ("property_id", "INTEGER"),
                    ("starts_at", "TIMESTAMP"), ("ends_at", "TIMESTAMP")],
      [(agency(i), i, i, START, None) for i in range(1, 181)])
table("suppliers", [("agency_id", "INTEGER"), ("supplier_id", "INTEGER"), ("supplier_name", "VARCHAR")],
      [(agency(i), i, f"Synthetic Supplier {i:02}") for i in range(1, 25)])
inspections = []
for i in range(1, 1081):
    prop = (i - 1) % 180 + 1
    when = START + dt.timedelta(days=20 + ((i - 1) // 180) * 132 + prop % 30)
    inspections.append((agency(prop), i, prop, prop, manager(prop),
                        when, when + dt.timedelta(hours=1), "routine"))
table("inspections", [("agency_id", "INTEGER"), ("inspection_id", "INTEGER"), ("property_id", "INTEGER"),
                      ("tenancy_id", "INTEGER"), ("manager_id", "INTEGER"), ("scheduled_at", "TIMESTAMP"),
                      ("completed_at", "TIMESTAMP"), ("inspection_type", "VARCHAR")], inspections)
findings = []
for i in range(1, 1621):
    ins = inspections[(i - 1) % len(inspections)]
    findings.append((ins[0], i, ins[1], ins[2], ["plumbing", "electrical", "general"][(i // 3) % 3],
                     "urgent" if i % 7 == 0 else "routine", ins[6]))
table("findings", [("agency_id", "INTEGER"), ("finding_id", "INTEGER"), ("inspection_id", "INTEGER"),
                   ("property_id", "INTEGER"), ("category", "VARCHAR"), ("priority", "VARCHAR"),
                   ("found_at", "TIMESTAMP")], findings)
jobs, quotes, orders, events, bills, lines = [], [], [], [], [], []
for i in range(1, 601):
    f = findings[((i - 1) * 7) % len(findings)]
    a, finding, inspection, prop, category, priority, found = f
    created = found + dt.timedelta(hours=2)
    state = ["awaiting_approval", "completed", "completed", "completed", "in_progress"][i % 5]
    if state == "awaiting_approval":
        created = max(created, CUTOFF - dt.timedelta(days=30 + i % 50 if a == 1 else 8 + i % 20))
    approved = None if state == "awaiting_approval" else created + dt.timedelta(hours=12 + i % 48)
    completed = approved + dt.timedelta(hours=24 + i % 96) if state == "completed" else None
    supplier = a + 3 * (i % 8)
    target_hours = 24 if priority == "urgent" else 72
    jobs.append((a, i, prop, inspection, finding, supplier, category, priority, state,
                 created, approved, completed, target_hours))
    events.append((a, len(events) + 1, i, "created", created))
    if approved:
        events.append((a, len(events) + 1, i, "approved", approved))
        orders.append((a, len(orders) + 1, i, supplier, approved, completed))
    if completed:
        events.append((a, len(events) + 1, i, "completed", completed))
    for q in range(1 + (i % 2)):
        quotes.append((a, len(quotes) + 1, i, a + 3 * ((i + q) % 8),
                       created + dt.timedelta(hours=2 + q), 10000 + i * 31 + q * 1700,
                       bool(approved and q == 0)))
    if completed and i % 11 != 0:
        bid = len(bills) + 1
        cents = 10000 + i * 31
        part = cents // 3
        bills.append((a, bid, i, supplier, completed + dt.timedelta(days=1), cents, "AUD"))
        for amount, desc in [(part, "materials"), (cents - part, "labour")]:
            lines.append((a, len(lines) + 1, bid, i, desc, amount))
table("maintenance_jobs", [("agency_id", "INTEGER"), ("job_id", "INTEGER"), ("property_id", "INTEGER"),
                           ("inspection_id", "INTEGER"), ("finding_id", "INTEGER"), ("supplier_id", "INTEGER"),
                           ("category", "VARCHAR"), ("priority", "VARCHAR"), ("status", "VARCHAR"),
                           ("created_at", "TIMESTAMP"), ("approved_at", "TIMESTAMP"), ("completed_at", "TIMESTAMP"),
                           ("illustrative_target_hours", "INTEGER")], jobs)
table("quotes", [("agency_id", "INTEGER"), ("quote_id", "INTEGER"), ("job_id", "INTEGER"),
                 ("supplier_id", "INTEGER"), ("quoted_at", "TIMESTAMP"), ("quote_cents", "INTEGER"),
                 ("accepted", "BOOLEAN")], quotes)
table("work_orders", [("agency_id", "INTEGER"), ("work_order_id", "INTEGER"), ("job_id", "INTEGER"),
                      ("supplier_id", "INTEGER"), ("issued_at", "TIMESTAMP"), ("completed_at", "TIMESTAMP")], orders)
table("status_events", [("agency_id", "INTEGER"), ("event_id", "INTEGER"), ("job_id", "INTEGER"),
                        ("status", "VARCHAR"), ("occurred_at", "TIMESTAMP")], events)
table("bills", [("agency_id", "INTEGER"), ("bill_id", "INTEGER"), ("job_id", "INTEGER"),
                ("supplier_id", "INTEGER"), ("billed_at", "TIMESTAMP"), ("total_cents", "INTEGER"),
                ("currency", "VARCHAR")], bills)
table("bill_lines", [("agency_id", "INTEGER"), ("bill_line_id", "INTEGER"), ("bill_id", "INTEGER"),
                     ("job_id", "INTEGER"), ("line_type", "VARCHAR"), ("amount_cents", "INTEGER")], lines)

(ROOT / "data").mkdir(exist_ok=True)
con = duckdb.connect(str(ROOT / "propertyme_synthetic.duckdb"))
for name, t in tables.items():
    con.execute(f"CREATE OR REPLACE TABLE {name} ({','.join(n+' '+ty for n,ty in t['columns'])})")
    con.executemany(f"INSERT INTO {name} VALUES ({','.join('?' for _ in t['columns'])})", t['rows'])

job_sql = """SELECT j.*, p.manager_id, a.agency_name, s.supplier_name,
coalesce(b.repair_spend_cents,0) AS repair_spend_cents, coalesce(b.bill_count,0) AS bill_count,
coalesce(q.quote_count,0) AS quote_count,
date_diff('hour',j.created_at,TIMESTAMP '2026-10-31 23:59:59') AS age_at_cutoff_hours,
CASE WHEN j.completed_at IS NOT NULL THEN date_diff('hour',j.created_at,j.completed_at) END AS completed_cycle_hours,
CASE WHEN j.approved_at IS NOT NULL THEN date_diff('hour',j.created_at,j.approved_at) END AS approval_hours,
CASE WHEN j.completed_at IS NOT NULL AND coalesce(b.bill_count,0)=0 THEN 1 ELSE 0 END AS missing_invoice,
CASE WHEN count(*) OVER(PARTITION BY j.agency_id,j.property_id,j.category)>1 THEN 1 ELSE 0 END AS repeat_repair
FROM maintenance_jobs j
JOIN properties p ON p.agency_id=j.agency_id AND p.property_id=j.property_id
JOIN agencies a ON a.agency_id=j.agency_id
JOIN suppliers s ON s.agency_id=j.agency_id AND s.supplier_id=j.supplier_id
LEFT JOIN (SELECT agency_id,job_id,sum(total_cents) repair_spend_cents,count(*) bill_count FROM bills GROUP BY 1,2) b
ON b.agency_id=j.agency_id AND b.job_id=j.job_id
LEFT JOIN (SELECT agency_id,job_id,count(*) quote_count FROM quotes GROUP BY 1,2) q
ON q.agency_id=j.agency_id AND q.job_id=j.job_id"""
inspection_sql = """SELECT i.*, coalesce(f.finding_count,0) finding_count,coalesce(j.job_count,0) job_count,
coalesce(j.repair_spend_cents,0) repair_spend_cents FROM inspections i
LEFT JOIN (SELECT agency_id,inspection_id,count(*) finding_count FROM findings GROUP BY 1,2) f
ON i.agency_id=f.agency_id AND i.inspection_id=f.inspection_id
LEFT JOIN (SELECT agency_id,inspection_id,count(*) job_count,sum(repair_spend_cents) repair_spend_cents FROM mart_jobs GROUP BY 1,2) j
ON i.agency_id=j.agency_id AND i.inspection_id=j.inspection_id"""
month_sql = """WITH months AS (SELECT CAST(month_start AS DATE) month_start FROM generate_series(TIMESTAMP '2024-11-01',TIMESTAMP '2026-10-01',INTERVAL '1 month') t(month_start)),
rollup AS (SELECT agency_id,CAST(date_trunc('month',created_at) AS DATE) month_start,count(*) jobs_created,
sum(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed_jobs,sum(repair_spend_cents) repair_spend_cents,
sum(CASE WHEN status!='completed' THEN 1 ELSE 0 END) open_jobs FROM mart_jobs GROUP BY 1,2)
SELECT a.synthetic_label,a.agency_id,m.month_start,coalesce(r.jobs_created,0) jobs_created,
coalesce(r.completed_jobs,0) completed_jobs,coalesce(r.repair_spend_cents,0) repair_spend_cents,
coalesce(r.open_jobs,0) open_jobs,p.properties_managed,coalesce(r.jobs_created,0)*100.0/p.properties_managed jobs_per_100_properties
FROM agencies a CROSS JOIN months m JOIN (SELECT agency_id,count(*) properties_managed FROM properties GROUP BY 1) p ON p.agency_id=a.agency_id
LEFT JOIN rollup r ON r.agency_id=a.agency_id AND r.month_start=m.month_start"""
for name, sql in [("mart_jobs", job_sql), ("mart_inspections", inspection_sql), ("mart_agency_month", month_sql)]:
    con.execute(f"CREATE OR REPLACE TABLE {name} AS {sql}")
    cols = [(r[0],r[1]) for r in con.execute(f"DESCRIBE {name}").fetchall()]
    tables[name] = {"columns": cols, "rows": con.execute(f"SELECT * FROM {name}").fetchall()}

checks = []
def zero(label, sql):
    count = con.execute(sql).fetchone()[0]
    assert count == 0, (label, count)
    checks.append({"check":label,"violations":count,"sql":sql})

keys = {"agencies":"agency_id","managers":"manager_id","properties":"property_id","tenancies":"tenancy_id",
        "suppliers":"supplier_id","inspections":"inspection_id","findings":"finding_id","maintenance_jobs":"job_id",
        "quotes":"quote_id","work_orders":"work_order_id","status_events":"event_id","bills":"bill_id","bill_lines":"bill_line_id"}
for name,key in keys.items():
    zero(name+" unique key", f"SELECT count(*)-count(DISTINCT {key}) FROM {name}")
    zero(name+" agency", f"SELECT count(*) FROM {name} t LEFT JOIN agencies a USING(agency_id) WHERE a.agency_id IS NULL")
relationships = [("properties","managers","manager_id"),("tenancies","properties","property_id"),
                 ("inspections","properties","property_id"),("inspections","managers","manager_id"),
                 ("inspections","tenancies","tenancy_id"),("findings","inspections","inspection_id"),
                 ("maintenance_jobs","properties","property_id"),("maintenance_jobs","inspections","inspection_id"),
                 ("maintenance_jobs","findings","finding_id"),("maintenance_jobs","suppliers","supplier_id"),
                 ("quotes","maintenance_jobs","job_id"),("quotes","suppliers","supplier_id"),
                 ("work_orders","maintenance_jobs","job_id"),("work_orders","suppliers","supplier_id"),
                 ("status_events","maintenance_jobs","job_id"),("bills","maintenance_jobs","job_id"),
                 ("bills","suppliers","supplier_id"),("bill_lines","bills","bill_id"),("bill_lines","maintenance_jobs","job_id")]
for child,parent,key in relationships:
    zero(f"{child}->{parent} no orphan/cross-agency",f"SELECT count(*) FROM {child} c LEFT JOIN {parent} p ON c.agency_id=p.agency_id AND c.{key}=p.{key} WHERE p.{key} IS NULL")
zero("bill reconciliation", "SELECT count(*) FROM bills b JOIN (SELECT agency_id,bill_id,sum(amount_cents) n FROM bill_lines GROUP BY 1,2) l USING(agency_id,bill_id) WHERE b.total_cents<>l.n")
zero("job dates ordered", "SELECT count(*) FROM maintenance_jobs j JOIN findings f USING(agency_id,finding_id) WHERE j.created_at<f.found_at OR j.approved_at<j.created_at OR j.completed_at<j.approved_at OR j.completed_at>TIMESTAMP '2026-10-31 23:59:59'")
zero("open stages null", "SELECT count(*) FROM maintenance_jobs WHERE (status!='completed' AND completed_at IS NOT NULL) OR (status='awaiting_approval' AND approved_at IS NOT NULL)")
zero("job/finding/property consistency", "SELECT count(*) FROM maintenance_jobs j JOIN findings f USING(agency_id,finding_id) WHERE j.property_id<>f.property_id OR j.inspection_id<>f.inspection_id")
zero("quote timestamps", "SELECT count(*) FROM quotes q JOIN maintenance_jobs j USING(agency_id,job_id) WHERE q.quoted_at<j.created_at OR (q.accepted AND q.quoted_at>j.approved_at)")
zero("event timestamps", "SELECT count(*) FROM status_events e JOIN maintenance_jobs j USING(agency_id,job_id) WHERE e.occurred_at<j.created_at OR e.occurred_at>TIMESTAMP '2026-10-31 23:59:59'")
zero("bill timestamps", "SELECT count(*) FROM bills b JOIN maintenance_jobs j USING(agency_id,job_id) WHERE b.billed_at<j.completed_at OR b.billed_at>TIMESTAMP '2026-10-31 23:59:59' OR j.completed_at IS NULL")
zero("job mart grain", "SELECT count(*)-count(DISTINCT job_id) FROM mart_jobs")
zero("inspection mart grain", "SELECT count(*)-count(DISTINCT inspection_id) FROM mart_inspections")
cost = con.execute("SELECT sum(total_cents) FROM bills").fetchone()[0]
for name in ["mart_jobs","mart_inspections","mart_agency_month"]:
    assert con.execute(f"SELECT sum(repair_spend_cents) FROM {name}").fetchone()[0] == cost
    checks.append({"check":name+" exact repair-spend invariance","cents":cost})
assert con.execute("SELECT count(*) FROM mart_jobs WHERE missing_invoice=1").fetchone()[0]>0
assert con.execute("SELECT count(*) FROM mart_jobs WHERE quote_count>1").fetchone()[0]>0
assert con.execute("SELECT count(*) FROM mart_jobs WHERE repeat_repair=1").fetchone()[0]>0

def literal(value):
    if value is None:return "NULL"
    if isinstance(value,bool):return "TRUE" if value else "FALSE"
    if isinstance(value,(int,float)):return str(value)
    return "'"+str(value).replace("'","''")+"'"

ddl = []
for name,t in tables.items():
    filename = ROOT / "data" / (name+".csv")
    with filename.open('w') as f:
        w=csv.writer(f);w.writerow([n for n,_ in t['columns']]);w.writerows(t['rows'])
    full = DATABASE+"."+SCHEMA+"."+PREFIX+name.upper()
    ddl.append(f"CREATE TABLE {full} ({','.join(n.upper()+' '+('NUMBER(38,0)' if ty=='HUGEINT' else ty) for n,ty in t['columns'])}) COMMENT='Illustrative synthetic inspection-to-repair demo; seed 68542; cutoff 2026-10-31; no customer data';")
    for start in range(0,len(t['rows']),200):
        ddl.append(f"INSERT INTO {full} VALUES "+','.join('('+','.join(literal(v) for v in row)+')' for row in t['rows'][start:start+200])+';')
(ROOT / "load.sql").write_text('\n'.join(ddl))
manifest = {"synthetic":True,"confirmed_customer_requirements":False,"seed":68542,"cutoff":CUTOFF.isoformat(),"start":START.isoformat(),
            "namespace":DATABASE+"."+SCHEMA+"."+PREFIX,"row_counts":{n:len(t['rows']) for n,t in tables.items()},
            "repair_spend_cents":cost,"currency":"AUD","checks":checks,
            "load_sha256":hashlib.sha256((ROOT/'load.sql').read_bytes()).hexdigest()}
(ROOT / "manifest.json").write_text(json.dumps(manifest,indent=2))
print(json.dumps({k:v for k,v in manifest.items() if k!='checks'},indent=2));print(len(checks),'checks passed')
