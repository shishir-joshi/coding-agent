from __future__ import annotations

import atexit
import shlex
import os
from dataclasses import dataclass
from pathlib import Path
import re

from .agent_loop import Agent, AgentConfig
from .history import HistoryStore
from .ui import (
	clear_screen,
	get_theme,
	load_ui_config,
	render_app_banner,
	render_markdown,
	render_system_info,
	run_onboarding,
	save_ui_config,
	supports_color,
)


@dataclass
class ReplConfig:
	history_path: str = ".agent/history.jsonl"
	ui_config_path: str = ".agent/ui.json"
	repl_history_path: str = ".agent/repl_history"


_READLINE_ENABLED = False


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _readline_safe_prompt(prompt: str) -> str:
	"""Wrap ANSI escapes so readline can correctly track cursor position.

	Readline expects non-printing sequences to be wrapped in \001 and \002.
	Without this, using Up/Down history can leave trailing characters on macOS.
	"""
	if not supports_color():
		return prompt
	# Wrap each ANSI SGR sequence.
	return _ANSI_RE.sub(lambda m: "\001" + m.group(0) + "\002", prompt)


def _setup_readline(*, history_path: str) -> None:
	"""Enable readline-based input editing/history for the REPL.

	Without this, terminals may echo arrow-key escape sequences (e.g. ^[[A).
	We only enable it for interactive TTY sessions.
	"""
	try:
		import readline  # type: ignore
	except Exception:
		return

	# Only makes sense in an interactive terminal.
	try:
		if not (os.isatty(0) and os.isatty(1)):
			return
	except Exception:
		return

	# Make sure the history directory exists.
	path = Path(history_path)
	if str(path.parent) not in {".", ""}:
		path.parent.mkdir(parents=True, exist_ok=True)

	# Best-effort load/save of history.
	try:
		readline.set_history_length(1000)
		history_file = str(path)
		if path.exists():
			readline.read_history_file(history_file)
		atexit.register(lambda: readline.write_history_file(history_file))
	except Exception:
		return

	global _READLINE_ENABLED
	_READLINE_ENABLED = True

	# Basic keybindings. (libedit vs GNU readline accept different strings.)
	try:
		if readline.__doc__ and "libedit" in readline.__doc__:
			readline.parse_and_bind("bind ^I rl_complete")
		else:
			readline.parse_and_bind("tab: complete")
	except Exception:
		pass


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
	_setup_readline(history_path=cfg.repl_history_path)
	history = HistoryStore(cfg.history_path)
	agent = Agent(history=history, config=agent_config)

	# UI/theme
	theme = run_onboarding(ui_config_path=cfg.ui_config_path)
	ui_cfg = load_ui_config(cfg.ui_config_path)
	theme = get_theme(ui_cfg.get("theme"))
	agent_cfg = getattr(agent, "config", None)
	agent_model = getattr(agent_cfg, "model", None) if agent_cfg is not None else None
	model = (agent_model or os.environ.get("LLM_MODEL") or "(default)").strip()
	cwd = os.getcwd()

	print(render_app_banner(theme))
	print("")
	print(render_system_info(theme=theme, model=model, cwd=cwd))
	print("")
	print(theme.a("Tiny Agent REPL") + theme.d(". Type /help for commands."))

	while True:
		try:
			prompt = theme.a("> ") if supports_color() else "> "
			if _READLINE_ENABLED and supports_color():
				prompt = _readline_safe_prompt(prompt)
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
		# In debug mode, tool traces and the final rendered answer can visually run together.
		# Add a clear separator before printing the final response.
		agent_cfg = getattr(agent, "config", None)
		if getattr(agent_cfg, "debug", False):
			sep = "-" * 72
			print(sep)
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
