from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class HistoryStore:
	path: str

	def append_event(self, event: dict[str, Any]) -> None:
		os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
		record = {"ts": time.time(), **event}
		with open(self.path, "a", encoding="utf-8") as f:
			f.write(json.dumps(record, ensure_ascii=False) + "\n")

	def tail(self, n: int) -> str:
		if n <= 0:
			return ""
		if not os.path.exists(self.path):
			return "(no history yet)"

		with open(self.path, "r", encoding="utf-8") as f:
			lines = f.readlines()
			chunk = lines[-n:]
		return "".join(chunk)
