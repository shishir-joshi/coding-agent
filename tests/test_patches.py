from __future__ import annotations

import os
import tempfile
import unittest

from agent.patches import PatchError, apply_v4a_patch


def vprint(msg: str) -> None:
	if os.environ.get("TEST_VISUAL"):
		print(msg)


class TestPatches(unittest.TestCase):
	def test_requires_begin_marker(self) -> None:
		with self.assertRaises(PatchError):
			apply_v4a_patch("*** Update File: x\n")

	def test_add_file(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			p = os.path.join(td, "a.txt")
			patch = f"""*** Begin Patch
*** Add File: {p}
+hello
+world
*** End Patch
"""
			vprint(f"\n--- patch (add) ---\n{patch}")
			out = apply_v4a_patch(patch)
			self.assertEqual(out["applied"][0]["action"], "add")
			self.assertTrue(os.path.exists(p))
			with open(p, "r", encoding="utf-8") as f:
				content = f.read()
				vprint(f"--- file after add ({p}) ---\n{content}")
				self.assertEqual(content, "hello\nworld\n")

	def test_update_file_single_chunk(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			p = os.path.join(td, "u.txt")
			with open(p, "w", encoding="utf-8") as f:
				f.write("a\nb\nc\n")
			with open(p, "r", encoding="utf-8") as f:
				vprint(f"\n--- before ({p}) ---\n{f.read()}")
			patch = f"""*** Begin Patch
*** Update File: {p}
@@
 a
-b
+x
 c
*** End Patch
"""
			vprint(f"--- patch (update single chunk) ---\n{patch}")
			apply_v4a_patch(patch)
			with open(p, "r", encoding="utf-8") as f:
				after = f.read()
				vprint(f"--- after ({p}) ---\n{after}")
				self.assertEqual(after, "a\nx\nc\n")

	def test_update_file_multiple_chunks(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			p = os.path.join(td, "m.txt")
			with open(p, "w", encoding="utf-8") as f:
				f.write("one\ntwo\nthree\nfour\n")
			with open(p, "r", encoding="utf-8") as f:
				vprint(f"\n--- before ({p}) ---\n{f.read()}")
			patch = f"""*** Begin Patch
*** Update File: {p}
@@
 one
-two
+TWO
@@
 three
-four
+FOUR
*** End Patch
"""
			vprint(f"--- patch (update multi chunk) ---\n{patch}")
			apply_v4a_patch(patch)
			with open(p, "r", encoding="utf-8") as f:
				after = f.read()
				vprint(f"--- after ({p}) ---\n{after}")
				self.assertEqual(after, "one\nTWO\nthree\nFOUR\n")

	def test_delete_file(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			p = os.path.join(td, "d.txt")
			with open(p, "w", encoding="utf-8") as f:
				f.write("x")
			patch = f"""*** Begin Patch
*** Delete File: {p}
*** End Patch
"""
			apply_v4a_patch(patch)
			self.assertFalse(os.path.exists(p))
