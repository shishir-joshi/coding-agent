"""Planning detection and generation."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .models import Plan, PlanStep, PLANNING_PROMPT

if TYPE_CHECKING:
	from ..llm_openai_compat import OpenAICompatClient


def should_plan(client: OpenAICompatClient, user_text: str, enable_planning: bool = True) -> tuple[bool, list[str], str]:
	"""Determine if request needs a plan.
	
	Returns: (needs_plan, steps, reasoning)
	"""
	if not enable_planning:
		return False, [], "planning disabled"

	# Quick heuristics for obviously simple queries
	if len(user_text.split()) < 10 and any(q in user_text.lower() for q in ["what", "how", "why", "show", "list", "?"]):
		return False, [], "simple query"
	
	# Ask LLM to analyze
	try:
		prompt = PLANNING_PROMPT.format(user_request=user_text)
		resp = client.chat(
			messages=[{"role": "user", "content": prompt}],
			tools=None,
		)
		content = resp["message"].get("content", "")
		
		# Extract JSON
		if "{" in content and "}" in content:
			json_str = content[content.find("{"):content.rfind("}") + 1]
			data = json.loads(json_str)
			needs_plan = bool(data.get("needs_plan", False))
			steps = data.get("steps", [])
			reasoning = data.get("reasoning", "")
			if needs_plan and not isinstance(steps, list):
				steps = []
			return needs_plan, steps, reasoning or "llm analysis"
	except Exception:
		pass

	return False, [], "planning analysis failed"


def generate_plan(client: OpenAICompatClient, user_text: str, enable_planning: bool = True) -> Plan | None:
	"""Generate a plan for the user's request."""
	needs_plan, steps, _reasoning = should_plan(client, user_text, enable_planning)
	
	if not needs_plan or not steps:
		return None
	
	plan = Plan(
		steps=[PlanStep(description=s) for s in steps],
		approved=False,
	)
	return plan
