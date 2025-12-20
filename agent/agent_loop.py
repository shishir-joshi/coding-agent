from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .history import HistoryStore
from .llm_openai_compat import OpenAICompatClient
from .tools import ToolRegistry
from .ui import get_theme, load_ui_config, render_markdown, supports_color, render_plan_banner


DEFAULT_SYSTEM_PROMPT = """You are a small, careful coding assistant running in a local CLI with tool access.

Your job:
- Understand the user's request, gather only the context you need, then implement a correct, minimal change.

Operating rules:
- Be explicit about uncertainty; ask 1–3 targeted questions if the request is ambiguous.
- Prefer tools over guessing. Do not invent file contents, command output, or repository structure.
- Use tools step-by-step: make one tool call at a time when possible, and wait for results before deciding the next step.
- Keep changes surgical: fix the root cause, avoid unrelated refactors.

Editing rules:
- Prefer `apply_patch` for edits.
- Use `write_file` only for new files or full-file rewrites.
- If you change code, run the narrowest relevant tests/commands when practical.

Paths and environment:
- Treat the current working directory as the project root.
- Prefer absolute paths in tool arguments when you are not sure.
- Do not assume external programs are installed; check or handle errors gracefully.

Terminal notes:
- `execute_command` runs in a persistent shell session, so state like `cd` and `export` persists.
- For long-running tasks, use `execute_command` with `is_background=true` then poll with `get_process_output`.

Response style:
- After tool use, briefly summarize what you did and what happened.
- Keep answers concise and actionable.
"""

PLANNING_PROMPT = """Analyze this request and determine if it needs a multi-step plan:

Request: {user_request}

Respond with JSON only:
{{
  "needs_plan": true/false,
  "reasoning": "why it does/doesn't need a plan",
  "steps": ["step 1", "step 2", ...] (only if needs_plan is true)
}}

Needs a plan if:
- Multiple files need changes
- Requires exploration before acting
- Has 3+ logical steps
- Involves coordination across components

Does NOT need a plan if:
- Simple question/explanation
- Single file edit
- Quick lookup/search
- 1-2 trivial steps
"""


@dataclass
class PlanStep:
	"""Represents a single step in an execution plan."""
	description: str
	completed: bool = False


@dataclass
class Plan:
	"""Multi-step execution plan."""
	steps: list[PlanStep] = field(default_factory=list)
	current_step_idx: int = 0
	approved: bool = False

	def mark_current_complete(self) -> None:
		"""Mark current step as completed and advance."""
		if self.current_step_idx < len(self.steps):
			self.steps[self.current_step_idx].completed = True
			self.current_step_idx += 1

	def is_complete(self) -> bool:
		return self.current_step_idx >= len(self.steps)

	def get_current_step(self) -> PlanStep | None:
		if self.current_step_idx < len(self.steps):
			return self.steps[self.current_step_idx]
		return None


@dataclass
class AgentConfig:
	model: str | None = None
	max_tool_rounds: int = 8
	debug: bool = False
	enable_planning: bool = True


