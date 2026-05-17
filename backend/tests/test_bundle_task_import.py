"""Regression test: bundle_tasks._wait_for_preparation must import check_simulation_prepared
from simulation_helpers, not the nonexistent _check_simulation_prepared from simulation.

Bug: bundle_tasks.py imported `_check_simulation_prepared` (with underscore) which doesn't
exist, causing an ImportError on every scenario run — making every bundle fail immediately.
"""
import pathlib
import ast


_BUNDLE_TASKS = pathlib.Path(__file__).parent.parent / "app" / "tasks" / "bundle_tasks.py"
_HELPERS = pathlib.Path(__file__).parent.parent / "app" / "api" / "simulation_helpers.py"


def test_wait_for_preparation_does_not_reference_underscore_variant():
    """Source must not contain the nonexistent _check_simulation_prepared name."""
    source = _BUNDLE_TASKS.read_text()
    assert "_check_simulation_prepared" not in source, (
        "bundle_tasks still imports _check_simulation_prepared (with underscore) "
        "which does not exist in simulation.py or simulation_helpers.py. "
        "This causes an ImportError on every bundle run."
    )


def test_wait_for_preparation_references_correct_name():
    """Source must reference check_simulation_prepared (no underscore prefix)."""
    source = _BUNDLE_TASKS.read_text()
    assert "check_simulation_prepared" in source


def test_check_simulation_prepared_defined_in_helpers():
    """check_simulation_prepared must be defined in simulation_helpers."""
    source = _HELPERS.read_text()
    tree = ast.parse(source)
    func_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert "check_simulation_prepared" in func_names, (
        "check_simulation_prepared not found in simulation_helpers.py"
    )
    assert "_check_simulation_prepared" not in func_names


def test_bundle_tasks_imports_from_simulation_helpers():
    """bundle_tasks must import check_simulation_prepared from simulation_helpers, not from simulation."""
    source = _BUNDLE_TASKS.read_text()
    # Must import from simulation_helpers (direct source), not from simulation (which just re-exports it)
    assert "simulation_helpers" in source and "check_simulation_prepared" in source
