"""
OASIS dual-platform parallel simulation preset script
Runs Twitter and Reddit simulations concurrently, reading the same config file

Features:
- Dual-platform (Twitter + Reddit) parallel simulation
- Does not close environments immediately after simulation; enters command-wait mode
- Supports receiving Interview commands via IPC
- Supports single-agent and batch interviews
- Supports remote environment shutdown commands

Usage:
    python run_parallel_simulation.py --config simulation_config.json
    python run_parallel_simulation.py --config simulation_config.json --no-wait  # close immediately after completion
    python run_parallel_simulation.py --config simulation_config.json --twitter-only
    python run_parallel_simulation.py --config simulation_config.json --reddit-only

Log structure:
    sim_xxx/
    ├── twitter/
    │   └── actions.jsonl    # Twitter platform action log
    ├── reddit/
    │   └── actions.jsonl    # Reddit platform action log
    ├── simulation.log       # main simulation process log
    └── run_state.json       # run state (for API queries)
"""

# ============================================================
# Fix Windows encoding issues: set UTF-8 encoding before all imports
# This fixes OASIS third-party libraries reading files without an explicit encoding
# ============================================================
import sys
import os

if sys.platform == 'win32':
    # Set the Python default I/O encoding to UTF-8
    # This affects all open() calls that do not specify an encoding
    os.environ.setdefault('PYTHONUTF8', '1')
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    
    # Reconfigure standard output streams to UTF-8 (fixes console text garbling)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    
    # Force the default encoding (affects the default encoding of open())
    # Note: this must be set at Python startup; setting it at runtime may not take effect
    # So we also monkey-patch the built-in open function
    import builtins
    _original_open = builtins.open
    
    def _utf8_open(file, mode='r', buffering=-1, encoding=None, errors=None, 
                   newline=None, closefd=True, opener=None):
        """
        Wrap the open() function to default to UTF-8 encoding for text mode
        This fixes third-party libraries (e.g. OASIS) reading files without an explicit encoding
        """
        # Only set a default encoding for text mode (non-binary) when none is specified
        if encoding is None and 'b' not in mode:
            encoding = 'utf-8'
        return _original_open(file, mode, buffering, encoding, errors, 
                              newline, closefd, opener)
    
    builtins.open = _utf8_open

import argparse
import asyncio
import json
import multiprocessing
import signal
import warnings
from datetime import datetime
from typing import Optional


# Add the lib directory to the path (shared bootstrap — see scripts/lib/paths.py)
_lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib')
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from paths import init_script_paths

_scripts_dir, _backend_dir, _project_root = init_script_paths(__file__)

# Load the .env file from the project root (contains LLM_API_KEY and other configuration)
from dotenv import load_dotenv
_env_file = os.path.join(_project_root, '.env')
if os.path.exists(_env_file):
    load_dotenv(_env_file)
    print(f"Loaded environment config: {_env_file}")
else:
    # Try loading backend/.env
    _backend_env = os.path.join(_backend_dir, '.env')
    if os.path.exists(_backend_env):
        load_dotenv(_backend_env)
        print(f"Loaded environment config: {_backend_env}")


from action_logger import SimulationLogManager


try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from app.services.simulation_tools import ToolRegistry, ToolCallLogger, set_effect_engine
    from app.services.simulation_effects import EffectEngine
except ImportError:
    ToolRegistry = None
    ToolCallLogger = None
    EffectEngine = None
    set_effect_engine = None


import logging_setup  # noqa: F401  (side-effect import: installs MaxTokensWarningFilter at module load)
from logging_setup import init_logging_for_simulation

import platform_runners

from config_utils import get_agent_names_from_config, load_config
from ipc import ParallelIPCHandler
from platform_runners import PlatformSimulation, run_reddit_simulation, run_twitter_simulation


