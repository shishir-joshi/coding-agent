from __future__ import annotations

import os
import unittest
from unittest import mock

from agent.ui import get_theme, render_markdown


class TestUiMarkdown(unittest.TestCase):
	def test_render_markdown_plain(self) -> None:
		# Force no color for deterministic assertions.
		with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
			theme = get_theme("dark")
			md = (
				"# Title\n"
				"Some **bold** and `code`.\n"
				"- item\n"
				"```py\n"
				"print(\"hi\")\n"
				"```\n"
			)
			out = render_markdown(md, theme)
			self.assertIn("Title\n", out)
			self.assertIn("-----", out)
			self.assertIn("Some bold and `code`.", out)
			self.assertIn("• item", out)
			self.assertIn("code (py)", out)
			self.assertIn("  print(\"hi\")", out)
