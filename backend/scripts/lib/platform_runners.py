"""Platform simulation runners (Twitter/Reddit) for the parallel simulation runner."""

import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional  # noqa: UP035

from action_logger import PlatformActionLogger, SimulationLogManager
from agent_graphs import (
    generate_reddit_agent_graph_with_tools,
    generate_twitter_agent_graph_with_tools,
)
from config_utils import get_agent_names_from_config
from db_utils import fetch_new_actions_from_db, fetch_new_tool_calls
from model_factory import create_model
from time_utils import compute_time_label, get_active_agents_for_round

try:
    import oasis
    from oasis import (
        ActionType,
        LLMAction,
        ManualAction,
    )
except ImportError as e:
    print(f"Error: missing dependency {e}")
    print("Please install first: pip install oasis-ai camel-ai")
    sys.exit(1)


# Global variables for signal handling
_shutdown_event = None
_cleanup_done = False

# Twitter available actions (INTERVIEW excluded; it can only be triggered manually via ManualAction)
TWITTER_ACTIONS = [
    ActionType.CREATE_POST,
    ActionType.LIKE_POST,
    ActionType.REPOST,
    ActionType.FOLLOW,
    ActionType.DO_NOTHING,
    ActionType.QUOTE_POST,
]

# Reddit available actions (INTERVIEW excluded; it can only be triggered manually via ManualAction)
REDDIT_ACTIONS = [
    ActionType.LIKE_POST,
    ActionType.DISLIKE_POST,
    ActionType.CREATE_POST,
    ActionType.CREATE_COMMENT,
    ActionType.LIKE_COMMENT,
    ActionType.DISLIKE_COMMENT,
    ActionType.SEARCH_POSTS,
    ActionType.SEARCH_USER,
    ActionType.TREND,
    ActionType.REFRESH,
    ActionType.DO_NOTHING,
    ActionType.FOLLOW,
    ActionType.MUTE,
]

class PlatformSimulation:
    """Container for a platform simulation result"""
    def __init__(self):
        self.env = None
        self.agent_graph = None
        self.total_actions = 0


