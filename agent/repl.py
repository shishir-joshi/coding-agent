from __future__ import annotations

import shlex
import os
from dataclasses import dataclass

from .agent_loop import Agent, AgentConfig
from .history import HistoryStore
from .ui import (
	clear_screen,
	get_theme,
	load_ui_config,
	render_app_banner,
	render_markdown,
	run_onboarding,
	save_ui_config,
	supports_color,
)


@dataclass
class ReplConfig:
	history_path: str = ".agent/history.jsonl"
	ui_config_path: str = ".agent/ui.json"


HELP_TEXT = """Commands:
  /help                 Show this help
  /context              Print current LLM context (all messages)
	/tools [json]         Show available tools (add 'json' to show full schemas)
  /history [n]          Print last n history events (default 10)
	/theme                Re-run theme selection
	/clear                Clear the screen
  /reset                Reset in-memory context
  /exit                 Quit

Type anything else to chat.
"""


def run_repl(*, agent_config: AgentConfig | None = None, history_path: str | None = None) -> None:
	cfg = ReplConfig(history_path=history_path or ReplConfig().history_path)
	history = HistoryStore(cfg.history_path)
	agent = Agent(history=history, config=agent_config)

	# UI/theme
	theme = run_onboarding(ui_config_path=cfg.ui_config_path)
	ui_cfg = load_ui_config(cfg.ui_config_path)
	theme = get_theme(ui_cfg.get("theme"))

	print(render_app_banner(theme))
	print("")
	print(theme.a("Tiny Agent REPL") + theme.d(". Type /help for commands."))

	while True:
		try:
			prompt = theme.a("> ") if supports_color() else "> "
			raw = input(prompt).rstrip("\n")
		except (EOFError, KeyboardInterrupt):
			print("\nbye")
			return

		if not raw.strip():
			continue

		if raw.startswith("/"):
			if _handle_command(raw, agent, history, cfg):
				return
			continue

		print(theme.d("* Simmering..."))
		answer = agent.chat(raw)
		print(render_markdown(answer, theme))


def _handle_command(raw: str, agent: Agent, history: HistoryStore, cfg: ReplConfig) -> bool:
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
	if cmd == "/clear":
		clear_screen()
		return False
	if cmd == "/theme":
		# Allow changing theme even if onboarding is disabled.
		os.environ.pop("AGENT_NO_ONBOARDING", None)
		new_theme = run_onboarding(ui_config_path=cfg.ui_config_path)
		ui_cfg = load_ui_config(cfg.ui_config_path)
		ui_cfg["theme"] = new_theme.id
		save_ui_config(cfg.ui_config_path, ui_cfg)
		return False

	print("unknown command; try /help")
	return False