async def main():
    parser = argparse.ArgumentParser(description='OASIS dual-platform parallel simulation')
    parser.add_argument(
        '--config', 
        type=str, 
        required=True,
        help='Path to the config file (simulation_config.json)'
    )
    parser.add_argument(
        '--twitter-only',
        action='store_true',
        help='Run only the Twitter simulation'
    )
    parser.add_argument(
        '--reddit-only',
        action='store_true',
        help='Run only the Reddit simulation'
    )
    parser.add_argument(
        '--max-rounds',
        type=int,
        default=None,
        help='Maximum simulation rounds (optional, used to cap overly long simulations)'
    )
    parser.add_argument(
        '--no-wait',
        action='store_true',
        default=False,
        help='Close the environment immediately after the simulation completes, without entering wait-for-command mode'
    )
    
    args = parser.parse_args()
    
    # Create the shutdown event at the start of main so the whole program can respond to exit signals
    platform_runners._shutdown_event = asyncio.Event()
    
    if not os.path.exists(args.config):
        print(f"Error: config file not found: {args.config}")
        sys.exit(1)
    
    config = load_config(args.config)
    simulation_dir = os.path.dirname(args.config) or "."
    wait_for_commands = not args.no_wait
    
    # Initialize logging config (disable OASIS logging, clean up old files)
    init_logging_for_simulation(simulation_dir)
    
    # Create the log manager
    log_manager = SimulationLogManager(simulation_dir)
    twitter_logger = log_manager.get_twitter_logger()
    reddit_logger = log_manager.get_reddit_logger()
    
    log_manager.info("=" * 60)
    log_manager.info("OASIS dual-platform parallel simulation")
    log_manager.info(f"Config file: {args.config}")
    log_manager.info(f"Simulation ID: {config.get('simulation_id', 'unknown')}")
    log_manager.info(f"Wait-for-command mode: {'enabled' if wait_for_commands else 'disabled'}")
    log_manager.info("=" * 60)
    
    time_config = config.get("time_config", {})
    time_scale = time_config.get("time_scale", {})
    ts_unit = time_scale.get("unit", "hour")

    if ts_unit != "hour":
        config_total_rounds = time_scale.get("total_duration", 60) // max(1, time_scale.get("per_round", 1))
        log_manager.info(f"Simulation parameters:")
        log_manager.info(f"  - Time scale: 1 round = {time_scale.get('per_round', 1)} {ts_unit}(s)")
        log_manager.info(f"  - Total duration: {time_scale.get('total_duration', 60)} {ts_unit}s")
        log_manager.info(f"  - Configured total rounds: {config_total_rounds}")
        phases = time_config.get("phases", [])
        if phases:
            for p in phases:
                if isinstance(p, dict):
                    log_manager.info(f"  - Phase: {p.get('name','')} (R{p.get('start_round','?')}-R{p.get('end_round','?')}) x{p.get('activity_multiplier', 1.0)}")
    else:
        total_hours = time_config.get('total_simulation_hours', 72)
        minutes_per_round = time_config.get('minutes_per_round', 30)
        config_total_rounds = (total_hours * 60) // minutes_per_round
        log_manager.info(f"Simulation parameters:")
        log_manager.info(f"  - Total simulation duration: {total_hours} hours")
        log_manager.info(f"  - Minutes per round: {minutes_per_round}")
        log_manager.info(f"  - Configured total rounds: {config_total_rounds}")
    if args.max_rounds:
        log_manager.info(f"  - Max rounds limit: {args.max_rounds}")
        if args.max_rounds < config_total_rounds:
            log_manager.info(f"  - Actual rounds executed: {args.max_rounds} (truncated)")
    log_manager.info(f"  - Agent count: {len(config.get('agent_configs', []))}")
    
    log_manager.info("Log structure:")
    log_manager.info(f"  - Main log: simulation.log")
    log_manager.info(f"  - Twitter actions: twitter/actions.jsonl")
    log_manager.info(f"  - Reddit actions: reddit/actions.jsonl")
    log_manager.info("=" * 60)
    
    # Build tool registry (opt-in: only if ToolRegistry is available and
    # the config contains a simulation_requirement)
    tool_reg = None
    effect_eng = None
    if ToolRegistry is not None:
        enable_tools = config.get("enable_agent_tools", True)
        sim_req = config.get("simulation_requirement", "")
        if enable_tools and sim_req:
            log_manager.info("Building agent tool registry...")
            tool_reg = ToolRegistry(config, sim_req, enable_tools=True)
            tool_reg.build(progress_callback=lambda msg: log_manager.info(f"  [Tools] {msg}"))
            tool_info = tool_reg.to_dict()
            log_manager.info(f"  Scenario tools: {[t['name'] for t in tool_info['scenario_tools']]}")
            log_manager.info(f"  Role assignments: {tool_info['role_assignments']}")
            tools_path = os.path.join(simulation_dir, "tool_registry.json")
            with open(tools_path, "w", encoding="utf-8") as f:
                json.dump(tool_info, f, ensure_ascii=False, indent=2)
            if ToolCallLogger is not None:
                ToolCallLogger.clear_instances()
                ToolCallLogger.get_or_create(simulation_dir)
                ToolCallLogger.set_active(simulation_dir)
            if set_effect_engine is not None:
                set_effect_engine(None)

            # Initialize effect engine for write-back tool effects
            if EffectEngine is not None:
                agent_names = get_agent_names_from_config(config)
                effect_eng = EffectEngine(config, agent_names, simulation_dir)
                if set_effect_engine is not None:
                    set_effect_engine(effect_eng)
                has_effects = any(
                    t.get("effects") for t in tool_info.get("scenario_tools", [])
                )
                log_manager.info(f"  Effect engine: initialized (tools with effects: {has_effects})")
    
    start_time = datetime.now()
    
    # Store the simulation results for both platforms
    twitter_result: Optional[PlatformSimulation] = None
    reddit_result: Optional[PlatformSimulation] = None
    
    run_sequential = os.environ.get("OASIS_SEQUENTIAL_PLATFORMS", "1") == "1"

    if args.twitter_only:
        twitter_result = await run_twitter_simulation(config, simulation_dir, twitter_logger, log_manager, args.max_rounds, tool_registry=tool_reg, effect_engine=effect_eng)
    elif args.reddit_only:
        reddit_result = await run_reddit_simulation(config, simulation_dir, reddit_logger, log_manager, args.max_rounds, tool_registry=tool_reg, effect_engine=effect_eng)
    elif run_sequential:
        log_manager.info("Running platforms sequentially to stay within API rate limits")
        twitter_result = await run_twitter_simulation(config, simulation_dir, twitter_logger, log_manager, args.max_rounds, tool_registry=tool_reg, effect_engine=effect_eng)
        reddit_result = await run_reddit_simulation(config, simulation_dir, reddit_logger, log_manager, args.max_rounds, tool_registry=tool_reg, effect_engine=effect_eng)
    else:
        results = await asyncio.gather(
            run_twitter_simulation(config, simulation_dir, twitter_logger, log_manager, args.max_rounds, tool_registry=tool_reg, effect_engine=effect_eng),
            run_reddit_simulation(config, simulation_dir, reddit_logger, log_manager, args.max_rounds, tool_registry=tool_reg, effect_engine=effect_eng),
        )
        twitter_result, reddit_result = results
    
    total_elapsed = (datetime.now() - start_time).total_seconds()
    log_manager.info("=" * 60)
    log_manager.info(f"Simulation loop complete! Total elapsed: {total_elapsed:.1f}s")
    
    # Whether to enter command-wait mode
    if wait_for_commands:
        log_manager.info("")
        log_manager.info("=" * 60)
        log_manager.info("Entering command-wait mode - environments remain running")
        log_manager.info("Supported commands: interview, batch_interview, close_env")
        log_manager.info("=" * 60)
        
        # Create the IPC handler
        ipc_handler = ParallelIPCHandler(
            simulation_dir=simulation_dir,
            twitter_env=twitter_result.env if twitter_result else None,
            twitter_agent_graph=twitter_result.agent_graph if twitter_result else None,
            reddit_env=reddit_result.env if reddit_result else None,
            reddit_agent_graph=reddit_result.agent_graph if reddit_result else None
        )
        ipc_handler.update_status("alive")
        
        # Command-wait loop (uses the global platform_runners._shutdown_event)
        try:
            while not platform_runners._shutdown_event.is_set():
                should_continue = await ipc_handler.process_commands()
                if not should_continue:
                    break
                # Use wait_for instead of sleep so we can respond to shutdown_event
                try:
                    await asyncio.wait_for(platform_runners._shutdown_event.wait(), timeout=0.5)
                    break  # received exit signal
                except asyncio.TimeoutError:
                    pass  # timeout, keep looping
        except KeyboardInterrupt:
            print("\nReceived interrupt signal")
        except asyncio.CancelledError:
            print("\nTask cancelled")
        except Exception as e:
            print(f"\nCommand processing error: {e}")
        
        log_manager.info("\nClosing environments...")
        ipc_handler.update_status("stopped")
    
    # Close the environments
    if twitter_result and twitter_result.env:
        await twitter_result.env.close()
        log_manager.info("[Twitter] Environment closed")
    
    if reddit_result and reddit_result.env:
        await reddit_result.env.close()
        log_manager.info("[Reddit] Environment closed")
    
    log_manager.info("=" * 60)
    log_manager.info(f"All done!")
    log_manager.info(f"Log files:")
    log_manager.info(f"  - {os.path.join(simulation_dir, 'simulation.log')}")
    log_manager.info(f"  - {os.path.join(simulation_dir, 'twitter', 'actions.jsonl')}")
    log_manager.info(f"  - {os.path.join(simulation_dir, 'reddit', 'actions.jsonl')}")
    log_manager.info("=" * 60)


