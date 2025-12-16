"""
V4A-like patch application.
eg:
*** Begin Patch
*** Add File: path/to/newfile.txt
+This is a new file.
+It has multiple lines.
*** Delete File: path/to/oldfile.txt
*** Update File: path/to/existingfile.txt
@@ -1,3 +1,4 @@
 Line 1
-Line 2
+Modified Line 2
 Line 3
*** End Patch
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable


class PatchError(Exception):
	pass


@dataclass
class UpdateChunk:
	lines: list[str]


def apply_v4a_patch(patch_text: str) -> dict:
	lines = patch_text.splitlines()
	if not any(l.startswith("*** Begin Patch") for l in lines):
		raise PatchError("Patch must start with '*** Begin Patch'")

	i = 0
	# Seek begin
	while i < len(lines) and not lines[i].startswith("*** Begin Patch"):
		i += 1
	i += 1

	applied: list[dict] = []
	while i < len(lines):
		line = lines[i]
		if line.startswith("*** End Patch"):
			break

		if line.startswith("*** Add File:"):
			path = line.split(":", 1)[1].strip()
			i += 1
			content_lines: list[str] = []
			while i < len(lines) and not lines[i].startswith("*** "):
				l = lines[i]
				# allow optional leading '+' for file content
				content_lines.append(l[1:] if l.startswith("+") else l)
				i += 1
			_write_text(path, "\n".join(content_lines) + ("\n" if content_lines else ""))
			applied.append({"action": "add", "path": path})
			continue

		if line.startswith("*** Delete File:"):
			path = line.split(":", 1)[1].strip()
			i += 1
			if os.path.exists(path):
				os.remove(path)
			applied.append({"action": "delete", "path": path})
			continue

		if line.startswith("*** Update File:"):
			path = line.split(":", 1)[1].strip()
			i += 1
			chunks: list[UpdateChunk] = []
			# If no @@ markers, treat until next action as one chunk
			if i < len(lines) and not lines[i].startswith("@@"):
				chunk_lines: list[str] = []
				while i < len(lines) and not lines[i].startswith("*** "):
					chunk_lines.append(lines[i])
					i += 1
				chunks.append(UpdateChunk(lines=chunk_lines))
			else:
				while i < len(lines) and lines[i].startswith("@@"):
					# consume '@@' header
					i += 1
					chunk_lines = []
					while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("*** "):
						chunk_lines.append(lines[i])
						i += 1
					chunks.append(UpdateChunk(lines=chunk_lines))

			_apply_update(path, chunks)
			applied.append({"action": "update", "path": path, "chunks": len(chunks)})
			continue

		raise PatchError(f"Unexpected patch line: {line}")

	return {"applied": applied}


def _apply_update(path: str, chunks: list[UpdateChunk]) -> None:
	old_text = ""
	if os.path.exists(path):
		with open(path, "r", encoding="utf-8") as f:
			old_text = f.read()

	file_lines = old_text.splitlines()

	for chunk in chunks:
		pattern, replacement = _compile_chunk(chunk.lines)
		start = _find_subsequence(file_lines, pattern)
		if start is None:
			# fallback: rstrip match
			start = _find_subsequence(file_lines, pattern, canonical=_rstrip)
		if start is None:
			# fallback: strip match
			start = _find_subsequence(file_lines, pattern, canonical=_strip)
		if start is None:
			raise PatchError(f"Could not find chunk to apply in {path} (pattern length={len(pattern)})")

		file_lines[start : start + len(pattern)] = replacement

	_write_text(path, "\n".join(file_lines) + ("\n" if file_lines else ""))


def _compile_chunk(lines: list[str]) -> tuple[list[str], list[str]]:
	"""Compile a V4A-like chunk into (pattern, replacement).

	- context lines: unchanged (either start with ' ' or no prefix)
	- deletions: start with '-'
	- additions: start with '+'

	Pattern is context+deletions (the exact subsequence to find in the file).
	Replacement is context+additions (what to put instead).
	"""
	pattern: list[str] = []
	replacement: list[str] = []
	for raw in lines:
		if raw.startswith("+"):
			replacement.append(raw[1:])
			continue
		if raw.startswith("-"):
			pattern.append(raw[1:])
			continue
		# context
		ctx = raw[1:] if raw.startswith(" ") else raw
		pattern.append(ctx)
		replacement.append(ctx)
	return pattern, replacement


def _find_subsequence(haystack: list[str], needle: list[str], canonical=None) -> int | None:
	if canonical is None:
		canonical = lambda s: s
	if not needle:
		return 0
	H = [canonical(x) for x in haystack]
	N = [canonical(x) for x in needle]
	for i in range(0, len(H) - len(N) + 1):
		if H[i : i + len(N)] == N:
			return i
	return None


def _rstrip(s: str) -> str:
	return s.rstrip()


def _strip(s: str) -> str:
	return s.strip()


def _write_text(path: str, content: str) -> None:
	os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
	with open(path, "w", encoding="utf-8") as f:
		f.write(content)
