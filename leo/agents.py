"""Builds the four distinct CrewAI agents (each with its own role, prompt and behaviour)."""
from crewai import Agent, LLM

from . import config, prompts
from .tools import calculator


def make_llm() -> LLM:
    return LLM(model=config.MODEL_NAME, api_key=config.get_api_key(), temperature=0.4)


def _agent(key: str, llm: LLM, tools=None) -> Agent:
    p = prompts.ROLES[key]
    return Agent(
        role=p["role"], goal=p["goal"], backstory=p["backstory"],
        llm=llm, tools=tools or [],
        allow_delegation=False,            # delegation is done by the Coordinator's plan + pipeline
        verbose=config.VERBOSE,
        max_iter=config.MAX_ITER,          # stops runaway reasoning loops
        max_retry_limit=2,                 # agent-level retry
        max_execution_time=config.AGENT_TIMEOUT,  # stall protection (seconds)
    )


def build_agents(llm: LLM) -> dict:
    tools = [calculator] if config.USE_TOOLS else []
    return {
        "coordinator": _agent("coordinator", llm),
        "explainer": _agent("explainer", llm, tools),
        "quiz_master": _agent("quiz_master", llm),
        "evaluator": _agent("evaluator", llm, tools),
    }
