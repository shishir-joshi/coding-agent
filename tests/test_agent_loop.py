from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from agent.agent_loop import Agent, AgentConfig
from agent.history import HistoryStore


class TestAgentLoop(unittest.TestCase):
	# Verifies a tool call is executed and the assistant consumes the tool output.
	def test_tool_call_round_trip(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			# Create a file the tool will read
			p = os.path.join(td, "x.txt")
			with open(p, "w", encoding="utf-8") as f:
				f.write("hello\nworld\n")

			hs = HistoryStore(os.path.join(td, "h.jsonl"))
			agent = Agent(history=hs, config=AgentConfig(max_tool_rounds=4, debug=False, enable_planning=False))
			calls = {"n": 0}

			def fake_chat(*, messages, tools):
				calls["n"] += 1
				if calls["n"] == 1:
					return {
						"message": {
							"role": "assistant",
							"content": None,
							"tool_calls": [
								{
									"id": "call_1",
									"type": "function",
									"function": {"name": "read_file", "arguments": json.dumps({"path": p})},
								}
							],
						}
					}
				# Second response: use the tool output already in messages
				return {"message": {"role": "assistant", "content": "done", "tool_calls": []}}

			agent.client.chat = fake_chat  # type: ignore[attr-defined]

			out = agent.chat("read the file")
			self.assertEqual(out, "done")

			# Ensure tool message was appended
			self.assertTrue(any(m.get("role") == "tool" for m in agent.messages))

	# Ensures debug mode surfaces the debug prefix in stdout.
	def test_debug_mode_prints(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			hs = HistoryStore(os.path.join(td, "h.jsonl"))
			agent = Agent(history=hs, config=AgentConfig(max_tool_rounds=2, debug=True))

			def fake_chat(*, messages, tools):
				return {"message": {"role": "assistant", "content": "hi", "tool_calls": []}}

			agent.client.chat = fake_chat  # type: ignore[attr-defined]

			buf = io.StringIO()
			with redirect_stdout(buf):
				agent.chat("hello")
			out = buf.getvalue()
			self.assertIn("[debug]", out)

		# Confirms the guard stops after max_tool_rounds and returns a safe message.
	def test_max_rounds_guard(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			hs = HistoryStore(os.path.join(td, "h.jsonl"))
			agent = Agent(history=hs, config=AgentConfig(max_tool_rounds=1, debug=False))

			# Always request a tool, so we exceed max rounds
			def fake_chat(*, messages, tools):
				return {
					"message": {
						"role": "assistant",
						"content": None,
						"tool_calls": [
							{
								"id": "call_1",
								"type": "function",
								"function": {"name": "list_dir", "arguments": json.dumps({"path": td})},
							}
						],
					}
				}

			agent.client.chat = fake_chat  # type: ignore[attr-defined]

			out = agent.chat("loop")
			self.assertIn("too many tool rounds", out)

	# Checks heuristic keywords for repo reorg trigger a deterministic multi-step plan.
	def test_should_plan_reorg_heuristic(self) -> None:
		agent = Agent(history=HistoryStore(":memory:"), config=AgentConfig(enable_planning=True))
		# Planning is LLM-driven; ensure we do call the LLM for analysis.
		agent.client.chat = lambda *_, **__: {  # type: ignore[attr-defined]
			"message": {
				"content": '{"needs_plan": true, "reasoning": "multi-step refactor", "steps": ["Inspect repo", "Propose layout", "Apply changes"]}'
			}
		}

		needs_plan, steps, reason = agent._should_plan("Please reorganize the repository layout")
		self.assertTrue(needs_plan)
		self.assertGreaterEqual(len(steps), 3)
		self.assertIn("multi-step", reason)

	# Checks planning keywords trigger deterministic steps even without LLM output.
	def test_should_plan_plan_word_heuristic(self) -> None:
		agent = Agent(history=HistoryStore(":memory:"), config=AgentConfig(enable_planning=True))
		agent.client.chat = lambda *_, **__: {  # type: ignore[attr-defined]
			"message": {
				"content": '{"needs_plan": true, "reasoning": "explicit request for roadmap", "steps": ["Clarify goals", "Draft plan", "Execute"]}'
			}
		}

		needs_plan, steps, reason = agent._should_plan("Give me a roadmap with steps")
		self.assertTrue(needs_plan)
		self.assertGreaterEqual(len(steps), 3)
		self.assertIn("roadmap", reason)

	# Ensures short, simple questions are classified as no-plan paths.
	def test_should_plan_simple_query_short_circuits(self) -> None:
		agent = Agent(history=HistoryStore(":memory:"), config=AgentConfig(enable_planning=True))
		agent.client.chat = lambda *_, **__: (_ for _ in ()).throw(RuntimeError("should not call llm"))  # type: ignore[attr-defined]

		needs_plan, steps, reason = agent._should_plan("what is this?")
		self.assertFalse(needs_plan)
		self.assertEqual(steps, [])
		self.assertIn("simple query", reason)
