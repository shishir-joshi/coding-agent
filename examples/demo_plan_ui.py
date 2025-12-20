#!/usr/bin/env python3
"""Demo script showing plan generation UI (without real LLM calls)."""

from agent.agent_loop import Plan, PlanStep
from agent.ui import get_theme, render_plan_banner, THEMES

# Demo plan
plan = Plan(steps=[
    PlanStep(description="Analyze current authentication implementation", completed=True),
    PlanStep(description="Design JWT token structure", completed=True),
    PlanStep(description="Implement token generation and validation logic", completed=False),
    PlanStep(description="Add refresh token endpoint", completed=False),
    PlanStep(description="Update login/logout flows", completed=False),
    PlanStep(description="Write integration tests", completed=False),
])

plan.current_step_idx = 2  # Currently on step 3

theme = THEMES[0]  # Dark theme

print("\n=== Plan Display Demo ===\n")
print("This is how the plan appears during execution:")
print()
print(render_plan_banner(plan, theme))
print()
print("Legend:")
print("  ✓ = Completed step (dimmed)")
print("  → = Current step (highlighted)")
print("  · = Pending step (dimmed)")
print()
