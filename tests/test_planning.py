"""Tests for plan generation and tracking."""
import unittest
from agent.agent_loop import Agent, AgentConfig, Plan, PlanStep
from agent.history import HistoryStore


class TestPlanning(unittest.TestCase):
	def setUp(self):
		self.history = HistoryStore(":memory:")

	# Validates a PlanStep defaults to incomplete with the provided description.
	def test_plan_step_creation(self):
		"""Test basic PlanStep creation."""
		step = PlanStep(description="Step 1")
		self.assertEqual(step.description, "Step 1")
		self.assertFalse(step.completed)

	# Confirms Plan initializes with expected state across multiple steps.
	def test_plan_creation(self):
		"""Test Plan with multiple steps."""
		plan = Plan(steps=[
			PlanStep(description="Step 1"),
			PlanStep(description="Step 2"),
			PlanStep(description="Step 3"),
		])
		self.assertEqual(len(plan.steps), 3)
		self.assertEqual(plan.current_step_idx, 0)
		self.assertFalse(plan.approved)
		self.assertFalse(plan.is_complete())

	# Ensures mark_current_complete advances the index and toggles completion flags.
	def test_plan_step_completion(self):
		"""Test marking steps as complete."""
		plan = Plan(steps=[
			PlanStep(description="Step 1"),
			PlanStep(description="Step 2"),
		])
		
		# Mark first step complete
		plan.mark_current_complete()
		self.assertTrue(plan.steps[0].completed)
		self.assertEqual(plan.current_step_idx, 1)
		self.assertFalse(plan.is_complete())
		
		# Mark second step complete
		plan.mark_current_complete()
		self.assertTrue(plan.steps[1].completed)
		self.assertEqual(plan.current_step_idx, 2)
		self.assertTrue(plan.is_complete())

	# Checks get_current_step moves through steps then returns None when finished.
	def test_get_current_step(self):
		"""Test getting current step."""
		plan = Plan(steps=[
			PlanStep(description="Step 1"),
			PlanStep(description="Step 2"),
		])
		
		current = plan.get_current_step()
		self.assertIsNotNone(current)
		self.assertEqual(current.description, "Step 1")
		
		plan.mark_current_complete()
		current = plan.get_current_step()
		self.assertIsNotNone(current)
		self.assertEqual(current.description, "Step 2")
		
		plan.mark_current_complete()
		current = plan.get_current_step()
		self.assertIsNone(current)

	# Verifies planning can be disabled via config and leaves plan unset.
	def test_agent_with_planning_disabled(self):
		"""Test agent when planning is disabled."""
		config = AgentConfig(enable_planning=False)
		agent = Agent(history=self.history, config=config)
		self.assertIsNone(agent.current_plan)

	# Verifies planning is enabled by default and no plan exists until generation.
	def test_agent_with_planning_enabled(self):
		"""Test agent when planning is enabled."""
		config = AgentConfig(enable_planning=True)
		agent = Agent(history=self.history, config=config)
		self.assertIsNone(agent.current_plan)
		self.assertTrue(config.enable_planning)

	# Ensures _generate_plan builds a Plan from LLM analysis.
	def test_generate_plan_from_heuristic(self):
		agent = Agent(history=self.history, config=AgentConfig(enable_planning=True))
		agent.client.chat = lambda *_, **__: {  # type: ignore[attr-defined]
			"message": {
				"content": '{"needs_plan": true, "reasoning": "repo restructure is multi-step", "steps": ["Inspect", "Design", "Implement"]}'
			}
		}

		plan = agent._generate_plan("restructure the repo layout")
		self.assertIsNotNone(plan)
		self.assertGreaterEqual(len(plan.steps), 3)
		self.assertFalse(plan.approved)
		self.assertEqual(plan.current_step_idx, 0)


if __name__ == "__main__":
	unittest.main()
