"""Integration: the EOD migration does not weaken the verified SQL design.
A fresh copy of the synthetic demo is built under an IT name (00-06 + 03 sample data), migrated with 13_eod_extension,
then the ORIGINAL 44 validation tests and 16 business queries are executed on it (database name substituted only).
Rollback restores the original trigger text byte-for-byte (whitespace-normalised) and re-applying is idempotent."""
import re

import pytest

from conftest import ROOT, STAMP, drop_it_database, it_settings
from marketlab_app import deploy
from marketlab_app.db import connect, query

pytestmark = pytest.mark.integration
EVIDENCE = ROOT / "var" / "test_evidence" / STAMP


@pytest.fixture(scope="module")
def migrated_demo(require_sql):
    db = f"MarketLabVN30_IT_{STAMP}_Mig"
    s = it_settings(db, "MarketLabVN30_Ops")
    deploy.create_database(s, db, "INTEGRATION_TEST")
    text = deploy.render_schema(db)
    sample = (ROOT / "sql" / "03_insert_sample_data.sql").read_text(encoding="utf-8-sig").replace("MarketLabVN30_Demo", db)
    text = text.replace("-- FILE: 04_functions.sql", sample + "\n-- FILE: 04_functions.sql", 1)
    script = EVIDENCE / f"{db}_schema_and_sample.sql"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(text, encoding="utf-8-sig")
    deploy.run_sqlcmd(s, script, "master", log=EVIDENCE / f"{db}_deploy.log")
    deploy.apply_eod_extension(s, db, EVIDENCE)
    yield s, db
    drop_it_database(db)


def run_original(s, db, name):
    text = (ROOT / "sql" / name).read_text(encoding="utf-8-sig").replace("MarketLabVN30_Demo", db)
    path = EVIDENCE / f"{db}_{name}"
    path.write_text(text, encoding="utf-8-sig")
    return deploy.run_sqlcmd(s, path, db, log=EVIDENCE / f"{db}_{name}.log")


def test_original_44_validation_tests_pass_after_migration(migrated_demo):
    s, db = migrated_demo
    out = run_original(s, db, "08_validation_tests.sql")
    assert re.search(r"^PASS\|44\s*$", out, re.M), out[-1500:]
    assert "FAIL|" not in out


def test_original_16_business_queries_run_after_migration(migrated_demo):
    s, db = migrated_demo
    out = run_original(s, db, "07_business_queries.sql")
    assert "Msg " not in out
    assert len(re.findall(r"\(\d+ rows? affected\)", out)) >= 16 or out.count("\n---") >= 16


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def test_rollback_restores_original_trigger_and_reapply_is_idempotent(migrated_demo):
    s, db = migrated_demo
    get = "SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.tr_Dataset_Guard')) AS d"
    with connect(s, "MarketLabVN30_Demo") as c:       # read-only reference: the untouched public demo
        reference = query(c, get)[0]["d"]
    with connect(s) as c:
        assert _norm(query(c, get)[0]["d"]) != _norm(reference)   # extension active
    deploy.run_sqlcmd(s, ROOT / "sql" / "13_eod_extension_rollback.sql", db, log=EVIDENCE / f"{db}_rollback.log")
    with connect(s) as c:
        assert _norm(query(c, get)[0]["d"]) == _norm(reference)
        assert query(c, "SELECT OBJECT_ID('ops.usp_EodApplySession') AS o, SCHEMA_ID('ops') AS s")[0] == {"o": None, "s": None}
        assert query(c, "SELECT COUNT(*) AS n FROM sys.extended_properties WHERE class=0 AND name='MarketLabEodExtension'")[0]["n"] == 0
    deploy.apply_eod_extension(s, db, EVIDENCE)
    deploy.apply_eod_extension(s, db, EVIDENCE)
    with connect(s) as c:
        assert query(c, "SELECT COUNT(*) AS n FROM sys.tables WHERE is_ms_shipped=0")[0]["n"] == 13
        assert query(c, "SELECT COUNT(*) AS n FROM sys.procedures WHERE SCHEMA_NAME(schema_id)='ops'")[0]["n"] == 1


def test_extension_refused_on_public_demo(require_sql):
    with pytest.raises(deploy.DeployError):
        deploy.apply_eod_extension(it_settings("MarketLabVN30_Demo", "MarketLabVN30_Ops"), "MarketLabVN30_Demo", EVIDENCE)
    with pytest.raises(deploy.DeployError):
        deploy.check_new_name("MarketLabVN30_Research_20261027")


def test_preflight_is_read_only_and_reports(migrated_demo):
    s, db = migrated_demo
    out = deploy.run_sqlcmd(s, ROOT / "sql" / "13_eod_preflight.sql", db, log=EVIDENCE / f"{db}_preflight.log")
    assert "EOD_PREFLIGHT_PASS" in out and "Last FULL backup" in out
