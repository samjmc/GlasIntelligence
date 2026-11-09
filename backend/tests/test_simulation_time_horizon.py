"""The scenario's time horizon is kept as data, and the round <-> horizon mapping is explicit.

Live run 2026-11-09 (Revolut Mobile, "over the next six months"): the LLM chose 4320 hours,
OASIS_DEFAULT_MAX_ROUNDS clamped the run to 10 rounds x 60 minutes (~10 simulated hours),
yet the reasoning still said "Simulation spans six months" and the report described the
six-month reaction. The saved time_config now says what each round stands for.
"""

import json
from unittest.mock import patch

from app.services.simulation_config_generator import SimulationConfigGenerator


def _generate(time_result: dict) -> dict:
    gen = SimulationConfigGenerator(api_key="test-key", base_url="http://localhost", model_name="m")
    with (
        patch("app.services.simulation_config_generator.Config.OASIS_DEFAULT_MAX_ROUNDS", 10),
        patch.object(gen, "_generate_time_config", return_value=time_result),
        patch.object(gen, "_generate_event_config", return_value={}),
    ):
        params = gen.generate_config(
            simulation_id="sim",
            project_id="proj",
            graph_id="graph",
            simulation_requirement="Over the next six months, how will Vodafone, Eir and Three react?",
            document_text="",
            entities=[],
        )
    return json.loads(params.to_json())


def test_six_month_horizon_compressed_into_ten_rounds_is_stated_honestly():
    cfg = _generate(
        {"total_simulation_hours": 4320, "minutes_per_round": 60, "reasoning": "Simulation spans six months"}
    )
    tc = cfg["time_config"]

    assert tc["total_simulation_hours"] == 10  # the run itself: 10 rounds x 60 minutes
    assert tc["scenario_horizon_hours"] == 4320  # what the scenario asks about
    assert tc["hours_represented_per_round"] == 432.0  # 18 days per round
    assert tc["total_simulation_hours"] * 60 // tc["minutes_per_round"] == 10

    reasoning = cfg["generation_reasoning"]
    assert "Scenario horizon: 6 months; run as 10 rounds, each standing for about 18 days" in reasoning
    assert "compressed time" in reasoning
    assert "spans six months" not in reasoning


def test_short_horizon_runs_hour_by_hour_and_keeps_llm_rationale():
    cfg = _generate({"total_simulation_hours": 6, "minutes_per_round": 60, "reasoning": "Evening peak"})
    tc = cfg["time_config"]

    assert tc["total_simulation_hours"] == 6
    assert tc["scenario_horizon_hours"] == 6
    assert tc["hours_represented_per_round"] == 1.0
    assert "run as 6 rounds of 60 minutes" in cfg["generation_reasoning"]
    assert "compressed" not in cfg["generation_reasoning"]
    assert "Time config: Evening peak" in cfg["generation_reasoning"]
