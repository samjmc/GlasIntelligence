"""A reddit-only simulation that already ran must still count as prepared.

Live 2026-10-10 (sim_b8bb8b07981b): a failed run could not be restarted. /start answered
400 "Simulation not ready ... please call /prepare first", because the prepared check
required twitter_profiles.csv, which reddit-only prepare no longer writes.
"""

from __future__ import annotations

import json

import pytest

from app.api import simulation as simulation_api
from app.api import simulation_helpers


def _sim(tmp_path, *, status="failed", enable_twitter=False, twitter_csv=False):
    sim_dir = tmp_path / "sim_x"
    sim_dir.mkdir()
    (sim_dir / "state.json").write_text(
        json.dumps(
            {"status": status, "config_generated": True, "enable_reddit": True, "enable_twitter": enable_twitter}
        ),
        encoding="utf-8",
    )
    (sim_dir / "simulation_config.json").write_text("{}", encoding="utf-8")
    (sim_dir / "reddit_profiles.json").write_text(json.dumps([{"user_id": 1}, {"user_id": 2}]), encoding="utf-8")
    if twitter_csv:
        (sim_dir / "twitter_profiles.csv").write_text("user_id\n1\n", encoding="utf-8")
    return sim_dir


CHECKS = [simulation_api._check_simulation_prepared, simulation_helpers.check_simulation_prepared]


@pytest.mark.parametrize("check", CHECKS)
@pytest.mark.parametrize("status", ["failed", "completed", "stopped", "ready"])
def test_reddit_only_simulation_is_prepared_without_twitter_csv(tmp_path, monkeypatch, check, status):
    _sim(tmp_path, status=status)
    monkeypatch.setattr("app.config.Config.OASIS_SIMULATION_DATA_DIR", str(tmp_path))

    ok, info = check("sim_x")

    assert ok, info
    assert info["profiles_count"] == 2


@pytest.mark.parametrize("check", CHECKS)
def test_a_saved_twitter_simulation_still_needs_its_csv(tmp_path, monkeypatch, check):
    _sim(tmp_path, enable_twitter=True, twitter_csv=False)
    monkeypatch.setattr("app.config.Config.OASIS_SIMULATION_DATA_DIR", str(tmp_path))

    ok, info = check("sim_x")

    assert not ok
    assert info["missing_files"] == ["twitter_profiles.csv"]
