"""Fail-closed experimental targeted extraction logic (no GDAL runtime needed)."""
import json
import sqlite3
from pathlib import Path
import pytest

from osm_scientific_converter.core.profiles import load_custom_profile, ResolvedProfile
from osm_scientific_converter.core.targeted import (
    reviewed_highway_mapping, _gdal_sql, _gdal_osm_config, _inject_provenance,
    _preflight_gpkg_records, _provenance_update_sql,
)

ROOT = Path(__file__).resolve().parents[2]


def profile():
    return load_custom_profile(ROOT / "examples/round2_road_extraction_rules.json")


def test_profile_whitelist_exact_lines():
    values, mapping = reviewed_highway_mapping(profile())
    assert len(values) == 13
    assert mapping["motorway"] == ("motorways_and_trunks", "road_motorways")
    assert all("'" not in val for val in values)
    assert "FROM lines WHERE highway IN" in _gdal_sql(values)


def test_config_promotes_highway_exact_field():
    source = (ROOT / "src/osm_scientific_converter/resources/osmconf.ini").read_text()
    updated = _gdal_osm_config(source)
    assert updated.count("attributes=highway,name,ref,maxspeed,oneway") == 1
    assert "[multipolygons]" in updated


@pytest.mark.parametrize("mutate", [
    lambda d: d["rules"][0].update({"source_layer": ["lines", "multipolygons"]}),
    lambda d: d["rules"][0].update({"geometry": ["line"]}),
    lambda d: d["rules"][0]["expression"].update({"op": "regex"}),
    lambda d: d["rules"][0]["expression"].update({"value": ["motorway' OR 1=1"]}),
])
def test_unsupported_rules_fail_closed(mutate):
    data = json.loads(json.dumps(profile().data))
    mutate(data)
    with pytest.raises(ValueError):
        reviewed_highway_mapping(ResolvedProfile(data, "x" * 64, "test"))


def test_duplicate_values_rejected():
    data = json.loads(json.dumps(profile().data))
    data["rules"][0]["expression"]["value"].append("residential")
    with pytest.raises(ValueError, match="Duplicate highway"):
        reviewed_highway_mapping(ResolvedProfile(data, "x" * 64, "test"))


def create_sqlite(path, records):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE highway_lines (fid INTEGER PRIMARY KEY, osm_id TEXT, highway TEXT, all_tags TEXT)")
    conn.executemany("INSERT INTO highway_lines VALUES(?,?,?,?)", records)
    conn.commit()
    return conn


def test_inject_profile_evidence_and_canonical_id(tmp_path):
    conn = create_sqlite(tmp_path/"mock.gpkg", [
        (1, "1001", "motorway", '{"highway":"motorway","name":"A1"}'),
        (2, "1002", "service", '{"highway":"service","name":"B"}'),
    ])
    _, mapping = reviewed_highway_mapping(profile())
    result = _inject_provenance(conn, "highway_lines", profile(), mapping)
    assert result["feature_count"] == 2
    rows = conn.execute("SELECT canonical_osm_id,source_layer,category,rule_ids,profile_sha256,tags_json FROM highway_lines ORDER BY fid").fetchall()
    assert rows[0][:4] == ("way/1001", "lines", "motorways_and_trunks", "road_motorways")
    assert rows[1][:4] == ("way/1002", "lines", "residential_and_service", "road_local")
    assert rows[0][4] == profile().sha256
    assert json.loads(rows[0][5])["highway"] == "motorway"
    conn.close()


def test_injection_requires_complete_all_tags(tmp_path):
    conn = create_sqlite(tmp_path/"bad.gpkg", [(1,"1001","motorway",'{"foo":"bar"}')])
    _, mapping=reviewed_highway_mapping(profile())
    with pytest.raises(RuntimeError,match="tag mismatch"):
        _inject_provenance(conn,"highway_lines",profile(),mapping)
    conn.close()


def test_injection_requires_unique_identity(tmp_path):
    conn = create_sqlite(tmp_path/"dup.gpkg", [
        (1, "1001", "motorway",'{"highway":"motorway"}'),
        (2, "1001", "service",'{"highway":"service"}'),
    ])
    _, mapping=reviewed_highway_mapping(profile())
    with pytest.raises(RuntimeError,match="Repeated canonical"):
        _inject_provenance(conn,"highway_lines",profile(),mapping)
    conn.close()


