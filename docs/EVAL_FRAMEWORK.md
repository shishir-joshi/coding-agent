# Agent Evaluation Framework

## Overview
Test the agent's capabilities across multiple dimensions using LLM-as-judge to measure quality, correctness, and behavior.

## Capability Dimensions

### 1. Tool Selection & Usage
**What we test:** Does the agent choose appropriate tools and use them correctly?

**Test scenarios:**
- File reading (choose `read_file` vs `grep_search` vs `list_dir`)
- File editing (choose `apply_patch` vs `write_file` appropriately)
- Terminal commands (prefer tools over shell equivalents when applicable)
- Multi-step tool chains (gather context → decide → act)

**Judge criteria:**
- Tool choice appropriateness (0-1 score)
- Argument correctness (all required params present, types valid)
- Minimal tool use (no redundant reads/searches)

**Implementation:**
```python
# Run agent with prompt, capture tool calls
# LLM judge evaluates:
# - Was the tool choice optimal? (yes/no + explanation)
# - Were arguments correct? (yes/no + specific errors if any)
# - Did agent use minimal tools? (count vs expected minimum)
```

---

### 2. Code Correctness
**What we test:** Does the agent produce working code that passes tests?

**Test scenarios:**
- Fix a failing unit test (provide test + broken implementation)
- Implement a function from docstring specification
- Refactor code while preserving behavior (tests still pass)
- Add a new feature with tests

**Judge criteria:**
- Tests pass (automated: run the actual tests)
- Code style/idioms (LLM judge: is it idiomatic Python?)
- Minimal diff size (automated: count changed lines vs baseline)

**Implementation:**
```python
# Setup: broken code + test in temp dir
# Agent fixes it
# Automated: run pytest, capture pass/fail
# LLM judge: review diff for quality/idioms
```

---

### 3. Patch Quality
**What we test:** Does the agent generate clean, minimal, correct patches?

**Test scenarios:**
- Change a function's behavior (small surgical edit)
- Rename a variable across a file
- Fix a bug without touching unrelated code
- Add error handling to existing code

