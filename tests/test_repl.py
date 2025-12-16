from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import agent.repl as repl
from agent.agent_loop import AgentConfig


class FakeAgent:
	def __init__(self, *args, **kwargs) -> None:
		self._context = "CTX"
		self._tools = "- t1: tool1\n- t2: tool2"

	def reset(self) -> None:
		self._context = "CTX_RESET"

	def dump_context(self) -> str:
		return self._context

	def dump_tools(self, *, as_json: bool = False) -> str:
		return self._tools if not as_json else "[{\"name\":\"t1\"}]"

	def chat(self, user_text: str) -> str:
		return f"ECHO:{user_text}"


class TestRepl(unittest.TestCase):
	def test_handle_commands(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			history = repl.HistoryStore(os.path.join(td, "h.jsonl"))
			agent = FakeAgent()
			cfg = repl.ReplConfig(history_path=os.path.join(td, "h.jsonl"))

			buf = io.StringIO()
			with redirect_stdout(buf):
				repl._handle_command("/context", agent, history, cfg)
				repl._handle_command("/tools", agent, history, cfg)
				repl._handle_command("/tools json", agent, history, cfg)
				repl._handle_command("/reset", agent, history, cfg)
				repl._handle_command("/history 5", agent, history, cfg)

			out = buf.getvalue()
			self.assertIn("CTX", out)
			self.assertIn("- t1: tool1", out)
			self.assertIn("[{\"name\":\"t1\"}]", out)
			self.assertIn("(context reset)", out)

	def test_run_repl_smoke(self) -> None:
		# Avoid real network by patching Agent to FakeAgent
		with tempfile.TemporaryDirectory() as td:
			history_path = os.path.join(td, "hist.jsonl")
			buf = io.StringIO()
			with patch.dict(os.environ, {"AGENT_NO_ONBOARDING": "1"}), patch.object(
				repl, "Agent", FakeAgent
			), patch("builtins.input", side_effect=["hello", "/exit"]), redirect_stdout(buf):
				repl.run_repl(agent_config=AgentConfig(debug=False), history_path=history_path)

			out = buf.getvalue()
			# Visual-friendly if enabled
			if os.environ.get("TEST_VISUAL"):
				print("\n--- repl transcript ---\n" + out)
			self.assertIn("Tiny Agent REPL", out)
			self.assertIn("ECHO:hello", out)
