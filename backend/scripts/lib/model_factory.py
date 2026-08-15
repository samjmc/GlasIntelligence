"""LLM model factory for the parallel simulation runner."""

import os
import sys
from typing import Any  # noqa: UP035

try:
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType
except ImportError as e:
    print(f"Error: missing dependency {e}")
    print("Please install first: pip install oasis-ai camel-ai")
    sys.exit(1)

def create_model(config: dict[str, Any], use_boost: bool = False):
    """
    Create an LLM model

    Supports a dual-LLM configuration for faster parallel simulations:
    - General config: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME
    - Boost config (optional): LLM_BOOST_API_KEY, LLM_BOOST_BASE_URL, LLM_BOOST_MODEL_NAME

    When a boost LLM is configured, parallel simulations can use different API
    providers per platform to improve concurrency.

    Args:
        config: simulation config dict
        use_boost: whether to use the boost LLM config (if available)
    """
    # Check whether a boost config is available
    boost_api_key = os.environ.get("LLM_BOOST_API_KEY", "")
    boost_base_url = os.environ.get("LLM_BOOST_BASE_URL", "")
    boost_model = os.environ.get("LLM_BOOST_MODEL_NAME", "")
    has_boost_config = bool(boost_api_key)

    # Pick which LLM to use based on the parameter and the config
    if use_boost and has_boost_config:
        # Use the boost config
        llm_api_key = boost_api_key
        llm_base_url = boost_base_url
        llm_model = boost_model or os.environ.get("LLM_MODEL_NAME", "")
        config_label = "[BOOST LLM]"
    else:
        # Use the general config
        llm_api_key = os.environ.get("LLM_API_KEY", "")
        llm_base_url = os.environ.get("LLM_BASE_URL", "")
        llm_model = os.environ.get("LLM_MODEL_NAME", "")
        config_label = "[GENERAL LLM]"

    # If no model name is set in .env, fall back to the config
    if not llm_model:
        llm_model = config.get("llm_model", "gpt-4o-mini")

    # Set the environment variables camel-ai requires
    if llm_api_key:
        os.environ["OPENAI_API_KEY"] = llm_api_key

    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("Missing API key config: set LLM_API_KEY in the .env file at the project root")

    if llm_base_url:
        os.environ["OPENAI_API_BASE_URL"] = llm_base_url

    print(f"{config_label} model={llm_model}, base_url={llm_base_url[:40] if llm_base_url else 'default'}...")

    # Platform derived from the key type: Anthropic keys (sk-ant-*) must
    # use the ANTHROPIC backend — hardcoding OPENAI 401s on every agent
    # call and produces a silently empty simulation (found 2026-08-14,
    # V9 verification: 26 rounds, zero actions).
    if llm_api_key.startswith("sk-ant-"):
        os.environ["ANTHROPIC_API_KEY"] = llm_api_key
        return ModelFactory.create(
            model_platform=ModelPlatformType.ANTHROPIC,
            model_type=llm_model,
            api_key=llm_api_key,
        )

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type=llm_model,
    )


