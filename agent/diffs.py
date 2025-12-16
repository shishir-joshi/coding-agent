from __future__ import annotations

import difflib


def unified_diff(path: str, old: str, new: str) -> str:
	old_lines = old.splitlines(keepends=True)
	new_lines = new.splitlines(keepends=True)
	out = difflib.unified_diff(
		old_lines,
		new_lines,
		fromfile=f"a/{path}",
		tofile=f"b/{path}",
		lineterm="",
	)
	return "".join(out)
