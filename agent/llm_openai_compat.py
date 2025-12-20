from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class OpenAICompatClient:
	model: str | None = None
	timeout_s: int = 120
	max_retries: int = 4

	def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
		"""Call OpenAI using the Responses API and return a chat-completions-like shape.

		We keep this signature stable so the rest of the project (agent loop + tests)
		doesn't need to care whether the backend is chat.completions or responses.
		"""
		api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("SHISHIR_OPENAI_API_KEY")
		if not api_key:
			raise RuntimeError("OPENAI_API_KEY is required")

		base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
		model = self.model or os.environ.get("OPENAI_MODEL", "gpt-5.2")

		url = f"{base_url}/responses"
		payload: dict[str, Any] = {
			"model": model,
			"input": self._to_responses_input(messages),
			"tools": self._to_responses_tools(tools),
			"temperature": 0.2,
			"text": {"format": {"type": "text"}},
		}

		# Optional knobs (avoid sending fields models might reject unless set)
		reasoning_effort = os.environ.get("OPENAI_REASONING_EFFORT")
		if reasoning_effort:
			payload["reasoning"] = {"effort": reasoning_effort}

		store = os.environ.get("OPENAI_STORE")
		if store is not None:
			payload["store"] = store.lower() in {"1", "true", "yes"}

		obj = self._post_json(url, payload, api_key=api_key)
		msg = self._responses_to_chat_message(obj)
		return {"message": msg, "raw": obj}

	def _post_json(self, url: str, payload: dict[str, Any], *, api_key: str) -> dict[str, Any]:
		data = json.dumps(payload).encode("utf-8")
		req = urllib.request.Request(
			url,
			data=data,
			method="POST",
			headers={
				"Content-Type": "application/json",
				"Authorization": f"Bearer {api_key}",
			},
		)

		last_err: Exception | None = None
		for attempt in range(self.max_retries + 1):
			try:
				with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
					body = resp.read().decode("utf-8")
					return json.loads(body)
			except urllib.error.HTTPError as e:
				last_err = e
				status = getattr(e, "code", None)
				# Try to parse error body for better messages
				try:
					err_body = e.read().decode("utf-8", errors="replace")
					err_obj = json.loads(err_body)
				except Exception:
					err_body = ""
					err_obj = {}

				# Retry on transient errors
				if status in {429, 500, 502, 503, 504} and attempt < self.max_retries:
					self._sleep_backoff(attempt)
					continue

				# Friendlier error messages for rate limits
				if status == 429:
					err_msg = err_obj.get("error", {}).get("message", "")
					if err_msg:
						raise RuntimeError(f"Rate limit exceeded: {err_msg}") from e
					raise RuntimeError(f"OpenAI HTTP 429: {err_body}".strip()) from e

				# Generic error
				raise RuntimeError(f"OpenAI HTTP {status}: {err_body}".strip()) from e
			except (urllib.error.URLError, TimeoutError) as e:
				last_err = e
				if attempt < self.max_retries:
					self._sleep_backoff(attempt)
					continue
				raise

		assert last_err is not None
		raise last_err

	@staticmethod
	def _sleep_backoff(attempt: int) -> None:
		# Exponential backoff with jitter
		base = min(8.0, 0.5 * (2**attempt))
		time.sleep(base + random.random() * 0.2)

	@staticmethod
	def _to_responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
		"""Convert chat-completions-like messages into Responses API input items."""
		items: list[dict[str, Any]] = []
		for m in messages:
			role = m.get("role")
			content = m.get("content")
			tool_calls = m.get("tool_calls")

			if role == "system":
				role = "developer"

			if role == "tool":
				call_id = m.get("tool_call_id")
				if call_id:
					items.append({"type": "function_call_output", "call_id": call_id, "output": str(content or "")})
				continue

			# If an assistant message included tool calls, represent them explicitly so that
			# subsequent function_call_output items can be validated by the API.
			if role == "assistant" and tool_calls:
				if isinstance(tool_calls, list):
					for call in tool_calls:
						if not isinstance(call, dict):
							continue
						call_id = call.get("id")
						fn = call.get("function") or {}
						name = fn.get("name")
						args = fn.get("arguments")
						if not call_id or not name:
							continue
						# Responses expects `arguments` to be a string (typically JSON).
						if isinstance(args, str):
							arguments = args
						elif args is None:
							arguments = "{}"
						else:
							arguments = json.dumps(args)
						items.append({"type": "function_call", "call_id": str(call_id), "name": str(name), "arguments": arguments})

			if content is None:
				continue

			# Per Responses API conventions: assistant content uses output_text.
			block_type = "output_text" if role == "assistant" else "input_text"
			text_key = "text" if block_type in {"input_text", "output_text"} else "text"

			if isinstance(content, str):
				items.append({"role": role, "content": [{"type": block_type, text_key: content}]})
			else:
				# Best-effort: stringify non-text content
				items.append({"role": role, "content": [{"type": block_type, text_key: json.dumps(content)}]})
		return items

	@staticmethod
	def _to_responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
		"""Convert chat-completions tool schema to Responses API tool schema.

		Chat-completions shape:
		  {"type":"function","function": {"name":...,"description":...,"parameters":...}}

		Responses shape:
		  {"type":"function","name":...,"description":...,"parameters":...}
		"""
		out: list[dict[str, Any]] = []
		for t in tools:
			if not isinstance(t, dict):
				continue
			if t.get("type") != "function":
				out.append(t)
				continue
			fn = t.get("function")
			if isinstance(fn, dict):
				name = fn.get("name")
				desc = fn.get("description")
				params = fn.get("parameters")
				tool_obj: dict[str, Any] = {"type": "function", "name": name}
				if desc is not None:
					tool_obj["description"] = desc
				if params is not None:
					tool_obj["parameters"] = params
				out.append(tool_obj)
			else:
				out.append(t)
		return out

	@staticmethod
	def _responses_to_chat_message(resp: dict[str, Any]) -> dict[str, Any]:
		"""Parse a Responses API response into a chat-completions-like assistant message."""
		text_parts: list[str] = []
		tool_calls: list[dict[str, Any]] = []

		output = resp.get("output")
		if isinstance(output, list):
			for item in output:
				if not isinstance(item, dict):
					continue
				t = item.get("type")
				if t == "message":
					content = item.get("content")
					if isinstance(content, list):
						for block in content:
							if isinstance(block, dict) and block.get("type") == "output_text":
								text = block.get("text")
								if isinstance(text, str):
									text_parts.append(text)
					continue

				# Tool calls in Responses
				if t in {"function_call", "tool_call"}:
					call_id = item.get("call_id") or item.get("id")
					name = item.get("name")
					args = item.get("arguments")
					if isinstance(args, dict):
						args_json = json.dumps(args)
					elif isinstance(args, str):
						args_json = args
					else:
						args_json = "{}"
					if call_id and name:
						tool_calls.append(
							{
								"id": str(call_id),
								"type": "function",
								"function": {"name": str(name), "arguments": args_json},
							}
						)
					continue

		# Fallbacks some models/SDKs include
		if not text_parts:
			out_text = resp.get("output_text")
			if isinstance(out_text, str):
				text_parts.append(out_text)

		content_text = "".join(text_parts).strip() if text_parts else None
		return {"role": "assistant", "content": content_text, "tool_calls": tool_calls}
