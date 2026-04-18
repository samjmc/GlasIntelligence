"""Unit tests for configuration validation."""

import pytest
from app.config import Config


class TestConfigSimulationLimits:
    def test_free_plan_limits(self):
        agents, rounds = Config.simulation_limits("free")
        assert agents == Config.FREE_SIMULATION_AGENTS
        assert rounds == Config.FREE_SIMULATION_ROUNDS

    def test_payg_plan_limits(self):
        agents, rounds = Config.simulation_limits("payg")
        assert agents == Config.FREE_SIMULATION_AGENTS
        assert rounds == Config.FREE_SIMULATION_ROUNDS

    def test_pro_plan_limits(self):
        agents, rounds = Config.simulation_limits("pro")
        assert agents == Config.PRO_SIMULATION_AGENTS
        assert rounds == Config.PRO_SIMULATION_ROUNDS

    def test_business_plan_limits(self):
        agents, rounds = Config.simulation_limits("business")
        assert agents == Config.BUSINESS_SIMULATION_AGENTS
        assert rounds == Config.BUSINESS_SIMULATION_ROUNDS

    def test_enterprise_plan_limits(self):
        agents, rounds = Config.simulation_limits("enterprise")
        assert agents == Config.ENTERPRISE_SIMULATION_AGENTS
        assert rounds == Config.ENTERPRISE_SIMULATION_ROUNDS

    def test_enterprise_plan_limits_normalizes_casing(self):
        """Supabase may store 'Enterprise' from manual grants; limits must still apply."""
        agents, rounds = Config.simulation_limits("Enterprise")
        assert agents == Config.ENTERPRISE_SIMULATION_AGENTS
        assert rounds == Config.ENTERPRISE_SIMULATION_ROUNDS

    def test_unknown_plan_defaults_to_pro(self):
        agents, rounds = Config.simulation_limits("unknown")
        assert agents == Config.PRO_SIMULATION_AGENTS
        assert rounds == Config.PRO_SIMULATION_ROUNDS


class TestConfigValidation:
    def test_validate_returns_lists(self):
        errors, warnings = Config.validate()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)
