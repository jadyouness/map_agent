import argparse
import asyncio
from part2_implementation.agent_sdk_app import AgentsSDKMapAssistant


def main():
    parser = argparse.ArgumentParser(description="Agents SDK Map Assistant demo")
    parser.add_argument("prompt", nargs="?", default="Find a driving route from Beirut to Tripoli",
                        help="User question for the agent")
    args = parser.parse_args()

    agent = AgentsSDKMapAssistant()
    result = asyncio.run(agent.run(args.prompt))
    print(result)


if __name__ == "__main__":
    main()

