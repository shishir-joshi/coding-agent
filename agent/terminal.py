from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from typing import Any, TextIO


class TerminalError(Exception):
	pass


@dataclass
class BackgroundProcess:
	process_id: str
	pid: int
	command: str
	cwd: str | None
	log_path: str
	status_path: str
	started_at: float


class TerminalManager:
	"""A tiny, Cline-like terminal integration.

	- Maintains a single persistent shell process (zsh by default)
	- Foreground commands run in the same shell context, so state persists (cwd, exports, etc.)
	- Background commands write output to a log file and write exit code to a status file
	"""

	def __init__(
		self,
		*,
		workdir: str = ".",
		state_dir: str = ".agent",
		shell_path: str = "/bin/zsh",
	) -> None:
		# Normalize paths early so background log/status paths remain stable even if
		# the shell changes its cwd.
		self.workdir = os.path.abspath(workdir)
		if os.path.isabs(state_dir):
			self.state_dir = state_dir
		else:
			self.state_dir = os.path.abspath(os.path.join(self.workdir, state_dir))
		self.shell_path = shell_path

		self._proc: subprocess.Popen[str] | None = None
		self._stdin: TextIO | None = None
		self._stdout: TextIO | None = None

		self._index_path = os.path.join(self.state_dir, "proc", "index.json")

	def close(self) -> None:
		proc = self._proc
		stdin = self._stdin
		stdout = self._stdout

		self._proc = None
		self._stdin = None
		self._stdout = None

		try:
			if stdin:
				stdin.close()
		except Exception:
			pass
		try:
			if stdout:
				stdout.close()
		except Exception:
			pass

		if proc and proc.poll() is None:
			try:
				proc.terminate()
				proc.wait(timeout=1)
			except Exception:
				try:
					proc.kill()
					proc.wait(timeout=1)
				except Exception:
					pass

	def _ensure_shell(self) -> None:
		if self._proc and self._proc.poll() is None:
			return

		os.makedirs(os.path.join(self.state_dir, "proc"), exist_ok=True)
		# Start a persistent shell. We avoid -i to reduce prompt/noise.
		self._proc = subprocess.Popen(
			[self.shell_path],
			stdin=subprocess.PIPE,
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			text=True,
			bufsize=1,
		)
		assert self._proc.stdin is not None
		assert self._proc.stdout is not None
		self._stdin = self._proc.stdin  # type: ignore[assignment]
		self._stdout = self._proc.stdout  # type: ignore[assignment]

		# Set initial working directory.
		self._write_line(f'cd "{self.workdir}"')
		# Drain any output produced by startup.
		self._drain_nonblocking(0.05)

	def execute(
		self,
		command: str,
		*,
		cwd: str | None = None,
		timeout_s: int = 120,
	) -> dict[str, Any]:
		"""Run a foreground command and return combined output + exit code.

		Important: Foreground commands run in the shell context (not a subshell), so `cd` persists.
		"""
		self._ensure_shell()
		req_id = uuid.uuid4().hex
		start = f"__AGENT_CMD_START__{req_id}__"
		end = f"__AGENT_CMD_END__{req_id}__"

		# If cwd is set, we intentionally *persist* it by doing cd in the shell.
		prefix = f'cd "{cwd}"; ' if cwd else ""
		# Use a brace-group so the command runs in the current shell context.
		wrapped = f'echo "{start}"; {prefix}{{ {command}; }} 2>&1; echo "{end}:$?"'

		self._write_line(wrapped)
		out_lines, exit_code = self._read_until_end_marker(end, timeout_s=timeout_s)

		return {
			"ok": True,
			"exit_code": exit_code,
			"stdout": "\n".join(out_lines).rstrip("\n"),
			"stderr": "",  # stderr is merged into stdout
		}

	def start_background(self, command: str, *, cwd: str | None = None) -> BackgroundProcess:
		"""Start a background command. Output goes to a log file, exit code to a status file."""
		self._ensure_shell()

		process_id = uuid.uuid4().hex
		log_path = os.path.join(self.state_dir, "proc", f"{process_id}.log")
		status_path = os.path.join(self.state_dir, "proc", f"{process_id}.status")

		marker = f"__AGENT_BG__{process_id}__"
		prefix = f'cd "{cwd}"; ' if cwd else ""

		# Start in background; store exit code once finished.
		# Note: The brace-group runs as a background job, so it won't affect shell state.
		cmd = (
			f'{prefix}{{ {{ {command}; }} > "{log_path}" 2>&1; echo $? > "{status_path}"; }} & '
			f'echo "{marker}:PID:$!"'
		)
		self._write_line(cmd)

		# Read one line that contains the PID marker
		pid = self._read_bg_pid(marker, timeout_s=5)

		proc = BackgroundProcess(
			process_id=process_id,
			pid=pid,
			command=command,
			cwd=cwd,
			log_path=log_path,
			status_path=status_path,
			started_at=time.time(),
		)
		self._index_put(proc)
		return proc

	def get_process_output(self, process_id: str, *, tail_lines: int | None = 200) -> dict[str, Any]:
		info = self._index_get(process_id)
		if not info:
			return {"ok": False, "error": f"Unknown process_id: {process_id}"}

		log_path = info["log_path"]
		status_path = info["status_path"]

		output = ""
		if os.path.exists(log_path):
			with open(log_path, "r", encoding="utf-8", errors="replace") as f:
				lines = f.read().splitlines()
				if tail_lines is not None:
					lines = lines[-tail_lines:]
				output = "\n".join(lines)

		exit_code = None
		if os.path.exists(status_path):
			try:
				with open(status_path, "r", encoding="utf-8") as f:
					exit_code = int(f.read().strip())
			except Exception:
				exit_code = None

		running = True
		try:
			os.kill(int(info["pid"]), 0)
		except OSError:
			running = False

		done = exit_code is not None
		return {
			"ok": True,
			"process_id": process_id,
			"pid": info["pid"],
			"running": running and not done,
			"exit_code": exit_code,
			"output": output,
		}

	def list_processes(self) -> dict[str, Any]:
		return {"ok": True, "processes": self._index_all()}

	def _write_line(self, s: str) -> None:
		assert self._stdin is not None
		self._stdin.write(s + "\n")
		self._stdin.flush()

	def _read_until_end_marker(self, end_marker_prefix: str, *, timeout_s: int) -> tuple[list[str], int]:
		assert self._stdout is not None
		start_time = time.time()
		out_lines: list[str] = []
		exit_code: int | None = None

		while True:
			if time.time() - start_time > timeout_s:
				raise TerminalError(f"Timeout waiting for command to finish ({timeout_s}s)")

			line = self._stdout.readline()
			if line == "":
				raise TerminalError("Shell terminated unexpectedly")
			line = line.rstrip("\n")

			if line.startswith(end_marker_prefix + ":"):
				try:
					exit_code = int(line.split(":", 1)[1])
				except Exception:
					exit_code = 0
				break

			# Skip the start marker line if it somehow appears in output
			if line.startswith("__AGENT_CMD_START__"):
				continue

			out_lines.append(line)

		return out_lines, int(exit_code or 0)

	def _read_bg_pid(self, marker_prefix: str, *, timeout_s: int) -> int:
		assert self._stdout is not None
		start_time = time.time()
		while True:
			if time.time() - start_time > timeout_s:
				raise TerminalError("Timeout waiting for background PID")
			line = self._stdout.readline()
			if line == "":
				raise TerminalError("Shell terminated unexpectedly")
			line = line.strip()
			if line.startswith(marker_prefix + ":PID:"):
				pid_s = line.split(":PID:", 1)[1]
				return int(pid_s)

	def _drain_nonblocking(self, max_seconds: float) -> None:
		# Best-effort: read a little if available. We avoid selectors for simplicity.
		# This is only used at startup.
		assert self._stdout is not None
		end = time.time() + max_seconds
		self._stdout.flush()
		while time.time() < end:
			# readline() will block, so don't do it. We just break.
			break

	def _index_all(self) -> list[dict[str, Any]]:
		if not os.path.exists(self._index_path):
			return []
		try:
			with open(self._index_path, "r", encoding="utf-8") as f:
				return json.load(f)
		except Exception:
			return []

	def _index_put(self, proc: BackgroundProcess) -> None:
		items = self._index_all()
		items.append(
			{
				"process_id": proc.process_id,
				"pid": proc.pid,
				"command": proc.command,
				"cwd": proc.cwd,
				"log_path": proc.log_path,
				"status_path": proc.status_path,
				"started_at": proc.started_at,
			}
		)
		os.makedirs(os.path.dirname(self._index_path), exist_ok=True)
		with open(self._index_path, "w", encoding="utf-8") as f:
			json.dump(items, f, indent=2)

	def _index_get(self, process_id: str) -> dict[str, Any] | None:
		for item in self._index_all():
			if item.get("process_id") == process_id:
				return item
		return None
