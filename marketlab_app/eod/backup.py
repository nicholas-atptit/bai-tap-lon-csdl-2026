"""Verified COPY_ONLY backups before large writes (business DB + ops DB).

Steps per database:
  1. preflight: database size (used pages) vs free space on the backup volume (needs >= 2x used + 256 MB);
  2. BACKUP DATABASE ... TO DISK WITH COPY_ONLY, CHECKSUM, INIT, FORMAT (does not break the log chain);
  3. RESTORE VERIFYONLY ... WITH CHECKSUM and RESTORE HEADERONLY (database name, finish time, checksum flag);
  4. optional test restore into MarketLabVN30_RestoreCheck_<stamp> (created and dropped by this module only), compare
     row counts of the key tables with the source, then drop the scratch database.
The backup files live in the SQL Server default backup directory (the service account can write there) and are never
committed (*.bak is gitignored). Restore plan (manual, operator decision): see docs/BACKFILL_RUNBOOK.md.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

from ..config import ROOT, Settings
from ..db import connect, query

RESTORE_PREFIX = "MarketLabVN30_RestoreCheck_"
KEY_TABLES = {"business": ["dbo.DailyPrice", "dbo.TradingDay", "dbo.Stock", "dbo.IndexMembership", "dbo.Dataset", "dbo.Prediction"],
              "ops": ["ops.EodRun", "ops.EodRunItem", "ops.PriceLoadLineage", "ops.PriceReconciliation"]}


class BackupError(RuntimeError):
    pass


def _drain(cur) -> None:
    """BACKUP/RESTORE report progress as informational result sets; they must be consumed or the command is cut short."""
    while cur.nextset():
        pass


def _exact_counts(settings: Settings, database: str, tables: list[str]) -> dict:
    out = {}
    with connect(settings, database) as c:
        for t in tables:
            if query(c, "SELECT OBJECT_ID(?) AS o", (t,))[0]["o"] is None:
                out[t] = None
                continue
            out[t] = query(c, f"SELECT COUNT_BIG(*) AS n FROM {t}")[0]["n"]
    return out


def backup_database(settings: Settings, database: str, kind: str, stamp: str, restore_check: bool = True) -> dict:
    with connect(settings, "master") as c:
        paths = query(c, "SELECT CONVERT(nvarchar(400),SERVERPROPERTY('InstanceDefaultBackupPath')) AS b, CONVERT(nvarchar(400),SERVERPROPERTY('InstanceDefaultDataPath')) AS d")[0]
    with connect(settings, database) as c:
        used = query(c, "SELECT SUM(CAST(FILEPROPERTY(name,'SpaceUsed') AS bigint))*8192 AS used, SUM(CAST(size AS bigint))*8192 AS alloc FROM sys.database_files")[0]
    backup_dir = Path(paths["b"])
    try:
        free = shutil.disk_usage(backup_dir.anchor or str(backup_dir)).free
    except OSError:
        free = None
    need = 2 * int(used["used"] or 0) + 256 * 1024 * 1024
    if free is not None and free < need:
        raise BackupError(f"not enough free space for {database} backup on {backup_dir.anchor}: free {free} < needed {need} bytes")
    target = str(backup_dir / f"{database}_preBackfill_{stamp}.bak")
    with connect(settings, "master") as c:
        cur = c.cursor()
        cur.execute(f"DECLARE @p nvarchar(400)=?; BACKUP DATABASE [{database}] TO DISK=@p WITH COPY_ONLY, CHECKSUM, INIT, FORMAT, "
                    f"NAME=N'{database} pre-backfill {stamp}', STATS=50;", target)
        _drain(cur)
        cur.execute("DECLARE @p nvarchar(400)=?; RESTORE VERIFYONLY FROM DISK=@p WITH CHECKSUM;", target)
        _drain(cur)
        cur.execute("DECLARE @p nvarchar(400)=?; RESTORE HEADERONLY FROM DISK=@p;", target)
        cols = [d[0] for d in cur.description]
        head = dict(zip(cols, cur.fetchone()))
        _drain(cur)
    if head.get("DatabaseName") != database or not head.get("HasBackupChecksums"):
        raise BackupError(f"backup header check failed for {database}: {head.get('DatabaseName')}, checksums={head.get('HasBackupChecksums')}")
    result = {"database": database, "kind": kind, "file": target, "backup_size": int(head.get("BackupSize") or 0),
              "finished": str(head.get("BackupFinishDate")), "copy_only": bool(head.get("IsCopyOnly")),
              "checksums": bool(head.get("HasBackupChecksums")), "verifyonly": "PASS", "used_bytes": int(used["used"] or 0),
              "free_bytes_before": free}
    if restore_check:
        result["restore_check"] = _restore_check(settings, database, kind, target, paths["d"], stamp)
    result["verified"] = result["verifyonly"] == "PASS" and (not restore_check or result["restore_check"]["match"])
    return result


def _restore_check(settings: Settings, database: str, kind: str, target: str, data_dir: str, stamp: str) -> dict:
    scratch = f"{RESTORE_PREFIX}{kind}_{stamp}"
    tables = KEY_TABLES[kind]
    source = _exact_counts(settings, database, tables)
    with connect(settings, "master") as c:
        if query(c, "SELECT 1 AS x FROM sys.databases WHERE name=?", (scratch,)):
            raise BackupError(f"scratch database {scratch} already exists; refusing")
        cur = c.cursor()
        cur.execute("DECLARE @p nvarchar(400)=?; RESTORE FILELISTONLY FROM DISK=@p;", target)
        files = [(r[0], r[2]) for r in cur.fetchall()]   # LogicalName, Type (D/L)
        _drain(cur)
        moves = []
        for i, (logical, ftype) in enumerate(files):
            physical = Path(data_dir) / f"{scratch}_{i}.{'mdf' if ftype == 'D' else 'ldf'}"
            moves.append(f"MOVE N'{logical}' TO N'{physical}'")
        moves = ", ".join(moves)
        try:
            cur.execute(f"DECLARE @p nvarchar(400)=?; RESTORE DATABASE [{scratch}] FROM DISK=@p WITH {moves}, RECOVERY, CHECKSUM, STATS=50;", target)
            _drain(cur)
            restored = _exact_counts(settings, scratch, tables)
        finally:
            if query(c, "SELECT 1 AS x FROM sys.databases WHERE name=?", (scratch,)) and scratch.startswith(RESTORE_PREFIX):
                c.cursor().execute(f"ALTER DATABASE [{scratch}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{scratch}];")
    return {"scratch_database": scratch, "source_counts": source, "restored_counts": restored, "match": source == restored,
            "scratch_dropped": True}


def backup_for_backfill(settings: Settings, restore_check: bool = True) -> dict:
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    if settings.sql_database in ("MarketLabVN30_Demo",) or settings.sql_database.startswith("MarketLabVN30_Research"):
        raise BackupError(f"backfill never targets {settings.sql_database}")
    out = {"stamp": stamp, "backups": [backup_database(settings, settings.sql_database, "business", stamp, restore_check),
                                       backup_database(settings, settings.ops_database, "ops", stamp, restore_check)]}
    out["verified"] = all(b["verified"] for b in out["backups"])
    manifest = ROOT / "var" / "backups" / f"backup_manifest_{stamp}.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    out["manifest"] = str(manifest)
    return out
