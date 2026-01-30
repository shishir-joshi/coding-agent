"""Context management and organization for long-running conversations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextMessage:
	"""Represents a single message in the conversation context."""
	role: str
	content: str
	metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextManager:
	"""Manages conversation context including organization, compression, and retrieval."""
	
	messages: list[ContextMessage] = field(default_factory=list)
	max_context_tokens: int = 100000
	compression_threshold: int = 80000
	
	def add_message(self, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
		"""Add a message to context."""
		msg = ContextMessage(role=role, content=content, metadata=metadata or {})
		self.messages.append(msg)
	
	def get_context_size(self) -> int:
		"""Estimate context size in tokens (rough approximation)."""
		total = 0
		for msg in self.messages:
			total += len(msg.content.split())  # Rough token count
		return total
	
	def should_compress(self) -> bool:
		"""Check if context should be compressed."""
		return self.get_context_size() > self.compression_threshold
	
	def compress_context(self) -> list[ContextMessage]:
		"""Compress older messages while keeping recent ones."""
		# Keep system message and last N messages
		if len(self.messages) <= 10:
			return self.messages
		
		# Keep first (system) and last 10
		compressed = [self.messages[0]] + self.messages[-10:]
		self.messages = compressed
		return compressed
	
	def retrieve_recent(self, n: int = 20) -> list[ContextMessage]:
		"""Retrieve last N messages."""
		return self.messages[-n:]
	
	def dump(self) -> list[dict[str, Any]]:
		"""Export context as list of dicts."""
		return [
			{"role": msg.role, "content": msg.content, **msg.metadata}
			for msg in self.messages
		]
