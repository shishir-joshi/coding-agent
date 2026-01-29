# Plan Generation Feature

## Overview

The agent now has **automatic plan generation** for complex multi-step tasks. When you provide a request that requires multiple steps, the agent will:

1. **Analyze** the complexity of your request
2. **Generate** a structured plan with clear steps
3. **Display** the plan for your approval
4. **Execute** the plan step-by-step, updating progress as it goes

## How It Works

### Automatic Detection

The agent uses an LLM to determine if a request needs a plan:

**Needs a plan:**
- Multiple files need changes
- Requires exploration before acting (e.g., "refactor the auth system")
- Has 3+ logical steps
- Involves coordination across components

**Doesn't need a plan:**
- Simple questions ("What does this function do?")
- Single file edits
- Quick lookups/searches
- 1-2 trivial steps

### Plan Display

When a plan is generated, you'll see:

```
┌───────────────────────────────────────────────────┐
│ Active Plan                                       │
│   · Analyze current authentication implementation │
│   · Identify security vulnerabilities             │
│   · Implement token refresh logic                 │
│   · Add tests for new auth flow                   │
│   · Update documentation                          │
└───────────────────────────────────────────────────┘

Approve plan? [Y/n]
```

### Progress Tracking

As the agent works through the plan, the display updates with minimal indicators:

- `✓` Completed steps (dimmed)
- `→` Current step (highlighted)
- `·` Pending steps (dimmed)

Example during execution:

```
┌───────────────────────────────────────────────────┐
│ Active Plan                                       │
│   ✓ Analyze current authentication implementation │
│   ✓ Identify security vulnerabilities             │
│   → Implement token refresh logic                 │
│   · Add tests for new auth flow                   │
│   · Update documentation                          │
└───────────────────────────────────────────────────┐
```

## Usage

### Enable (Default)

Planning is enabled by default:

```bash
python3 -m agent
```

### Disable Planning

If you prefer direct execution without plans:

```bash
python3 -m agent --no-plan
```

### Approving Plans

When prompted with a plan:

- Press `Enter` or type `y` to approve
- Type `n` to reject (returns to prompt without executing)
- Press `Ctrl+C` to cancel

## Examples

### Complex Request (Generates Plan)

```
> Refactor the authentication system to use JWT tokens with refresh token support

* Analyzing...

┌──────────────────────────────────────────────────┐
│ Active Plan                                      │
│   · Read current auth implementation             │
│   · Design JWT token structure                   │
│   · Implement token generation/validation        │
│   · Add refresh token endpoint                   │
│   · Update login/logout flows                    │
│   · Add integration tests                        │
└──────────────────────────────────────────────────┘

Approve plan? [Y/n] y
✓ Plan approved

[Agent proceeds step-by-step...]
```

### Simple Request (No Plan)

```
> What does the login() function do?

* Analyzing...

The `login()` function in `auth.py` handles user authentication...
[Direct answer, no plan needed]
```

## Technical Details

### Plan Structure

```python
@dataclass
class PlanStep:
    description: str
    completed: bool = False

@dataclass
class Plan:
    steps: list[PlanStep]
    current_step_idx: int = 0
    approved: bool = False
```

### Agent Configuration

```python
config = AgentConfig(
    enable_planning=True,  # Enable/disable planning
    max_tool_rounds=8,
    debug=False,
)
```

### Customization

The planning prompt can be customized in `agent/agent_loop.py`:

- `PLANNING_PROMPT`: Template for plan generation
- `_should_plan()`: Logic for determining if a plan is needed
- `_generate_plan()`: Plan generation implementation

## Design Philosophy

### Minimal UI

The plan display is intentionally minimal:
- Simple ASCII box with Unicode symbols
- Clear 3-state indicator system (✓, →, ·)
- No percentage bars or verbose progress messages
- Updates only when steps complete

### User Control

- Plans always require approval (no surprises)
- Easy to reject and rephrase request
- Can disable planning entirely with `--no-plan`
- Ctrl+C works at any point

### Smart Detection

The agent tries to minimize false positives:
- Won't generate plans for simple questions
- Uses LLM judgment
- Errs on the side of direct execution for ambiguous cases

## Future Enhancements

Potential improvements for plan generation:

1. **Plan editing**: Allow users to modify steps before approval
2. **Checkpointing**: Save plan state and resume later
3. **Parallel execution**: Run independent steps concurrently
4. **Plan templates**: Pre-defined plans for common tasks
5. **Learning**: Improve plan generation based on execution outcomes
