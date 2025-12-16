from __future__ import annotations

import os
import tempfile
import unittest

from agent.tools import ToolRegistry


def vprint(msg: str) -> None:
	if os.environ.get("TEST_VISUAL"):
		print(msg)


class TestTools(unittest.TestCase):
	def setUp(self) -> None:
		self.tools = ToolRegistry()

	def test_list_dir(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			with open(os.path.join(td, "a.txt"), "w", encoding="utf-8") as f:
				f.write("x")
			os.makedirs(os.path.join(td, "sub"), exist_ok=True)

			res = self.tools.execute("list_dir", {"path": td})
			self.assertTrue(res["ok"])
			names = [e["name"] for e in res["entries"]]
			self.assertIn("a.txt", names)
			self.assertIn("sub", names)

	def test_write_and_read_file_with_range(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			p = os.path.join(td, "f.txt")
			w = self.tools.execute("write_file", {"path": p, "content": "l1\nl2\nl3\n"})
			self.assertTrue(w["ok"])

			r = self.tools.execute("read_file", {"path": p, "start_line": 2, "end_line": 3})
			self.assertTrue(r["ok"])
			self.assertEqual(r["content"], "l2\nl3")

	def test_grep_search(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			with open(os.path.join(td, "a.txt"), "w", encoding="utf-8") as f:
				f.write("hello\nneedle\n")
			with open(os.path.join(td, "b.txt"), "w", encoding="utf-8") as f:
				f.write("nope\n")

			res = self.tools.execute("grep_search", {"root": td, "pattern": "needle", "max_results": 10})
			self.assertTrue(res["ok"])
			self.assertGreaterEqual(len(res["results"]), 1)
			self.assertTrue(any("needle" in r["text"] for r in res["results"]))

	def test_create_diff(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			p = os.path.join(td, "x.txt")
			with open(p, "w", encoding="utf-8") as f:
				f.write("old\n")

			res = self.tools.execute("create_diff", {"path": p, "new_content": "new\n"})
			self.assertTrue(res["ok"])
			d = res["diff"]
			vprint(f"\n--- unified diff (create_diff) for {p} ---\n{d}\n")
			self.assertIn(f"--- a/{p}", d)
			self.assertIn(f"+++ b/{p}", d)

	def test_apply_patch_add_update_delete(self) -> None:
		with tempfile.TemporaryDirectory() as td:
			p = os.path.join(td, "t.txt")

			patch = """*** Begin Patch
*** Add File: {p}
+line1
+line2
*** End Patch
""".format(p=p)
			vprint(f"\n--- patch (add) ---\n{patch}")
			res = self.tools.execute("apply_patch", {"patch": patch})
			self.assertTrue(res["ok"])
			self.assertTrue(os.path.exists(p))
			with open(p, "r", encoding="utf-8") as f:
				vprint(f"--- file after add ({p}) ---\n{f.read()}")

			patch2 = """*** Begin Patch
*** Update File: {p}
@@
 line1
-line2
+lineX
*** End Patch
""".format(p=p)
			vprint(f"\n--- patch (update) ---\n{patch2}")
			res2 = self.tools.execute("apply_patch", {"patch": patch2})
			self.assertTrue(res2["ok"])
			with open(p, "r", encoding="utf-8") as f:
				content = f.read()
				vprint(f"--- file after update ({p}) ---\n{content}")
			self.assertIn("lineX", content)

			patch3 = """*** Begin Patch
*** Delete File: {p}
*** End Patch
""".format(p=p)
			vprint(f"\n--- patch (delete) ---\n{patch3}")
			res3 = self.tools.execute("apply_patch", {"patch": patch3})
			self.assertTrue(res3["ok"])
			self.assertFalse(os.path.exists(p))
			vprint(f"--- file exists after delete? {os.path.exists(p)} ---\n")
