from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class OpenAICompatClient:
	model: str | None = None

	def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
		api_key = os.environ.get("SHISHIR_OPENAI_API_KEY")
		if not api_key:
			raise RuntimeError("OPENAI_API_KEY is required")

		base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
		model = self.model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

		url = f"{base_url}/chat/completions"
		payload = {
			"model": model,
			"messages": messages,
			"tools": tools,
			"tool_choice": "auto",
			"temperature": 0.2,
		}

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

		with urllib.request.urlopen(req, timeout=120) as resp:
			body = resp.read().decode("utf-8")
			obj = json.loads(body)

		choice = obj["choices"][0]
		msg = choice["message"]
		return {"message": msg, "raw": obj}
