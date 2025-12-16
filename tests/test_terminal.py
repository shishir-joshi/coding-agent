from __future__ import annotations

import os
import tempfile
import time
import unittest

from agent.terminal import TerminalManager


def vprint(msg: str) -> None:
	if os.environ.get("TEST_VISUAL"):
		print(msg)


class TestTerminalManager(unittest.TestCase):
	def test_stateful_cwd_persists(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			state_dir = os.path.join(td, ".agent")
			term = TerminalManager(workdir=td, state_dir=state_dir)

			res1 = term.execute("pwd")
			vprint(f"\n--- pwd 1 ---\n{res1}\n")
			self.assertTrue(res1["ok"])
			self.assertIn(td, res1["stdout"])

			# Change directory via cwd argument (this should persist)
			sub = os.path.join(td, "sub")
			os.makedirs(sub, exist_ok=True)
			res2 = term.execute("pwd", cwd=sub)
			vprint(f"--- pwd 2 (after cwd=sub) ---\n{res2}\n")
			self.assertIn(sub, res2["stdout"])

			# Now run again without cwd: should still be in sub
			res3 = term.execute("pwd")
			vprint(f"--- pwd 3 (should still be sub) ---\n{res3}\n")
			self.assertIn(sub, res3["stdout"])

			term.close()

	def test_background_process_output(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			state_dir = os.path.join(td, ".agent")
			term = TerminalManager(workdir=td, state_dir=state_dir)

			# Use python to avoid shell portability issues with sleep/echo
			proc = term.start_background("python3 -c 'import time; time.sleep(0.1); print(\"hi\")'")
			vprint(f"\n--- started bg ---\n{proc}\n")

			# Poll until done
			deadline = time.time() + 5
			last = None
			while time.time() < deadline:
				last = term.get_process_output(proc.process_id, tail_lines=200)
				if last.get("exit_code") is not None:
					break
				time.sleep(0.05)

			vprint(f"--- bg output ---\n{last}\n")
			self.assertIsNotNone(last)
			self.assertTrue(last["ok"])
			self.assertEqual(last["exit_code"], 0)
			self.assertIn("hi", last["output"])

			term.close()
