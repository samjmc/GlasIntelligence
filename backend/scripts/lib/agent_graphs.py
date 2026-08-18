"""Custom OASIS agent graph builders with optional per-agent tool assignment."""

import asyncio
import json
import sys

try:
    from oasis.social_agent import SocialAgent
    try:
        from oasis.social_agent import AgentGraph
    except ImportError:
        from oasis.social_agent.agent_graph import AgentGraph
    try:
        from oasis.social_platform.config import UserInfo
    except ImportError:
        from oasis.social_platform.typing import UserInfo
except ImportError as e:
    print(f"Error: missing dependency {e}")
    print("Please install first: pip install oasis-ai camel-ai")
    sys.exit(1)

async def generate_twitter_agent_graph_with_tools(
    profile_path: str,
    model,
    available_actions,
    tool_registry=None,
):
    """Build a Twitter agent graph with optional per-agent tools.

    When tool_registry is None (or ToolRegistry not available), this
    behaves identically to OASIS's generate_twitter_agent_graph.
    """
    import pandas as pd

    agent_info = pd.read_csv(profile_path)
    agent_graph = AgentGraph()

    for agent_id in range(len(agent_info)):
        profile = {"nodes": [], "edges": [], "other_info": {}}
        profile["other_info"]["user_profile"] = agent_info["user_char"][agent_id]

        user_info = UserInfo(
            name=agent_info["username"][agent_id],
            description=agent_info["description"][agent_id],
            profile=profile,
            recsys_type="twitter",
        )

        agent_kwargs = dict(
            agent_id=agent_id,
            user_info=user_info,
            model=model,
            agent_graph=agent_graph,
            available_actions=available_actions,
        )

        if tool_registry is not None:
            agent_tools = tool_registry.get_tools_for_agent(agent_id, platform="twitter")
            if agent_tools:
                agent_kwargs["tools"] = agent_tools
                agent_kwargs["max_iteration"] = tool_registry.get_max_iterations(agent_id)

        agent = SocialAgent(**agent_kwargs)
        agent_graph.add_agent(agent)

    return agent_graph


async def generate_reddit_agent_graph_with_tools(
    profile_path: str,
    model,
    available_actions,
    tool_registry=None,
):
    """Build a Reddit agent graph with optional per-agent tools.

    When tool_registry is None (or ToolRegistry not available), this
    behaves identically to OASIS's generate_reddit_agent_graph.
    """
    agent_graph = AgentGraph()
    with open(profile_path, "r", encoding="utf-8") as f:
        agent_info = json.load(f)

    async def process_agent(i):
        profile = {"nodes": [], "edges": [], "other_info": {}}
        profile["other_info"]["user_profile"] = agent_info[i]["persona"]
        profile["other_info"]["mbti"] = agent_info[i]["mbti"]
        profile["other_info"]["gender"] = agent_info[i]["gender"]
        profile["other_info"]["age"] = agent_info[i]["age"]
        profile["other_info"]["country"] = agent_info[i]["country"]

        user_info = UserInfo(
            name=agent_info[i]["username"],
            description=agent_info[i]["bio"],
            profile=profile,
            recsys_type="reddit",
        )

        agent_kwargs = dict(
            agent_id=i,
            user_info=user_info,
            agent_graph=agent_graph,
            model=model,
            available_actions=available_actions,
        )

        if tool_registry is not None:
            agent_tools = tool_registry.get_tools_for_agent(i, platform="reddit")
            if agent_tools:
                agent_kwargs["tools"] = agent_tools
                agent_kwargs["max_iteration"] = tool_registry.get_max_iterations(i)

        agent = SocialAgent(**agent_kwargs)
        agent_graph.add_agent(agent)

    tasks = [process_agent(i) for i in range(len(agent_info))]
    await asyncio.gather(*tasks)
    return agent_graph


