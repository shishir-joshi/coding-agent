from __future__ import annotations

import shlex
from dataclasses import dataclass

from .agent_loop import Agent, AgentConfig
from .history import HistoryStore


@dataclass
class ReplConfig:
	history_path: str = ".agent/history.jsonl"


HELP_TEXT = """Commands:
  /help                 Show this help
  /context              Print current LLM context (all messages)
	/tools [json]         Show available tools (add 'json' to show full schemas)
  /history [n]          Print last n history events (default 10)
  /reset                Reset in-memory context
  /exit                 Quit

Type anything else to chat.
"""


def run_repl(*, agent_config: AgentConfig | None = None, history_path: str | None = None) -> None:
	cfg = ReplConfig(history_path=history_path or ReplConfig().history_path)
	history = HistoryStore(cfg.history_path)
	agent = Agent(history=history, config=agent_config)

	print("Tiny Agent REPL. Type /help for commands.")

	while True:
		try:
			raw = input("> ").rstrip("\n")
		except (EOFError, KeyboardInterrupt):
			print("\nbye")
			return

		if not raw.strip():
			continue

		if raw.startswith("/"):
			if _handle_command(raw, agent, history):
				return
			continue

		answer = agent.chat(raw)
		print(answer)


def _handle_command(raw: str, agent: Agent, history: HistoryStore) -> bool:
	parts = shlex.split(raw)
	cmd = parts[0]

	if cmd == "/exit":
		return True
	if cmd == "/help":
		print(HELP_TEXT)
		return False
	if cmd == "/reset":
		agent.reset()
		print("(context reset)")
		return False
	if cmd == "/context":
		print(agent.dump_context())
		return False
	if cmd == "/tools":
		as_json = len(parts) > 1 and parts[1].lower() == "json"
		print(agent.dump_tools(as_json=as_json))
		return False
	if cmd == "/history":
		n = 10
		if len(parts) > 1:
			try:
				n = int(parts[1])
			except ValueError:
				print("usage: /history [n]")
				return False
		print(history.tail(n))
		return False

	print("unknown command; try /help")
	return False
