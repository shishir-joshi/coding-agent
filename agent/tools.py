from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from .patches import apply_v4a_patch
from .diffs import unified_diff
from .terminal import TerminalManager


@dataclass
class ToolRegistry:
	terminal: TerminalManager | None = None

	def _terminal(self) -> TerminalManager:
		if self.terminal is None:
			self.terminal = TerminalManager(workdir=".", state_dir=".agent")
		return self.terminal

	def tool_schemas(self) -> list[dict[str, Any]]:
		# OpenAI function-tool schema
		return [
			{
				"type": "function",
				"function": {
					"name": "read_file",
					"description": "Read a text file from disk (optionally by line range).",
					"parameters": {
						"type": "object",
						"properties": {
							"path": {"type": "string"},
							"start_line": {"type": "integer", "minimum": 1},
							"end_line": {"type": "integer", "minimum": 1},
						},
						"required": ["path"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "list_dir",
					"description": "List directory contents.",
					"parameters": {
						"type": "object",
						"properties": {"path": {"type": "string"}},
						"required": ["path"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "grep_search",
					"description": "Search for a regex pattern in text files under a directory.",
					"parameters": {
						"type": "object",
						"properties": {
							"root": {"type": "string", "default": "."},
							"pattern": {"type": "string"},
							"max_results": {"type": "integer", "default": 20, "minimum": 1},
						},
						"required": ["pattern"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "write_file",
					"description": "Write a file to disk (overwrites).",
					"parameters": {
						"type": "object",
						"properties": {
							"path": {"type": "string"},
							"content": {"type": "string"},
						},
						"required": ["path", "content"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "apply_patch",
					"description": "Apply a simple diff-style patch in a V4A-like format (*** Begin Patch ... *** End Patch).",
					"parameters": {
						"type": "object",
						"properties": {"patch": {"type": "string"}},
						"required": ["patch"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "create_diff",
					"description": "Create a unified diff between current file and provided new content.",
					"parameters": {
						"type": "object",
						"properties": {
							"path": {"type": "string"},
							"new_content": {"type": "string"},
						},
						"required": ["path", "new_content"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "execute_command",
					"description": "Run a shell command in a persistent terminal session (stateful). Can run in background.",
					"parameters": {
						"type": "object",
						"properties": {
							"command": {"type": "string"},
							"cwd": {"type": "string", "description": "If provided, cd to this directory (persists for later commands)."},
							"timeout_s": {"type": "integer", "default": 120, "minimum": 1},
							"is_background": {"type": "boolean", "default": False},
						},
						"required": ["command"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "get_process_output",
					"description": "Get output (and exit code if finished) for a background process started by execute_command.",
					"parameters": {
						"type": "object",
						"properties": {
							"process_id": {"type": "string"},
							"tail_lines": {"type": "integer", "default": 200, "minimum": 1},
						},
						"required": ["process_id"],
					},
				},
			},
			{
				"type": "function",
				"function": {
					"name": "list_processes",
					"description": "List background processes started in this workspace (best-effort).",
					"parameters": {"type": "object", "properties": {}},
				},
			},
		]

	def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
		try:
			if name == "read_file":
				return self._read_file(args)
			if name == "list_dir":
				return self._list_dir(args)
			if name == "grep_search":
				return self._grep_search(args)
			if name == "write_file":
				return self._write_file(args)
			if name == "apply_patch":
				return self._apply_patch(args)
			if name == "create_diff":
				return self._create_diff(args)
			if name == "execute_command":
				return self._execute_command(args)
			if name == "get_process_output":
				return self._get_process_output(args)
			if name == "list_processes":
				return self._list_processes(args)
			return {"ok": False, "error": f"Unknown tool: {name}"}
		except Exception as e:
			return {"ok": False, "error": str(e)}

	def _read_file(self, args: dict[str, Any]) -> dict[str, Any]:
		path = args["path"]
		start = int(args.get("start_line", 1) or 1)
		end = args.get("end_line")
		end_i = int(end) if end is not None else None

		with open(path, "r", encoding="utf-8") as f:
			lines = f.read().splitlines()

		start_idx = max(start - 1, 0)
		end_idx = end_i if end_i is not None else len(lines)
		end_idx = min(end_idx, len(lines))
		selected = lines[start_idx:end_idx]
		return {"ok": True, "path": path, "start_line": start, "end_line": end_i or len(lines), "content": "\n".join(selected)}

	def _list_dir(self, args: dict[str, Any]) -> dict[str, Any]:
		path = args["path"]
		entries = []
		for name in sorted(os.listdir(path)):
			full = os.path.join(path, name)
			entries.append({"name": name, "type": "dir" if os.path.isdir(full) else "file"})
		return {"ok": True, "path": path, "entries": entries}

	def _grep_search(self, args: dict[str, Any]) -> dict[str, Any]:
		root = args.get("root", ".")
		pattern = args["pattern"]
		max_results = int(args.get("max_results", 20) or 20)
		rx = re.compile(pattern)

		results: list[dict[str, Any]] = []
		for dirpath, dirnames, filenames in os.walk(root):
			# skip common noisy dirs
			dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "__pycache__", ".agent"}]
			for fn in filenames:
				full = os.path.join(dirpath, fn)
				try:
					with open(full, "r", encoding="utf-8") as f:
						for i, line in enumerate(f, start=1):
							if rx.search(line):
								results.append({"path": full, "line": i, "text": line.rstrip("\n")})
								if len(results) >= max_results:
									return {"ok": True, "pattern": pattern, "results": results}
				except Exception:
					continue

		return {"ok": True, "pattern": pattern, "results": results}

	def _write_file(self, args: dict[str, Any]) -> dict[str, Any]:
		path = args["path"]
		content = args["content"]
		os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
		with open(path, "w", encoding="utf-8") as f:
			f.write(content)
		return {"ok": True, "path": path, "bytes": len(content.encode("utf-8"))}

	def _apply_patch(self, args: dict[str, Any]) -> dict[str, Any]:
		patch = args["patch"]
		applied = apply_v4a_patch(patch)
		return {"ok": True, **applied}

	def _create_diff(self, args: dict[str, Any]) -> dict[str, Any]:
		path = args["path"]
		new_content = args["new_content"]
		old = ""
		try:
			with open(path, "r", encoding="utf-8") as f:
				old = f.read()
		except FileNotFoundError:
			old = ""
		d = unified_diff(path, old, new_content)
		return {"ok": True, "path": path, "diff": d}

	def _execute_command(self, args: dict[str, Any]) -> dict[str, Any]:
		command = args["command"]
		cwd = args.get("cwd")
		timeout_s = int(args.get("timeout_s", 120) or 120)
		is_background = bool(args.get("is_background", False))

		term = self._terminal()
		if is_background:
			proc = term.start_background(command, cwd=cwd)
			return {
				"ok": True,
				"background": True,
				"process_id": proc.process_id,
				"pid": proc.pid,
				"log_path": proc.log_path,
				"status_path": proc.status_path,
			}

		res = term.execute(command, cwd=cwd, timeout_s=timeout_s)
		return {"ok": True, "background": False, **res}

	def _get_process_output(self, args: dict[str, Any]) -> dict[str, Any]:
		process_id = args["process_id"]
		tail_lines = args.get("tail_lines", 200)
		term = self._terminal()
		return term.get_process_output(process_id, tail_lines=int(tail_lines) if tail_lines is not None else None)

	def _list_processes(self, _args: dict[str, Any]) -> dict[str, Any]:
		term = self._terminal()
		return term.list_processes()
