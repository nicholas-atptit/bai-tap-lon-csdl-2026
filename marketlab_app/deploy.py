"""Create / migrate MarketLab databases WITHOUT touching the public demo or the research database.

python -m marketlab_app.deploy ops-db
python -m marketlab_app.deploy live-db --database MarketLabVN30_Live --universe-csv <csv> --observed-through 2026-09-30
python -m marketlab_app.deploy preflight --database <db>
python -m marketlab_app.deploy migrate --database <db> --confirm-backup <path-to-.bak>   (existing DB with data)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .config import ROOT, ConfigError, Settings, load_settings
from .db import connect, query

PROTECTED = {"MarketLabVN30_Demo"}
SAFE_NAME = re.compile(r"^MarketLabVN30_[A-Za-z0-9_]{1,80}$")
SCHEMA_FILES = ["00_create_database.sql", "01_create_tables.sql", "02_constraints_indexes.sql",
                "04_functions.sql", "05_views.sql", "06_stored_procedures.sql"]


class DeployError(RuntimeError):
    pass


def check_new_name(name: str) -> None:
    if not SAFE_NAME.match(name) or name in PROTECTED or name.startswith("MarketLabVN30_Research"):
        raise DeployError(f"Refusing database name {name!r}: must match MarketLabVN30_<name>, not demo/research")


def run_sqlcmd(settings: Settings, script: Path, database: str, variables: dict[str, str] | None = None,
               log: Path | None = None) -> str:
    cmd = ["sqlcmd", "-S", settings.sql_server, "-C", "-b", "-f", "65001", "-W", "-s", "|", "-l",
           str(settings.sql_login_timeout), "-d", database, "-i", str(script)]
    env = dict(os.environ)
    if settings.sql_auth == "sql":
        cmd += ["-U", settings.sql_user]
        env["SQLCMDPASSWORD"] = settings.sql_password  # not on the command line
    else:
        cmd.append("-E")
    for k, v in (variables or {}).items():
        cmd += ["-v", f"{k}={v}"]
    p = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", env=env)
    out = (p.stdout or "") + (p.stderr or "")
    if settings.sql_password:
        out = out.replace(settings.sql_password, "***")
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(out, encoding="utf-8")
    if p.returncode != 0:
        raise DeployError(f"sqlcmd failed ({script.name} on {database}, exit {p.returncode}):\n{out[-3000:]}")
    return out


def database_exists(settings: Settings, name: str) -> bool:
    with connect(settings, "master") as c:
        return bool(query(c, "SELECT 1 AS x FROM sys.databases WHERE name=?", (name,)))


def create_database(settings: Settings, name: str, purpose: str) -> bool:
    """Create an empty database tagged with MarketLabPurpose. Returns False if it already existed (and is ours)."""
    check_new_name(name)
    with connect(settings, "master") as c:
        if query(c, "SELECT 1 AS x FROM sys.databases WHERE name=?", (name,)):
            with connect(settings, name) as d:
                tag = query(d, "SELECT CONVERT(nvarchar(100),value) AS v FROM sys.extended_properties WHERE class=0 AND name=N'MarketLabPurpose'")
                tables = query(d, "SELECT COUNT(*) AS n FROM sys.tables WHERE is_ms_shipped=0")[0]["n"]
            if not tag and tables:
                raise DeployError(f"{name} exists, has tables and is not tagged as a MarketLab database; refusing")
            return False
        c.cursor().execute(f"CREATE DATABASE [{name}]")
    with connect(settings, name) as d:
        d.cursor().execute("EXEC sys.sp_addextendedproperty @name=N'MarketLabPurpose', @value=?", purpose)
    return True


def render_schema(name: str) -> str:
    check_new_name(name)
    parts = []
    for f in SCHEMA_FILES:
        text = (ROOT / "sql" / f).read_text(encoding="utf-8-sig")
        parts.append(f"-- FILE: {f} (database name substituted: {name})\n" + text.replace("MarketLabVN30_Demo", name))
    return "\n".join(parts) + "\nSET NOEXEC OFF;\nGO\n"


def deploy_business_schema(settings: Settings, name: str, workdir: Path) -> Path:
    script = workdir / f"schema_{name}.sql"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(render_schema(name), encoding="utf-8-sig")
    run_sqlcmd(settings, script, "master", log=workdir / f"schema_{name}.log")
    return script


def apply_eod_extension(settings: Settings, name: str, workdir: Path) -> str:
    if name in PROTECTED:
        raise DeployError("The public synthetic demo never receives the EOD extension")
    return run_sqlcmd(settings, ROOT / "sql" / "13_eod_extension.sql", name, log=workdir / f"eod_extension_{name}.log")


def deploy_ops_db(settings: Settings, name: str, workdir: Path) -> str:
    create_database(settings, name, "OPS")
    out = run_sqlcmd(settings, ROOT / "sql" / "14_ops_database.sql", name, log=workdir / f"ops_schema_{name}.log")
    return out + run_sqlcmd(settings, ROOT / "sql" / "15_ops_schema_v2.sql", name, log=workdir / f"ops_schema_v2_{name}.log")


def read_universe_csv(path: Path) -> tuple[list[dict], str]:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    rows = list(csv.DictReader(data.decode("utf-8-sig").splitlines()))
    if not rows or not {"symbol", "exchange", "effective_month"} <= set(rows[0]):
        raise DeployError("Universe CSV needs columns symbol, exchange, effective_month")
    symbols = [r["symbol"].strip().upper() for r in rows]
    if len(set(symbols)) != len(symbols) or not all(re.fullmatch(r"[A-Z0-9]{2,10}", s) for s in symbols):
        raise DeployError("Universe CSV has duplicate or malformed symbols")
    months = {r["effective_month"] for r in rows}
    if len(months) != 1:
        raise DeployError("Universe CSV must describe exactly one effective month (snapshot)")
    return rows, digest


def seed_live(settings: Settings, name: str, universe_csv: Path, observed_through: dt.date,
              dataset_code: str, source_note: str) -> dict:
    """Seed catalog rows only (no prices, no forecasts). Idempotent; conflicts abort the whole transaction."""
    rows, digest = read_universe_csv(universe_csv)
    month = rows[0]["effective_month"]
    y, m = (int(x) for x in month.split("-"))
    valid_from = dt.date(y, m, 1)
    valid_to = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
    url = rows[0].get("source_url", "")
    evidence = (f"Chi snapshot {month} tu {universe_csv.name} (sha256 {digest[:16]}...); nguon: {url[:180]}; "
                "khong suy rong lich su hay thanh phan hien tai.")[:500]
    with connect(settings, name, autocommit=False) as c:
        cur = c.cursor()
        try:
            def ensure(sql_exists: str, key: tuple, sql_insert: str, values: tuple, compare_sql: str | None = None):
                cur.execute(sql_exists, *key)
                row = cur.fetchone()
                if row is None:
                    cur.execute(sql_insert, *values)
                    return "inserted"
                if compare_sql:
                    cur.execute(compare_sql, *values)
                    if cur.fetchone() is None:
                        raise DeployError(f"Seed conflict: {sql_exists} {key}")
                return "present"

            ensure("SELECT 1 FROM dbo.Market WHERE MarketId=?", (1,),
                   "INSERT dbo.Market(MarketId,MarketCode,MarketName,CurrencyCode) VALUES(?,?,?,?)",
                   (1, "HOSE", "HOSE - EOD live (universe snapshot VN30)", "VND"),
                   "SELECT 1 FROM dbo.Market WHERE MarketId=? AND MarketCode=? AND MarketName=? AND CurrencyCode=?")
            ensure("SELECT 1 FROM dbo.StockIndex WHERE IndexId=?", (1,),
                   "INSERT dbo.StockIndex(IndexId,MarketId,IndexCode,IndexName) VALUES(?,?,?,?)",
                   (1, 1, "VN30", f"VN30 - snapshot nguon thang {month}"),
                   "SELECT 1 FROM dbo.StockIndex WHERE IndexId=? AND MarketId=? AND IndexCode=? AND IndexName=?")
            for i, r in enumerate(rows, start=1):
                sym = r["symbol"].strip().upper()
                cur.execute("SELECT StockId FROM dbo.Stock WHERE MarketId=1 AND Ticker=?", sym)
                hit = cur.fetchone()
                if hit is None:
                    cur.execute("SELECT ISNULL(MAX(StockId),0)+1 FROM dbo.Stock")
                    sid = cur.fetchone()[0]
                    cur.execute("INSERT dbo.Stock(StockId,MarketId,Ticker,CompanyName,IndustryId,IsSynthetic) VALUES(?,1,?,NULL,NULL,0)", sid, sym)
                else:
                    sid = hit[0]
                cur.execute("SELECT 1 FROM dbo.IndexMembership WHERE IndexId=1 AND StockId=? AND ValidFrom=?", sid, valid_from)
                if cur.fetchone() is None:
                    cur.execute("INSERT dbo.IndexMembership(IndexId,StockId,ValidFrom,ValidTo,EvidenceNote) VALUES(1,?,?,?,?)",
                                sid, valid_from, valid_to, evidence)
            cur.execute("SELECT DatasetId,DataKind,ObservedThrough FROM dbo.Dataset WHERE DatasetCode=?", dataset_code)
            ds = cur.fetchone()
            if ds is None:
                cur.execute("SELECT ISNULL(MAX(DatasetId),0)+1 FROM dbo.Dataset")
                dataset_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT dbo.Dataset(DatasetId,DatasetCode,MarketId,DataKind,PriceBasis,PriceUnit,ObservedThrough,ManifestPath,ProvenanceNote) "
                    "VALUES(?,?,1,'REAL_PRIVATE','SOURCE_CLOSE',?,?,?,?)",
                    dataset_id, dataset_code,
                    "Don vi bao gia nguon KBS (quan sat ~nghin VND/co phieu); chua xac minh he so VND",
                    observed_through, f"ops:{settings.ops_database}.ops.EodRun",
                    source_note[:1000])
            else:
                dataset_id = ds[0]
                if ds[1] != "REAL_PRIVATE":
                    raise DeployError("Existing dataset with this code is not REAL_PRIVATE")
            c.commit()
        except Exception:
            c.rollback()
            raise
    return {"database": name, "dataset_id": dataset_id, "stocks": len(rows), "universe_sha256": digest,
            "valid_from": valid_from.isoformat(), "valid_to": valid_to.isoformat(), "evidence": evidence}


def register_eod_config(settings: Settings, ops_db: str, database: str, dataset_id: int, index_code: str,
                        universe_as_of: dt.date, reference_symbol: str, evidence: str, cutoff: str = "16:10") -> None:
    with connect(settings, ops_db) as c:
        existing = query(c, "SELECT IndexCode,UniverseAsOf,CalendarReferenceSymbol FROM ops.EodConfig WHERE DatabaseName=? AND DatasetId=?",
                         (database, dataset_id))
        if existing:
            e = existing[0]
            if (e["IndexCode"], e["UniverseAsOf"], e["CalendarReferenceSymbol"]) != (index_code, universe_as_of.isoformat(), reference_symbol):
                raise DeployError("EodConfig already exists with different values; change it deliberately in SQL")
            return
        c.cursor().execute(
            "INSERT ops.EodConfig(DatabaseName,DatasetId,SourceCode,IndexCode,UniverseAsOf,CalendarReferenceSymbol,CutoffLocalTime,UniverseEvidence) "
            "VALUES(?,?,'KBS_VNSTOCK',?,?,?,?,?)",
            database, dataset_id, index_code, universe_as_of, reference_symbol, cutoff, evidence[:1000])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m marketlab_app.deploy")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ops-db", help="create/upgrade the ops database (MARKETLAB_OPS_DATABASE)")
    lv = sub.add_parser("live-db", help="create a NEW REAL_PRIVATE business database for EOD sync")
    lv.add_argument("--database", default="MarketLabVN30_Live")
    lv.add_argument("--universe-csv", required=True, type=Path)
    lv.add_argument("--observed-through", required=True, type=dt.date.fromisoformat,
                    help="initial ObservedThrough (day before the first session you will sync)")
    lv.add_argument("--dataset-code", default="KBS_VN30_EOD_LIVE")
    lv.add_argument("--reference-symbol", default="VN30")
    pf = sub.add_parser("preflight", help="read-only checks before migrating an existing database")
    pf.add_argument("--database", required=True)
    mg = sub.add_parser("migrate", help="apply 13_eod_extension to an EXISTING database (needs backup)")
    mg.add_argument("--database", required=True)
    mg.add_argument("--confirm-backup", required=True, type=Path, help="path of a verified .bak taken before migration")
    args = ap.parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    workdir = ROOT / "var" / "deploy" / stamp
    try:
        if args.cmd == "ops-db":
            out = deploy_ops_db(settings, settings.ops_database, workdir)
            print(out.strip().splitlines()[-3:])
        elif args.cmd == "live-db":
            check_new_name(args.database)
            created = create_database(settings, args.database, "REAL_PRIVATE_EOD")
            deploy_business_schema(settings, args.database, workdir)
            apply_eod_extension(settings, args.database, workdir)
            vnstock_note = ("KBS qua vnstock; Close nguon nhu tra ve tai thoi diem dong bo; nha cung cap co dieu chinh hoi to "
                            "(quan sat FPT 09/2025 thap hon ~9% so voi ban trich xuat truoc, cung Volume) - khong phai total return; "
                            "du lieu rieng cuc bo, quyen phan phoi UNKNOWN; lineage tung dong trong ops.PriceLoadLineage.")
            seeded = seed_live(settings, args.database, args.universe_csv, args.observed_through, args.dataset_code, vnstock_note)
            deploy_ops_db(settings, settings.ops_database, workdir)
            register_eod_config(settings, settings.ops_database, args.database, seeded["dataset_id"], "VN30",
                                dt.date.fromisoformat(seeded["valid_to"]), args.reference_symbol, seeded["evidence"], settings.eod_cutoff)
            print(json.dumps({"created": created, **seeded, "ops_database": settings.ops_database, "logs": str(workdir)}, ensure_ascii=False, indent=1))
        elif args.cmd == "preflight":
            print(run_sqlcmd(settings, ROOT / "sql" / "13_eod_preflight.sql", args.database, log=workdir / "preflight.log"))
        elif args.cmd == "migrate":
            if args.database in PROTECTED:
                raise DeployError("The public synthetic demo is never migrated")
            if not args.confirm_backup.is_file() or args.confirm_backup.stat().st_size == 0:
                raise DeployError("--confirm-backup must point to an existing, non-empty backup file")
            print(run_sqlcmd(settings, ROOT / "sql" / "13_eod_preflight.sql", args.database, log=workdir / "preflight.log"))
            print(apply_eod_extension(settings, args.database, workdir))
        return 0
    except DeployError as exc:
        print(f"DEPLOY ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