**Judge criteria:**
- Patch applies cleanly (automated: does `apply_patch` succeed?)
- Minimal scope (LLM judge: did it change only what's needed?)
- Correctness (automated: tests pass after patch)

**Implementation:**
```python
# Provide file + change request
# Agent generates patch
# Automated: apply patch, verify it works
# LLM judge: assess if changes are minimal/focused
```

---

### 4. Context Management
**What we test:** Does the agent gather the right context efficiently?

**Test scenarios:**
- Find implementation of a function (search → read → summarize)
- Understand a bug from error message (read traceback → find code → diagnose)
- Cross-file context (find all usages of a class)

**Judge criteria:**
- Search precision (did it find the right files?)
- Read efficiency (minimal redundant reads)
- Completeness (gathered all needed context before acting)

**Implementation:**
```python
# Prompt requiring cross-file context
# Track: which tools called, in what order
# LLM judge: was the search strategy reasonable?
# Automated: did agent find all relevant files (compare to ground truth)?
```

---

### 5. Terminal Command Quality
**What we test:** Does the agent use terminal correctly and safely?

**Test scenarios:**
- Run a command and check output
- Chain commands with shell state (cd + ls)
- Handle long-running processes (background execution)
- Error handling (command not found, non-zero exit)

**Judge criteria:**
- Command safety (no destructive operations without confirmation)
- Correctness (command achieves intended goal)
- Shell awareness (uses persistent session features appropriately)

**Implementation:**
```python
# Prompt: "list files in subdirectory X"
# Agent should: execute_command(cd X && ls) or list_dir(X)
# Automated: verify output matches expectation
# LLM judge: was the command safe and idiomatic?
```

---

### 6. Error Recovery
**What we test:** Does the agent handle failures gracefully?

**Test scenarios:**
- Tool returns error (file not found)
- Patch fails to apply (context mismatch)
- Command fails (exit code 1)
- LLM hits context limit (too many tool rounds)

**Judge criteria:**
- Recognized error (did agent acknowledge failure?)
- Reasonable retry/alternative (did it try a different approach?)
- Clear communication (did it explain what went wrong?)

**Implementation:**
```python
# Inject failure: provide non-existent file path
# Agent should: recognize error, try alternative (grep_search?)
# LLM judge: did agent respond appropriately to failure?
```

---

### 7. Instruction Following
**What we test:** Does the agent follow explicit constraints and requirements?

**Test scenarios:**
- "Use apply_patch, not write_file" → verify tool choice
- "Run tests after changing code" → verify execute_command called
- "Don't change file X" → verify X not in tool calls
- "Explain your reasoning" → verify explanation in output

**Judge criteria:**
- Constraint adherence (automated: check tool calls match requirements)
- Requirement completeness (LLM judge: did it do everything asked?)

**Implementation:**
```python
# Prompt with explicit constraints
# Automated: verify tool calls respect constraints
# LLM judge: assess if all requirements met
```

---

## LLM Judge Implementation

### Judge Prompt Template
```
You are evaluating an AI coding agent's performance.

Task: {task_description}
Agent's actions: {tool_calls_summary}
Agent's output: {agent_response}
Ground truth (if applicable): {expected_behavior}

Evaluate on these criteria:
{criteria_list}

For each criterion, provide:
1. Score (0.0 to 1.0)
2. Reasoning (2-3 sentences)
3. Specific examples from the agent's behavior

Return JSON:
{
  "criteria": [
    {"name": "...", "score": 0.8, "reasoning": "...", "examples": ["..."]}
  ],
  "overall_score": 0.75,
  "summary": "..."
}
```

### Automated Metrics
- **Tool efficiency:** Count of tool calls / minimum required
- **Patch success rate:** % of patches that apply cleanly
- **Test pass rate:** % of scenarios where tests pass after agent edits
- **Context precision:** Relevant files read / total files read
- **Error recovery rate:** % of failures where agent tries alternative

---

## Benchmark Suite Structure

```
evals/
  benchmarks/
    tool_selection/
      test_read_vs_search.py
      test_patch_vs_write.py
    code_correctness/
      test_fix_bug.py
      test_implement_feature.py
    patch_quality/
      test_minimal_diff.py
      test_surgical_edit.py
    context_management/
      test_cross_file_search.py
      test_efficient_context.py
    terminal_quality/
      test_safe_commands.py
      test_background_jobs.py
    error_recovery/
      test_file_not_found.py
      test_patch_fail.py
    instruction_following/
      test_explicit_constraints.py
      test_requirement_completeness.py
  judges/
    llm_judge.py          # LLM-as-judge implementation
    automated_metrics.py  # Test pass rate, patch success, etc.
  runner.py               # Orchestrate eval runs
  reports/                # Store results + comparisons
```

---

## Comparison Metrics (Agent vs Baseline)

### Baseline Options
1. **No-tool baseline:** Same LLM, but no tool access (pure prompt + response)
2. **Simple-agent baseline:** Agent with only `read_file` and `write_file` (no grep/patch/terminal)
3. **Human baseline:** Hand-crafted solutions for benchmark tasks

### Key Comparisons
- Tool efficiency (our agent vs simple-agent)
- Code quality (our agent vs no-tool baseline, judged by LLM)
- Task success rate (% of benchmarks solved correctly)
- Token usage (total tokens per task)

---

## Proposed First Implementation

### Phase 1: Core Eval Harness
1. Create `evals/runner.py` that:
   - Loads a benchmark task (prompt + expected behavior)
   - Runs agent in isolated environment
   - Captures tool calls + final response
   - Saves full trace for judging

2. Create `evals/judges/llm_judge.py`:
   - Takes task + agent trace
   - Calls LLM (gpt-5.2 or similar) with judge prompt
   - Returns structured scores

3. Create 3-5 simple benchmarks:
   - Fix a broken function (code correctness)
   - Apply a surgical edit (patch quality)
   - Find a function implementation (context management)

### Phase 2: Automated Metrics
1. Add test execution (pytest) to measure correctness
2. Add patch application success rate
3. Add tool call counting / efficiency metrics

### Phase 3: Comparison & Iteration
1. Run baselines (no-tool, simple-agent)
2. Generate comparison report
3. Identify weakest capability dimension
4. Improve agent (prompt, tools, or logic) and re-eval

---

## Open Questions / Design Choices

1. **Judge model:** Use same model (gpt-5.2) or stronger model (gpt-4.5/o1)?
   - Tradeoff: cost vs judge quality
   - Recommendation: Start with gpt-4o-mini for speed, upgrade to gpt-5.2 for final evals

2. **Environment isolation:** Run each eval in temp dir or docker container?
   - Recommendation: temp dir + git repo snapshot for speed

3. **Scoring granularity:** Single overall score or per-criterion detailed scores?
   - Recommendation: Both (detailed for debugging, overall for leaderboard)

4. **Benchmark diversity:** How many tasks per dimension?
   - Recommendation: Start with 3-5 per dimension, grow to 10-20 for robustness

5. **Human eval:** Include human judges for qualitative assessment?
   - Recommendation: Phase 3 addition (slow but high-quality signal)
