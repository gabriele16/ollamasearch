from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent

from ollamasearch.agent_swarm import AgentSwarm, SwarmConfig, load_config