async def run_twitter_simulation(
    config: Dict[str, Any], 
    simulation_dir: str,
    action_logger: Optional[PlatformActionLogger] = None,
    main_logger: Optional[SimulationLogManager] = None,
    max_rounds: Optional[int] = None,
    tool_registry=None,
    effect_engine=None,
) -> PlatformSimulation:
    """Run the Twitter simulation
    
    Args:
        config: simulation config
        simulation_dir: simulation directory
        action_logger: action log recorder
        main_logger: main log manager
        max_rounds: maximum simulation rounds (optional, to truncate overly long simulations)
        
    Returns:
        PlatformSimulation: result object containing env and agent_graph
    """
    result = PlatformSimulation()
    
    def log_info(msg):
        if main_logger:
            main_logger.info(f"[Twitter] {msg}")
        print(f"[Twitter] {msg}")
    
    log_info("Initializing...")
    
    # Twitter uses the general LLM config
    model = create_model(config, use_boost=False)
    
    # OASIS Twitter uses CSV format
    profile_path = os.path.join(simulation_dir, "twitter_profiles.csv")
    if not os.path.exists(profile_path):
        log_info(f"Error: Profile file not found: {profile_path}")
        return result
    
    result.agent_graph = await generate_twitter_agent_graph_with_tools(
        profile_path=profile_path,
        model=model,
        available_actions=TWITTER_ACTIONS,
        tool_registry=tool_registry,
    )
    
    if tool_registry is not None:
        role_map = tool_registry.role_map
        tool_count = sum(1 for r in role_map.values() if r != "none")
        log_info(f"Tool-enhanced agents: {tool_count}/{result.agent_graph.get_num_nodes()}")
    
    # Get real agent names from the config (use entity_name instead of the default Agent_X)
    agent_names = get_agent_names_from_config(config)
    # Fall back to OASIS's default name for agents missing from the config
    for agent_id, agent in result.agent_graph.get_agents():
        if agent_id not in agent_names:
            agent_names[agent_id] = getattr(agent, 'name', f'Agent_{agent_id}')
    
    db_path = os.path.join(simulation_dir, "twitter_simulation.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    
    llm_semaphore = int(os.environ.get("OASIS_LLM_SEMAPHORE", "5"))
    result.env = oasis.make(
        agent_graph=result.agent_graph,
        platform=oasis.DefaultPlatformType.TWITTER,
        database_path=db_path,
        semaphore=llm_semaphore,
    )
    
    await result.env.reset()
    log_info("Environment started")

    if effect_engine:
        effect_engine.set_env(result.env, result.agent_graph, "twitter")
    
    if action_logger:
        action_logger.log_simulation_start(config)
    
    total_actions = 0
    last_rowid = 0
    
    event_config = config.get("event_config", {})
    initial_posts = event_config.get("initial_posts", [])
    
    if action_logger:
        action_logger.log_round_start(0, 0)
    
    initial_action_count = 0
    if initial_posts:
        initial_actions = {}
        for post in initial_posts:
            agent_id = post.get("poster_agent_id", 0)
            content = post.get("content", "")
            try:
                agent = result.env.agent_graph.get_agent(agent_id)
                initial_actions[agent] = ManualAction(
                    action_type=ActionType.CREATE_POST,
                    action_args={"content": content}
                )
                
                if action_logger:
                    action_logger.log_action(
                        round_num=0,
                        agent_id=agent_id,
                        agent_name=agent_names.get(agent_id, f"Agent_{agent_id}"),
                        action_type="CREATE_POST",
                        action_args={"content": content}
                    )
                    total_actions += 1
                    initial_action_count += 1
            except Exception:
                pass
        
        if initial_actions:
            await result.env.step(initial_actions)
            log_info(f"Published {len(initial_actions)} initial posts")
    
    if action_logger:
        action_logger.log_round_end(0, initial_action_count)
    
    time_config = config.get("time_config", {})
    time_scale = time_config.get("time_scale", {})
    ts_unit = time_scale.get("unit", "hour")

    if ts_unit != "hour":
        total_rounds = time_scale.get("total_duration", 60) // max(1, time_scale.get("per_round", 1))
    else:
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)
        total_rounds = (total_hours * 60) // minutes_per_round

    if max_rounds is not None and max_rounds > 0:
        original_rounds = total_rounds
        total_rounds = min(total_rounds, max_rounds)
        if total_rounds < original_rounds:
            log_info(f"Rounds truncated: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")

    minutes_per_round = time_config.get("minutes_per_round", 30)
    start_time = datetime.now()

    for round_num in range(total_rounds):
        if _shutdown_event and _shutdown_event.is_set():
            if main_logger:
                main_logger.info(f"Received exit signal, stopping simulation at round {round_num + 1}")
            break

        simulated_minutes = round_num * minutes_per_round
        simulated_hour = (simulated_minutes // 60) % 24
        simulated_day = simulated_minutes // (60 * 24) + 1

        time_label = compute_time_label(round_num, time_scale)

        active_agents = get_active_agents_for_round(
            result.env, config, simulated_hour, round_num
        )

        if action_logger:
            action_logger.log_round_start(round_num + 1, simulated_hour, time_label=time_label)

        elapsed_sim_hours = (
            simulated_minutes / 60 if ts_unit == "hour" else 0
        )

        if not active_agents:
            if action_logger:
                action_logger.log_round_end(round_num + 1, 0, time_label=time_label, simulated_hours=elapsed_sim_hours)
            continue

        # Inject time context into agent system messages
        for _, agent in active_agents:
            if hasattr(agent, 'system_message') and agent.system_message is not None:
                if not hasattr(agent, '_original_system_content'):
                    agent._original_system_content = agent.system_message.content
                agent.system_message.content = (
                    f"[CURRENT SIMULATED TIME: {time_label['label']}]\n\n"
                    + agent._original_system_content
                )

        actions = {agent: LLMAction() for _, agent in active_agents}
        await result.env.step(actions)

        actual_actions, last_rowid = fetch_new_actions_from_db(
            db_path, last_rowid, agent_names
        )

        tool_actions = fetch_new_tool_calls(simulation_dir, agent_names, platform="twitter")
        actual_actions = tool_actions + actual_actions

        if effect_engine:
            applied = effect_engine.apply_pending(round_num + 1, "twitter")
            if applied:
                state_actions = effect_engine.to_action_dicts(applied, agent_names)
                actual_actions.extend(state_actions)
                log_info(f"Round {round_num + 1}: Applied {len(applied)} state effects")

        round_action_count = 0
        for action_data in actual_actions:
            action_data["time_label"] = time_label.get("label", "")
            if action_logger:
                action_logger.log_action(
                    round_num=round_num + 1,
                    agent_id=action_data['agent_id'],
                    agent_name=action_data['agent_name'],
                    action_type=action_data['action_type'],
                    action_args=action_data['action_args']
                )
                total_actions += 1
                round_action_count += 1

        if action_logger:
            action_logger.log_round_end(round_num + 1, round_action_count, time_label=time_label, simulated_hours=elapsed_sim_hours)

        if (round_num + 1) % 20 == 0:
            progress = (round_num + 1) / total_rounds * 100
            if ts_unit != "hour":
                log_info(f"{time_label['label']} - Round {round_num + 1}/{total_rounds} ({progress:.1f}%)")
            else:
                log_info(f"Day {simulated_day}, {simulated_hour:02d}:00 - Round {round_num + 1}/{total_rounds} ({progress:.1f}%)")

    if action_logger:
        action_logger.log_simulation_end(total_rounds, total_actions)

    result.total_actions = total_actions
    elapsed = (datetime.now() - start_time).total_seconds()
    log_info(f"Simulation loop complete! Elapsed: {elapsed:.1f}s, total actions: {total_actions}")

    return result


async def run_reddit_simulation(
    config: Dict[str, Any], 
    simulation_dir: str,
    action_logger: Optional[PlatformActionLogger] = None,
    main_logger: Optional[SimulationLogManager] = None,
    max_rounds: Optional[int] = None,
    tool_registry=None,
    effect_engine=None,
) -> PlatformSimulation:
    """Run the Reddit simulation
    
    Args:
        config: simulation config
        simulation_dir: simulation directory
        action_logger: action log recorder
        main_logger: main log manager
        max_rounds: maximum simulation rounds (optional, to truncate overly long simulations)
        
    Returns:
        PlatformSimulation: result object containing env and agent_graph
    """
    result = PlatformSimulation()
    
    def log_info(msg):
        if main_logger:
            main_logger.info(f"[Reddit] {msg}")
        print(f"[Reddit] {msg}")
    
    log_info("Initializing...")
    
    # Reddit uses the boost LLM config (if available, otherwise falls back to the general config)
    model = create_model(config, use_boost=True)
    
    profile_path = os.path.join(simulation_dir, "reddit_profiles.json")
    if not os.path.exists(profile_path):
        log_info(f"Error: Profile file not found: {profile_path}")
        return result
    
    result.agent_graph = await generate_reddit_agent_graph_with_tools(
        profile_path=profile_path,
        model=model,
        available_actions=REDDIT_ACTIONS,
        tool_registry=tool_registry,
    )
    
    if tool_registry is not None:
        role_map = tool_registry.role_map
        tool_count = sum(1 for r in role_map.values() if r != "none")
        log_info(f"Tool-enhanced agents: {tool_count}/{result.agent_graph.get_num_nodes()}")
    
    # Get real agent names from the config (use entity_name instead of the default Agent_X)
    agent_names = get_agent_names_from_config(config)
    # Fall back to OASIS's default name for agents missing from the config
    for agent_id, agent in result.agent_graph.get_agents():
        if agent_id not in agent_names:
            agent_names[agent_id] = getattr(agent, 'name', f'Agent_{agent_id}')
    
    db_path = os.path.join(simulation_dir, "reddit_simulation.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    
    llm_semaphore = int(os.environ.get("OASIS_LLM_SEMAPHORE", "5"))
    result.env = oasis.make(
        agent_graph=result.agent_graph,
        platform=oasis.DefaultPlatformType.REDDIT,
        database_path=db_path,
        semaphore=llm_semaphore,
    )
    
    await result.env.reset()
    log_info("Environment started")

    if effect_engine:
        effect_engine.set_env(result.env, result.agent_graph, "reddit")
    
    if action_logger:
        action_logger.log_simulation_start(config)
    
    total_actions = 0
    last_rowid = 0
    
    event_config = config.get("event_config", {})
    initial_posts = event_config.get("initial_posts", [])
    
    if action_logger:
        action_logger.log_round_start(0, 0)
    
    initial_action_count = 0
    if initial_posts:
        initial_actions = {}
        for post in initial_posts:
            agent_id = post.get("poster_agent_id", 0)
            content = post.get("content", "")
            try:
                agent = result.env.agent_graph.get_agent(agent_id)
                if agent in initial_actions:
                    if not isinstance(initial_actions[agent], list):
                        initial_actions[agent] = [initial_actions[agent]]
                    initial_actions[agent].append(ManualAction(
                        action_type=ActionType.CREATE_POST,
                        action_args={"content": content}
                    ))
                else:
                    initial_actions[agent] = ManualAction(
                        action_type=ActionType.CREATE_POST,
                        action_args={"content": content}
                    )
                
                if action_logger:
                    action_logger.log_action(
                        round_num=0,
                        agent_id=agent_id,
                        agent_name=agent_names.get(agent_id, f"Agent_{agent_id}"),
                        action_type="CREATE_POST",
                        action_args={"content": content}
                    )
                    total_actions += 1
                    initial_action_count += 1
            except Exception:
                pass
        
        if initial_actions:
            await result.env.step(initial_actions)
            log_info(f"Published {len(initial_actions)} initial posts")
    
    if action_logger:
        action_logger.log_round_end(0, initial_action_count)
    
    time_config = config.get("time_config", {})
    time_scale = time_config.get("time_scale", {})
    ts_unit = time_scale.get("unit", "hour")

    if ts_unit != "hour":
        total_rounds = time_scale.get("total_duration", 60) // max(1, time_scale.get("per_round", 1))
    else:
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)
        total_rounds = (total_hours * 60) // minutes_per_round

    if max_rounds is not None and max_rounds > 0:
        original_rounds = total_rounds
        total_rounds = min(total_rounds, max_rounds)
        if total_rounds < original_rounds:
            log_info(f"Rounds truncated: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")

    minutes_per_round = time_config.get("minutes_per_round", 30)
    start_time = datetime.now()

    for round_num in range(total_rounds):
        if _shutdown_event and _shutdown_event.is_set():
            if main_logger:
                main_logger.info(f"Received exit signal, stopping simulation at round {round_num + 1}")
            break

        simulated_minutes = round_num * minutes_per_round
        simulated_hour = (simulated_minutes // 60) % 24
        simulated_day = simulated_minutes // (60 * 24) + 1

        time_label = compute_time_label(round_num, time_scale)

        active_agents = get_active_agents_for_round(
            result.env, config, simulated_hour, round_num
        )

        if action_logger:
            action_logger.log_round_start(round_num + 1, simulated_hour, time_label=time_label)

        elapsed_sim_hours = (
            simulated_minutes / 60 if ts_unit == "hour" else 0
        )

        if not active_agents:
            if action_logger:
                action_logger.log_round_end(round_num + 1, 0, time_label=time_label, simulated_hours=elapsed_sim_hours)
            continue

        for _, agent in active_agents:
            if hasattr(agent, 'system_message') and agent.system_message is not None:
                if not hasattr(agent, '_original_system_content'):
                    agent._original_system_content = agent.system_message.content
                agent.system_message.content = (
                    f"[CURRENT SIMULATED TIME: {time_label['label']}]\n\n"
                    + agent._original_system_content
                )

        actions = {agent: LLMAction() for _, agent in active_agents}
        await result.env.step(actions)

        actual_actions, last_rowid = fetch_new_actions_from_db(
            db_path, last_rowid, agent_names
        )

        tool_actions = fetch_new_tool_calls(simulation_dir, agent_names, platform="reddit")
        actual_actions = tool_actions + actual_actions

        if effect_engine:
            applied = effect_engine.apply_pending(round_num + 1, "reddit")
            if applied:
                state_actions = effect_engine.to_action_dicts(applied, agent_names)
                actual_actions.extend(state_actions)
                log_info(f"Round {round_num + 1}: Applied {len(applied)} state effects")

        round_action_count = 0
        for action_data in actual_actions:
            action_data["time_label"] = time_label.get("label", "")
            if action_logger:
                action_logger.log_action(
                    round_num=round_num + 1,
                    agent_id=action_data['agent_id'],
                    agent_name=action_data['agent_name'],
                    action_type=action_data['action_type'],
                    action_args=action_data['action_args']
                )
                total_actions += 1
                round_action_count += 1

        if action_logger:
            action_logger.log_round_end(round_num + 1, round_action_count, time_label=time_label, simulated_hours=elapsed_sim_hours)

        if (round_num + 1) % 20 == 0:
            progress = (round_num + 1) / total_rounds * 100
            if ts_unit != "hour":
                log_info(f"{time_label['label']} - Round {round_num + 1}/{total_rounds} ({progress:.1f}%)")
            else:
                log_info(f"Day {simulated_day}, {simulated_hour:02d}:00 - Round {round_num + 1}/{total_rounds} ({progress:.1f}%)")

    if action_logger:
        action_logger.log_simulation_end(total_rounds, total_actions)

    result.total_actions = total_actions
    elapsed = (datetime.now() - start_time).total_seconds()
    log_info(f"Simulation loop complete! Elapsed: {elapsed:.1f}s, total actions: {total_actions}")

    return result


