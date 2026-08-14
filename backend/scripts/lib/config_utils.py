"""Configuration loading helpers for the parallel simulation runner."""

import json
from typing import Any, Dict  # noqa: UP035

def load_config(config_path: str) -> Dict[str, Any]:
    """Load a config file"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_agent_names_from_config(config: Dict[str, Any]) -> Dict[int, str]:
    """
    Build an agent_id -> entity_name mapping from the simulation config
    
    This lets actions.jsonl show real entity names instead of placeholders like "Agent_0"
    
    Args:
        config: contents of simulation_config.json
        
    Returns:
        a dict mapping agent_id -> entity_name
    """
    agent_names = {}
    agent_configs = config.get("agent_configs", [])
    
    for agent_config in agent_configs:
        agent_id = agent_config.get("agent_id")
        entity_name = agent_config.get("entity_name", f"Agent_{agent_id}")
        if agent_id is not None:
            agent_names[agent_id] = entity_name
    
    return agent_names


