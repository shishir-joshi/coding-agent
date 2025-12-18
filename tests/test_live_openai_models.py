from __future__ import annotations

import os
import unittest

from agent.llm_openai_compat import OpenAICompatClient


def _live_tests_enabled() -> bool:
	return os.environ.get("RUN_LIVE_OPENAI_TESTS", "").lower() in {"1", "true", "yes"}


class TestLiveOpenAIModels(unittest.TestCase):
	@unittest.skipUnless(_live_tests_enabled(), "Set RUN_LIVE_OPENAI_TESTS=1 to enable live OpenAI tests")
	def test_arbitrary_prompt_gpt_5_1_codex_mini(self) -> None:
		# Requires OPENAI_API_KEY in the environment.
		client = OpenAICompatClient(model="gpt-5.1-codex-mini", timeout_s=120)
		resp = client.chat(
			messages=[
				{"role": "system", "content": "You are a helpful assistant."},
				{"role": "user", "content": "Reply with a single short sentence about ASTs."},
			],
			tools=[],
		)
		msg = resp["message"]
		self.assertEqual(msg.get("role"), "assistant")
		self.assertIsInstance(msg.get("content"), str)
		self.assertTrue(len(msg.get("content", "")) > 0)

	@unittest.skipUnless(_live_tests_enabled(), "Set RUN_LIVE_OPENAI_TESTS=1 to enable live OpenAI tests")
	def test_arbitrary_prompt_gpt_4o_mini(self) -> None:
		# Requires OPENAI_API_KEY in the environment.
		client = OpenAICompatClient(model="gpt-4o-mini", timeout_s=120)
		resp = client.chat(
			messages=[
				{"role": "system", "content": "You are a helpful assistant."},
				{"role": "user", "content": "Reply with a single short sentence about parsing."},
			],
			tools=[],
		)
		msg = resp["message"]
		self.assertEqual(msg.get("role"), "assistant")
		self.assertIsInstance(msg.get("content"), str)
		self.assertTrue(len(msg.get("content", "")) > 0)
