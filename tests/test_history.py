from __future__ import annotations

import json
import os
import tempfile
import unittest

from agent.history import HistoryStore


def vprint(msg: str) -> None:
	if os.environ.get("TEST_VISUAL"):
		print(msg)


class TestHistoryStore(unittest.TestCase):
	def test_append_and_tail(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			path = os.path.join(td, "history.jsonl")
			hs = HistoryStore(path)

			hs.append_event({"type": "user", "text": "hello"})
			hs.append_event({"type": "assistant", "text": "hi"})

			out = hs.tail(10)
			vprint("\n--- history tail ---\n" + out)

			lines = [l for l in out.splitlines() if l.strip()]
			self.assertGreaterEqual(len(lines), 2)
			rec0 = json.loads(lines[0])
			rec1 = json.loads(lines[1])
			self.assertIn("ts", rec0)
			self.assertEqual(rec0["type"], "user")
			self.assertEqual(rec1["type"], "assistant")

	def test_tail_empty(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			path = os.path.join(td, "missing.jsonl")
			hs = HistoryStore(path)
			self.assertEqual(hs.tail(10), "(no history yet)")
