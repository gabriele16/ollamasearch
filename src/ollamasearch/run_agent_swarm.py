"""
Console script entrypoint for running the AgentSwarm.
"""
import argparse
import sys
from ollamasearch.agent_swarm import AgentSwarm, SwarmConfig, load_config


def main():
    parser = argparse.ArgumentParser(
        description="Run an AgentSwarm with YAML config via console script."
    )
    parser.add_argument(
        "-c", "--config", required=True,
        help="Path to YAML config file."
    )
    parser.add_argument(
        "-o", "--output", help="Path to output Markdown file."
    )
    args = parser.parse_args()

    config = load_config(args.config)
    if not config.query:
        parser.error("No query provided in config under 'query'.")
    query = config.query

    swarm = AgentSwarm(config)
    result = swarm.run(query)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Answer written to {args.output}")
    else:
        print(result)

if __name__ == "__main__":
    main()
