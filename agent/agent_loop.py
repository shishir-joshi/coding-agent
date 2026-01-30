from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from .history import HistoryStore
from .llm_openai_compat import OpenAICompatClient
from .tools import ToolRegistry
from .ui_layer import get_theme, load_ui_config, render_markdown, supports_color, render_plan_banner
from .planning import Plan, PlanStep, generate_plan


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

FINALIZE_PROMPT = """You are finalizing the response after executing a multi-step plan.

Given:
- The original user request
- The plan steps
- The intermediate assistant outputs produced while executing each step

Write a concise final response for the user that summarizes what was done and the outcome.

Rules:
- Be succinct and concrete (bullet points are OK).
- Do not include internal tool logs or raw JSON.
- If something failed or was skipped, say so.
- If no meaningful work was done, say that.
"""


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
		self._plan_intermediate_outputs: list[dict[str, Any]] = []
		self.ui_callback = ui_callback  # For updating banner
		self.reset()

	def _finalize_plan_response(self, *, original_request: str, plan: Plan, intermediate_outputs: list[dict[str, Any]]) -> str:
		"""Ask the LLM to produce a final user-facing summary of the plan execution."""
		steps = [s.description for s in plan.steps]
		payload = {
			"original_request": original_request,
			"plan_steps": steps,
			"intermediate_outputs": [o.get("text", "") for o in intermediate_outputs if o.get("text")],
		}
		resp = self.client.chat(
			messages=[
				{"role": "system", "content": FINALIZE_PROMPT},
				{"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
			],
			tools=None,
		)
		return (resp.get("message") or {}).get("content") or ""

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
		"""Deprecated: previously returned hard-coded plan steps.

		Planning is now LLM-driven; keep this method for API compatibility.
		"""
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
		
		This delegates to the planning module's should_plan function.
		"""
		from .planning.detector import should_plan as planning_should_plan
		return planning_should_plan(self.client, user_text, self.config.enable_planning)


	def _generate_plan(self, user_text: str) -> Plan | None:
		"""Generate a plan for the user's request.
		
		This delegates to the planning module's generate_plan function.
		"""
		return generate_plan(self.client, user_text, self.config.enable_planning)

	def chat(self, user_text: str, *, auto_approve_plan: bool = False) -> str:
		self.history.append_event({"type": "user", "text": user_text})
		original_request = user_text
		
		# Check if we need a plan
		if self.config.enable_planning and not self.current_plan:
			plan = self._generate_plan(user_text)
			if plan:
				self.current_plan = plan
				self._plan_intermediate_outputs = []
				# Return plan for approval (caller will handle display)
				if not auto_approve_plan:
					return "__PLAN_APPROVAL_NEEDED__"
				else:
					self.current_plan.approved = True
		
		self.messages.append({"role": "user", "content": user_text})

		for _round in range(self.config.max_tool_rounds):
			if self.config.debug:
				self._debug_print_round_header(_round)
				self._debug_print_request_summary(round_idx=_round)

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
				if self.current_plan:
					self._plan_intermediate_outputs.append({"step_idx": self.current_plan.current_step_idx, "text": text})
				
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
						# Plan complete: produce a final, LLM-driven summary response.
						completed_plan = self.current_plan
						intermediate = list(self._plan_intermediate_outputs)
						self.current_plan = None
						self._plan_intermediate_outputs = []
						try:
							final = self._finalize_plan_response(
								original_request=original_request,
								plan=completed_plan,
								intermediate_outputs=intermediate,
							)
							if final.strip():
								self.history.append_event({"type": "assistant", "text": final, "finalized": True})
								return final
						except Exception:
							pass

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

	def _debug_print_request_summary(self, *, round_idx: int) -> None:
		# Default: print the full request/tools/messages summary only once (round 0).
		# Subsequent rounds tend to be iterative tool calls, so re-printing the full
		# message list is noisy. When executing a multi-step plan, we still print the
		# newly-started step (see below).
		if round_idx > 0 and self.current_plan is None:
			return

		# When executing an approved multi-step plan, each new round typically corresponds
		# to an auto-continued step (we append a synthetic user message like
		# "Continue with next step: ..."). In debug mode this used to spam the full
		# message list every round, so for subsequent rounds we print only the step.
		if round_idx > 0 and self.current_plan is not None:
			last = self.messages[-1] if self.messages else {}
			if last.get("role") == "user":
				content = last.get("content")
				if isinstance(content, str) and content.startswith("Continue with next step:"):
					step_desc = content.split(":", 1)[1].strip() if ":" in content else content
					print(
						self._debug_prefix()
						+ " "
						+ self._debug_label("step", kind="accent")
						+ ": "
						+ self._truncate(step_desc, 200)
					)
					return

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
