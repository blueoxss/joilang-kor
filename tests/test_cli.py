from __future__ import annotations

import json

import pytest

from joilang_kor.__main__ import main


def test_cli_check_data_and_render_and_score(repo_root, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(repo_root)
    assert main(["check-data"]) == 0
    assert '"ok": true' in capsys.readouterr().out
    out = tmp_path / "prompt.json"
    assert main(["render-prompt", "--row", "214", "--prompt-mode", "source", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["prompt_mode"] == "source"
    preds = tmp_path / "preds.jsonl"
    preds.write_text(json.dumps({"row_no": 4, "output": '{"name":"","cron":"","period":0,"code":"(#Siren).siren_setsirenmode(\\"emergency\\")"}'}) + "\n")
    assert main(["score", "--predictions", str(preds), "--out", str(tmp_path / "score")]) == 0
    assert json.loads((tmp_path / "score/summary.json").read_text())["passed"] == 1
    for bad in ('{"row_no": 999, "output": ""}', '{"output": ""}', "not json", '{"row_no": "4", "output": ""}'):
        preds.write_text(bad + "\n")
        with pytest.raises(SystemExit):
            main(["score", "--predictions", str(preds), "--out", str(tmp_path / "score2")])
    with pytest.raises(SystemExit):
        main(["score", "--predictions", str(tmp_path / "missing.jsonl"), "--out", str(tmp_path / "score3")])


def test_cli_demo_offline_and_option_guards(repo_root, tmp_path, monkeypatch, capsys):
    import urllib.error
    import urllib.request

    monkeypatch.chdir(repo_root)
    assert main(["demo", "--mode", "offline", "--case", "examples/scenario.json", "--out", str(tmp_path / "demo")]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["regeneration"] == "not_performed" and summary["regeneration_reason"] == "offline mode"
    with pytest.raises(SystemExit):
        main(["demo", "--mode", "offline", "--case", "examples/scenario.json", "--out", str(tmp_path / "d2"), "--endpoint", "http://x/v1"])
    with pytest.raises(SystemExit):
        main(["demo", "--mode", "live", "--case", "examples/scenario.json", "--out", str(tmp_path / "d3"), "--saved-output", "examples/saved_output.json"])
    with pytest.raises(SystemExit):
        main(["render-prompt", "--row", "4", "--retrieval-corpus", "schemas/service_retrieval_corpus.json"])
    def refused(*args, **kwargs):
        raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))

    monkeypatch.setattr(urllib.request, "urlopen", refused)
    assert main(["demo", "--mode", "live", "--case", "examples/scenario.json", "--out", str(tmp_path / "live"),
                 "--endpoint", "http://127.0.0.1:9/v1", "--model", "m"]) == 1
    assert json.loads((tmp_path / "live/summary.json").read_text())["status"] == "failed"
