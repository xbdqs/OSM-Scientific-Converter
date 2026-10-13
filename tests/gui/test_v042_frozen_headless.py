"""Release regression: frozen application launches the audited quick CLI."""
from __future__ import annotations
import sys
from pathlib import Path

def test_frozen_quick_worker_launches_executable(monkeypatch, tmp_path):
    import osm_scientific_converter.gui.workers as w
    from types import SimpleNamespace
    seen = {}
    class FakeProcess:
        returncode = 0
        def __init__(self, command, **kw):
            seen['command'] = command
            self.returncode = 0
            output = tmp_path / 'output.gpkg'
            output.write_bytes(b'GPKG')
            Path(str(output) + '.audit.json').write_text('{"status":"success","source_layer":"lines"}')
        def poll(self): return 0
    monkeypatch.setattr(w.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(w.subprocess, 'Popen', FakeProcess)
    monkeypatch.setattr(w.time, 'sleep', lambda _: None)
    src = tmp_path / 'input.osm'; src.write_text('<osm/>')
    rules = tmp_path / 'rule.json'; rules.write_text('{}')
    result = w.quick_highway_worker(src, rules, tmp_path / 'output.gpkg').function(lambda _: None)
    assert seen['command'][0] == sys.executable
    assert seen['command'][1:3] == ['--headless-cli', 'quick-extract']
    assert result['audit']['status'] == 'success'

def test_headless_app_dispatch_accepts_quick_extract_only(monkeypatch):
    import osm_scientific_converter.gui.app as app
    import osm_scientific_converter.cli.main as cli
    calls=[]
    monkeypatch.setattr(app, 'configure_frozen_runtime', lambda: calls.append('config'))
    monkeypatch.setattr(cli, 'main', lambda args: calls.append(args) or 0)
    assert app.main(['frozen.exe','--headless-cli','quick-extract','file.osm']) == 0
    assert calls == ['config',['quick-extract','file.osm']]

def test_headless_app_rejects_other_commands():
    import pytest
    import osm_scientific_converter.gui.app as app
    with pytest.raises(SystemExit):
        app.main(['frozen.exe','--headless-cli','scan','file.osm'])