def test_targeted_extract_stages_atomically_with_execution_report(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from osm_scientific_converter.core.targeted import targeted_highway_extract
    input_path = tmp_path / "input.osm"
    input_path.write_text("<osm version='0.6'/>", encoding="utf-8")
    config = ROOT / "src/osm_scientific_converter/resources/osmconf.ini"
    out = tmp_path / "result.gpkg"

    def fake_gdal(command, capture_output, text, errors):
        assert "FROM lines WHERE highway IN" in command[command.index("-sql") + 1]
        sqlite = Path(command[command.index("-f") + 2])
        conn = create_sqlite(sqlite, [(1, "1001", "motorway", '{"highway":"motorway"}')])
        conn.close()
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("osm_scientific_converter.core.targeted.subprocess.run", fake_gdal)

    def fake_ogr_injection(path, table, resolved, mapping):
        # Test the workflow orchestration without needing native GDAL here.
        from contextlib import closing
        with closing(sqlite3.connect(path)) as conn:
            with conn:
                return _inject_provenance(conn, table, resolved, mapping)

    monkeypatch.setattr("osm_scientific_converter.core.targeted._inject_provenance_ogr", fake_ogr_injection)
    audit = targeted_highway_extract(input_path, out, profile(), base_config=config)
    assert audit["status"] == "success"
    assert audit["feature_count"] == 1
    assert not any("No GUI integration" in item for item in audit["scope_limitations"])
    assert any("first 400 exported objects" in item for item in audit["scope_limitations"])
    assert out.is_file() and Path(str(out) + ".audit.json").is_file()
    with sqlite3.connect(out) as conn:
        assert conn.execute("SELECT canonical_osm_id FROM highway_lines").fetchone()[0] == "way/1001"
    with pytest.raises(FileExistsError):
        targeted_highway_extract(input_path, out, profile(), base_config=config)


def test_staging_sqlite_connection_closed_before_cleanup(tmp_path, monkeypatch):
    """Catch Windows WinError 32 before deployment, even on POSIX systems.

    Holding a Python reference to the connection means its destructor cannot
    silently close the file; the production code must explicitly close it.
    """
    from types import SimpleNamespace
    from osm_scientific_converter.core import targeted

    source = tmp_path / "input.osm"
    source.write_text("<osm version='0.6'/>", encoding="utf-8")
    out = tmp_path / "result.gpkg"
    config = ROOT / "src/osm_scientific_converter/resources/osmconf.ini"
    real_connect = sqlite3.connect
    opened = []

    def tracking_connect(path, *args, **kwargs):
        connection = real_connect(path, *args, **kwargs)
        if Path(path).name == "selected.gpkg":
            opened.append(connection)
        return connection

    def fake_gdal(command, capture_output, text, errors):
        path = Path(command[command.index("-f") + 2])
        with real_connect(path) as connection:
            connection.execute("CREATE TABLE highway_lines (fid INTEGER PRIMARY KEY, osm_id TEXT, highway TEXT, all_tags TEXT)")
            connection.execute("INSERT INTO highway_lines VALUES(?,?,?,?)", (1, "1001", "motorway", '{"highway":"motorway"}'))
        # Note: this separate mock connection must also be closed explicitly.
        connection.close()
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(targeted.sqlite3, "connect", tracking_connect)
    monkeypatch.setattr(targeted.subprocess, "run", fake_gdal)

    def fake_ogr_injection(path, table, resolved, mapping):
        from contextlib import closing
        with closing(sqlite3.connect(path)) as conn:
            with conn:
                return targeted._inject_provenance(conn, table, resolved, mapping)

    monkeypatch.setattr(targeted, "_inject_provenance_ogr", fake_ogr_injection)
    targeted.targeted_highway_extract(source, out, profile(), base_config=config)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")
    assert out.exists()
    assert not list(tmp_path.glob(".osm-sci-targeted-*"))


def test_preflight_read_only_validates_road_semantics(tmp_path):
    path = tmp_path / "fake.gpkg"
    conn = create_sqlite(path, [
        (1, "1001", "motorway", '{"highway":"motorway"}'),
        (2, "1002", "service", '{"highway":"service"}'),
    ])
    _, mapping = reviewed_highway_mapping(profile())
    result = _preflight_gpkg_records(conn, "highway_lines", mapping)
    assert result["feature_count"] == 2
    assert set(result["category_counts"]) == {"motorways_and_trunks", "residential_and_service"}
    columns = {item[1] for item in conn.execute("PRAGMA table_info(highway_lines)")}
    assert "canonical_osm_id" not in columns
    conn.close()


def test_native_gpkg_bulk_sql_quotes_literals_and_keeps_ids():
    p = profile()
    _, mapping = reviewed_highway_mapping(p)
    statement = _provenance_update_sql("highway_lines", p, mapping)
    assert 'UPDATE "highway_lines" SET' in statement
    assert "'way/' || CAST(\"osm_id\" AS TEXT)" in statement
    assert '"tags_json" = "all_tags"' in statement
    # A deliberately unusual but valid profile category must be SQL-escaped.
    mapping = dict(mapping)
    mapping["motorway"] = ("O'Brian's highways", "rule'1")
    escaped = _provenance_update_sql("highway_lines", p, mapping)
    assert "'O''Brian''s highways'" in escaped
    assert "'rule''1'" in escaped


def test_deferred_flag_writes_config_and_requests_post_update_index(tmp_path, monkeypatch):
    """Protect the opt-in flag wiring without native GDAL."""
    from types import SimpleNamespace
    from osm_scientific_converter.core import targeted
    source = tmp_path / "input.osm"
    source.write_text("<osm version='0.6'/>", encoding="utf-8")
    target = tmp_path / "experimental.gpkg"
    config = ROOT / "src/osm_scientific_converter/resources/osmconf.ini"
    observed = {}

    def fake_gdal(command, capture_output, text, errors):
        observed['command'] = command
        db = Path(command[command.index('-f')+2])
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE highway_lines (fid INTEGER PRIMARY KEY, osm_id TEXT, highway TEXT, all_tags TEXT)")
            conn.execute("INSERT INTO highway_lines VALUES (?,?,?,?)", (1, '1001', 'motorway', json.dumps({'highway': 'motorway'})))
        conn.close()
        return SimpleNamespace(returncode=0, stderr='', stdout='')

    def fake_inject(path, table, resolved, mapping, *, deferred_spatial_index=False):
        observed['deferred_spatial_index'] = deferred_spatial_index
        from contextlib import closing
        with closing(sqlite3.connect(path)) as conn:
            with conn:
                return targeted._inject_provenance(conn, table, resolved, mapping)

    monkeypatch.setattr(targeted.subprocess, 'run', fake_gdal)
    monkeypatch.setattr(targeted, '_inject_provenance_ogr', fake_inject)
    report = targeted.targeted_highway_extract(
        source, target, profile(), base_config=config,
        experimental_deferred_index=True,
    )
    assert observed['command'][-2:] == ['-lco', 'SPATIAL_INDEX=NO']
    assert observed['deferred_spatial_index'] is True
    assert report['experimental_deferred_index'] is True
    assert report['feature_count'] == 1
