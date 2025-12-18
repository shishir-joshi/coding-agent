from __future__ import annotations

import json
import unittest

from agent.llm_openai_compat import OpenAICompatClient


class TestOpenAICompatResponsesConversions(unittest.TestCase):
	def test_to_responses_tools_converts_function_schema(self) -> None:
		tools = [
			{
				"type": "function",
				"function": {
					"name": "read_file",
					"description": "Read a file",
					"parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
				},
			}
		]
		out = OpenAICompatClient._to_responses_tools(tools)
		self.assertEqual(out[0]["type"], "function")
		self.assertEqual(out[0]["name"], "read_file")
		self.assertIn("parameters", out[0])

	def test_to_responses_input_uses_output_text_for_assistant(self) -> None:
		messages = [
			{"role": "system", "content": "you are helpful"},
			{"role": "user", "content": "hi"},
			{"role": "assistant", "content": "hello"},
		]
		items = OpenAICompatClient._to_responses_input(messages)
		self.assertEqual(items[0]["role"], "developer")
		self.assertEqual(items[0]["content"][0]["type"], "input_text")
		self.assertEqual(items[1]["role"], "user")
		self.assertEqual(items[1]["content"][0]["type"], "input_text")
		self.assertEqual(items[2]["role"], "assistant")
		self.assertEqual(items[2]["content"][0]["type"], "output_text")

	def test_to_responses_input_converts_tool_outputs(self) -> None:
		messages = [
			{
				"role": "tool",
				"tool_call_id": "call_123",
				"name": "read_file",
				"content": json.dumps({"ok": True, "content": "x"}),
			}
		]
		items = OpenAICompatClient._to_responses_input(messages)
		self.assertEqual(items[0]["type"], "function_call_output")
		self.assertEqual(items[0]["call_id"], "call_123")
		self.assertIn("output", items[0])

	def test_to_responses_input_includes_assistant_tool_calls(self) -> None:
		messages = [
			{
				"role": "assistant",
				"content": None,
				"tool_calls": [
					{
						"id": "call_abc",
						"type": "function",
						"function": {"name": "execute_command", "arguments": "{\"command\": \"ls\"}"},
					}
				],
			},
			{
				"role": "tool",
				"tool_call_id": "call_abc",
				"name": "execute_command",
				"content": "{\"ok\": true}",
			},
		]
		items = OpenAICompatClient._to_responses_input(messages)
		self.assertEqual(items[0]["type"], "function_call")
		self.assertEqual(items[0]["call_id"], "call_abc")
		self.assertEqual(items[0]["name"], "execute_command")
		self.assertIsInstance(items[0]["arguments"], str)
		self.assertEqual(items[1]["type"], "function_call_output")
		self.assertEqual(items[1]["call_id"], "call_abc")