def setup_signal_handlers(loop=None):
    """
    Set up signal handlers so SIGTERM/SIGINT exit cleanly.
    
    Persistent simulation scenario: after the simulation completes the process
    keeps running and waits for interview commands. When a termination
    signal is received, we need to:
    1. Notify the asyncio loop to stop waiting
    2. Give the program a chance to clean up resources (close databases, environments, etc.)
    3. Then exit
    """
    def signal_handler(signum, frame):
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        print(f"\nReceived {sig_name} signal, shutting down...")
        
        if not platform_runners._cleanup_done:
            platform_runners._cleanup_done = True
            # Set the event to notify the asyncio loop to exit (so the loop can clean up resources)
            if platform_runners._shutdown_event:
                platform_runners._shutdown_event.set()
        
        # Do not call sys.exit() directly; let the asyncio loop exit normally and clean up resources
        # Only force exit if the signal is received a second time
        else:
            print("Forcing exit...")
            sys.exit(1)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


if __name__ == "__main__":
    setup_signal_handlers()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted")
    except SystemExit:
        pass
    finally:
        # Clean up the multiprocessing resource tracker (to avoid warnings on exit)
        try:
            from multiprocessing import resource_tracker
            resource_tracker._resource_tracker._stop()
        except Exception:
            pass
        print("Simulation process exited")