class Agent:
	def __init__(self, history: HistoryStore, config: AgentConfig | None = None, ui_callback: Callable[[str], None] | None = None) -> None:
		self.history = history
		self.config = config or AgentConfig()
		self.tools = ToolRegistry()
		self.client = OpenAICompatClient(model=self.config.model)
		self._debug_theme = None
		self._debug_round_idx = 0
		self.current_plan: Plan | None = None
		self.ui_callback = ui_callback  # For updating banner
		self.reset()

	def _debug_render_md(self, text: str) -> str:
		"""Render markdown in debug logs when color is available."""
		theme = self._get_debug_theme()
		if theme and theme is not False:
			try:
				return render_markdown(text, theme)
			except Exception:
				return text
		return text

	def _get_debug_theme(self):
		if self._debug_theme is not None:
			return self._debug_theme
		if not supports_color():
			self._debug_theme = False
			return self._debug_theme
		cfg = load_ui_config(".agent/ui.json")
		self._debug_theme = get_theme(cfg.get("theme"))
		return self._debug_theme

	def _debug_prefix(self, role: str | None = None) -> str:
		"""Color the [debug] tag by role; default gray, user/assistant orange."""
		theme = self._get_debug_theme()
		if theme and theme is not False:
			if role in {"user", "assistant"}:
				return theme.a("[debug]")
			return theme.d("[debug]")
		return "[debug]"

	def _debug_role(self, role: str | None) -> str:
		theme = self._get_debug_theme()
		label = str(role or "?")
		if not (theme and theme is not False):
			return label
		if label in {"system", "developer"}:
			return theme.d(label)
		if label == "user":
			return theme.a(label)
		if label == "assistant":
			return theme.t(label)
		if label == "tool":
			return theme.ok(label)
		return theme.t(label)

	def _debug_label(self, label: str, *, kind: str = "dim") -> str:
		theme = self._get_debug_theme()
		if not (theme and theme is not False):
			return label
		if kind == "accent":
			return theme.a(label)
		if kind == "ok":
			return theme.ok(label)
		if kind == "err":
			return theme.err(label)
		return theme.d(label)

	def reset(self) -> None:
		self.messages: list[dict[str, Any]] = [
			{"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
		]

	def _heuristic_plan_steps(self, user_text: str) -> list[str]:
		"""Lightweight keyword-based plan trigger for deterministic cases."""
		text = user_text.lower()
		if any(k in text for k in ["reorganize", "re-org", "reorg", "restructure", "re-structure", "layout", "structure"]):
			return [
				"Inspect the current repository structure and key config files",
				"Identify natural boundaries (src/tests/docs/examples/scripts/config)",
				"Propose a target layout with folders and naming",
				"Outline migration steps and risks",
			]
		if any(k in text for k in ["plan", "roadmap", "steps", "timeline"]):
			return [
				"Clarify goals and constraints",
				"Draft a multi-step execution plan",
				"Execute steps and validate the result",
			]
		return []

	def dump_context(self) -> str:
		return json.dumps(self.messages, indent=2, ensure_ascii=False)

	def dump_tools(self, *, as_json: bool = False) -> str:
		schemas = self.tools.tool_schemas()
		if as_json:
			return json.dumps(schemas, indent=2, ensure_ascii=False)
		lines: list[str] = []
		for item in schemas:
			fn = (item or {}).get("function") or {}
			name = fn.get("name") or "(unknown)"
			desc = fn.get("description") or ""
			lines.append(f"- {name}: {desc}")
		return "\n".join(lines)

	def _should_plan(self, user_text: str) -> tuple[bool, list[str], str]:
		"""Determine if request needs a plan.
		
		Returns: (needs_plan, steps, reasoning)
		"""
		if not self.config.enable_planning:
			return False, [], "planning disabled"

		heuristic_steps = self._heuristic_plan_steps(user_text)
		if heuristic_steps:
			return True, heuristic_steps, "heuristic trigger"
		
		# Quick heuristics for obviously simple queries
		if len(user_text.split()) < 10 and any(q in user_text.lower() for q in ["what", "how", "why", "show", "list", "?"]):
			return False, [], "simple query"
		
		# Ask LLM to analyze
		try:
			prompt = PLANNING_PROMPT.format(user_request=user_text)
			resp = self.client.chat(
				messages=[{"role": "user", "content": prompt}],
				tools=None,
			)
			content = resp["message"].get("content", "")
			
			# Extract JSON
			if "{" in content and "}" in content:
				json_str = content[content.find("{"):content.rfind("}") + 1]
				data = json.loads(json_str)
				needs_plan = data.get("needs_plan", False)
				steps = data.get("steps", [])
				reasoning = data.get("reasoning", "")
				if needs_plan and not steps and heuristic_steps:
					steps = heuristic_steps
				return needs_plan, steps, reasoning or "llm analysis"
		except Exception:
			pass

		if heuristic_steps:
			return True, heuristic_steps, "heuristic fallback"

		return False, [], "planning analysis failed"

	def _generate_plan(self, user_text: str) -> Plan | None:
		"""Generate a plan for the user's request."""
		needs_plan, steps, reasoning = self._should_plan(user_text)
		
		if not needs_plan or not steps:
			return None
		
		plan = Plan(
			steps=[PlanStep(description=s) for s in steps],
			approved=False,
		)
		return plan

	def chat(self, user_text: str, *, auto_approve_plan: bool = False) -> str:
		self.history.append_event({"type": "user", "text": user_text})
		
		# Check if we need a plan
		if self.config.enable_planning and not self.current_plan:
			plan = self._generate_plan(user_text)
			if plan:
				self.current_plan = plan
				# Return plan for approval (caller will handle display)
				if not auto_approve_plan:
					return "__PLAN_APPROVAL_NEEDED__"
				else:
					self.current_plan.approved = True
		
		self.messages.append({"role": "user", "content": user_text})

		for _round in range(self.config.max_tool_rounds):
			if self.config.debug:
				self._debug_print_round_header(_round)
				self._debug_print_request_summary()

			resp = self.client.chat(
				messages=self.messages,
				tools=self.tools.tool_schemas(),
			)

			if self.config.debug:
				self.history.append_event({"type": "debug", "llm_raw": resp})
				self._debug_print_response_summary(resp.get("message") or {})

			assistant_msg = resp["message"]
			self.messages.append(assistant_msg)

			tool_calls = assistant_msg.get("tool_calls") or []
			if not tool_calls:
				text = assistant_msg.get("content") or ""
				self.history.append_event({"type": "assistant", "text": text})
				
				# Mark current plan step as complete
				if self.current_plan and not self.current_plan.is_complete():
					self.current_plan.mark_current_complete()
					if self.ui_callback:
						self.ui_callback("plan_updated")
					if not self.current_plan.is_complete():
						# Continue to next step
						next_step = self.current_plan.get_current_step()
						if next_step:
							self.messages.append({"role": "user", "content": f"Continue with next step: {next_step.description}"})
							continue
					else:
						# Plan complete
						self.current_plan = None
				
				return text

			# Execute tool calls and feed tool results back.
			for call in tool_calls:
				tool_name = call["function"]["name"]
				args_json = call["function"].get("arguments") or "{}"
				try:
					args = json.loads(args_json)
				except json.JSONDecodeError:
					args = {"_raw": args_json}

				if self.config.debug:
					print(
						self._debug_prefix()
						+ " "
						+ self._debug_label("tool_call", kind="ok")
						+ ": "
						+ self._debug_label(tool_name, kind="accent")
						+ f" args={args_json}"
					)

				self.history.append_event({"type": "tool_call", "name": tool_name, "args": args})
				result = self.tools.execute(tool_name, args)
				self.history.append_event({"type": "tool_result", "name": tool_name, "result": result})
				if self.config.debug:
					preview = self._truncate(json.dumps(result, ensure_ascii=False), 2000)
					md_preview = self._debug_render_md("```\n" + preview + "\n```")
					print(
						self._debug_prefix()
						+ " "
						+ self._debug_label("tool_result", kind="ok")
						+ ": "
						+ self._debug_label(tool_name, kind="accent")
						+ "\n"
						+ md_preview
					)

				self.messages.append(
					{
						"role": "tool",
						"tool_call_id": call["id"],
						"name": tool_name,
						"content": json.dumps(result, ensure_ascii=False),
					}
				)

		# If we hit the limit, return a safe message.
		text = "(stopped: too many tool rounds; try a smaller request)"
		self.history.append_event({"type": "assistant", "text": text})
		return text

	def _debug_print_round_header(self, round_idx: int) -> None:
		self._debug_round_idx = round_idx
		head = f"===== round {round_idx + 1}/{self.config.max_tool_rounds} ====="
		print("\n" + self._debug_prefix() + " " + self._debug_label(head, kind="accent"))

	def _debug_print_request_summary(self) -> None:
		tool_names = []
		for item in self.tools.tool_schemas():
			fn = (item or {}).get("function") or {}
			name = fn.get("name")
			if name:
				tool_names.append(name)
		print(self._debug_prefix() + " " + self._debug_label("tools", kind="dim") + ": " + ", ".join(tool_names))
		print(self._debug_prefix() + " " + self._debug_label("messages", kind="dim") + f": {len(self.messages)}")
		# Print a compact view of messages (role + preview)
		for idx, m in enumerate(self.messages[-12:], start=max(0, len(self.messages) - 12)):
			role = m.get("role")
			content = m.get("content")
			name = m.get("name")
			if isinstance(content, str):
				preview = self._truncate(content.replace("\n", "\\n"), 200)
			else:
				preview = self._truncate(json.dumps(content, ensure_ascii=False), 200)
			suffix = f" name={name}" if name else ""
			role_s = self._debug_role(role)
			line = f"  {idx}: {role_s}{suffix}: {preview}"
			print(self._debug_prefix(role) + " " + line)

	def _debug_print_response_summary(self, assistant_msg: dict[str, Any]) -> None:
		content = assistant_msg.get("content")
		if isinstance(content, str) and content.strip():
			label = self._debug_role("assistant")
			preview = self._truncate(content, 1200)
			rendered = self._debug_render_md(preview)
			print(self._debug_prefix("assistant") + f" {label}: {rendered}")
		tool_calls = assistant_msg.get("tool_calls") or []
		if tool_calls:
			names = [c.get("function", {}).get("name", "?") for c in tool_calls]
			print(
				self._debug_prefix()
				+ " "
				+ self._debug_label("assistant requested tools", kind="ok")
				+ ": "
				+ ", ".join(names)
			)

	@staticmethod
	def _truncate(s: str, n: int) -> str:
		if len(s) <= n:
			return s
		return s[: n - 3] + "..."
