from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .history import HistoryStore
from .llm_openai_compat import OpenAICompatClient
from .tools import ToolRegistry


DEFAULT_SYSTEM_PROMPT = """You are a small, careful coding assistant running in a local CLI.

Rules:
- If a tool is needed, call it.
- Keep edits minimal and correct.
- Prefer apply_patch for changes; only use write_file for new files or full rewrites.
- After using tools, explain what you did briefly.

You have access to tools defined in the tool schema. Use them when helpful.
"""


@dataclass
class AgentConfig:
	model: str | None = None
	max_tool_rounds: int = 8
	debug: bool = False


class Agent:
	def __init__(self, history: HistoryStore, config: AgentConfig | None = None) -> None:
		self.history = history
		self.config = config or AgentConfig()
		self.tools = ToolRegistry()
		self.client = OpenAICompatClient(model=self.config.model)
		self.reset()

	def reset(self) -> None:
		self.messages: list[dict[str, Any]] = [
			{"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
		]

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

	def chat(self, user_text: str) -> str:
		self.history.append_event({"type": "user", "text": user_text})
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
					print(f"[debug] tool_call: {tool_name} args={args_json}")

				self.history.append_event({"type": "tool_call", "name": tool_name, "args": args})
				result = self.tools.execute(tool_name, args)
				self.history.append_event({"type": "tool_result", "name": tool_name, "result": result})
				if self.config.debug:
					print(f"[debug] tool_result: {tool_name} {self._truncate(json.dumps(result, ensure_ascii=False), 2000)}")

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
		print(f"\n[debug] ===== round {round_idx + 1}/{self.config.max_tool_rounds} =====")

	def _debug_print_request_summary(self) -> None:
		tool_names = []
		for item in self.tools.tool_schemas():
			fn = (item or {}).get("function") or {}
			name = fn.get("name")
			if name:
				tool_names.append(name)
		print(f"[debug] tools: {', '.join(tool_names)}")
		print(f"[debug] messages: {len(self.messages)}")
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
			print(f"[debug]   {idx}: {role}{suffix}: {preview}")

	def _debug_print_response_summary(self, assistant_msg: dict[str, Any]) -> None:
		content = assistant_msg.get("content")
		if isinstance(content, str) and content.strip():
			print(f"[debug] assistant: {self._truncate(content.replace('\n', '\\n'), 400)}")
		tool_calls = assistant_msg.get("tool_calls") or []
		if tool_calls:
			names = [c.get("function", {}).get("name", "?") for c in tool_calls]
			print(f"[debug] assistant requested tools: {', '.join(names)}")

	@staticmethod
	def _truncate(s: str, n: int) -> str:
		if len(s) <= n:
			return s
		return s[: n - 3] + "..."
