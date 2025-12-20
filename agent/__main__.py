import argparse

from .agent_loop import AgentConfig
from .repl import run_repl


def main() -> None:
	parser = argparse.ArgumentParser(prog="python -m agent", description="Tiny tool-using LLM agent (learning project)")
	parser.add_argument("--debug", action="store_true", help="Print LLM requests/responses and tool calls/results")
	parser.add_argument("--model", default=None, help="Override model (otherwise uses OPENAI_MODEL)")
	parser.add_argument(
		"--max-tool-rounds",
		type=int,
		default=8,
		help="Maximum tool-call/response iterations per user message",
	)
	parser.add_argument(
		"--history-path",
		default=".agent/history.jsonl",
		help="Where to append JSONL history events",
	)
	parser.add_argument(
		"--no-plan",
		action="store_true",
		help="Disable automatic plan generation for complex tasks",
	)
	args = parser.parse_args()

	agent_cfg = AgentConfig(
		model=args.model,
		max_tool_rounds=args.max_tool_rounds,
		debug=args.debug,
		enable_planning=not args.no_plan,
	)
	run_repl(agent_config=agent_cfg, history_path=args.history_path)


if __name__ == "__main__":
	main()
