"""Planning models and constants."""

from __future__ import annotations

from dataclasses import dataclass, field


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
