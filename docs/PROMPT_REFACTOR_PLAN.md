# Prompt Refactor Plan (Developer-Only, Canonical Prompts)

This document is an implementation guide for refactoring prompt definitions and usage in this repo.

**Goal:** Stop defining LLM prompts inline in Python modules. Centralize prompts as developer-owned template files and provide a small registry/helper API to load/render them.

**Non-goals (for this iteration):**
- No end-user prompt overrides (no `.agent/prompts` or env overrides).
- No per-model prompt variants.
- No prompt content changes beyond moving text verbatim (unless explicitly called out).

---

## 0) Current prompt inventory (what exists today)

### Product prompts
1. `agent/agent_loop.py`
   - Defines:
     - `DEFAULT_SYSTEM_PROMPT` (large system instruction block)
     - `FINALIZE_PROMPT` (system prompt used to summarize plan execution)
   - Uses:
     - `reset()` seeds `self.messages` with `DEFAULT_SYSTEM_PROMPT`
     - `_finalize_plan_response()` sends `FINALIZE_PROMPT` as system message

2. `agent/planning/models.py`
   - Defines:
     - `PLANNING_PROMPT` (template with `{user_request}`; instructs JSON-only output)

3. `agent/planning/detector.py`
   - Uses:
     - `PLANNING_PROMPT.format(user_request=user_text)`
     - Sends as a single user message to the model

### Tests (non-product prompts)
- `tests/test_live_openai_models.py`: inline system prompt `"You are a helpful assistant."`
- `tests/test_llm_openai_compat.py`: inline system prompt `"you are helpful"`

### Non-LLM prompt
- `agent/repl.py`: terminal input prompt `"> "` (not part of LLM prompt refactor)

---

## 1) Files to add (new prompt system)

### 1.1 Create prompt templates (developer-owned)
Add directory:
- `agent/prompts/templates/`

Add template files (copy prompt text verbatim from current constants):
1. `agent/prompts/templates/agent_system.md`
   - Content: current `DEFAULT_SYSTEM_PROMPT` from `agent/agent_loop.py`

2. `agent/prompts/templates/finalize_plan.md`
   - Content: current `FINALIZE_PROMPT` from `agent/agent_loop.py`

3. `agent/prompts/templates/planning_detect.md`
   - Content: current `PLANNING_PROMPT` from `agent/planning/models.py`
   - Must retain `{user_request}` placeholder.

**Template format:** plain text/markdown with Python `str.format()` placeholders.

### 1.2 Add prompt IDs
Add file:
- `agent/prompts/ids.py`

Define stable IDs (string constants or Enum):
- `AGENT_SYSTEM = "agent.system"`
- `FINALIZE_PLAN = "agent.finalize_plan"`
- `PLANNING_DETECT = "planning.detect"`

### 1.3 Add prompt registry/renderer
Add file:
- `agent/prompts/registry.py`

Responsibilities:
- Map prompt IDs to template file paths.
- Load template text from package files.
- Render with `str.format(**vars)`.
- Validate required variables per prompt ID.

Suggested API:
- `render(prompt_id: str, **vars) -> str`
- `system_message(prompt_id: str, **vars) -> dict`
- `user_message(prompt_id: str, **vars) -> dict`

Validation behavior:
- If required vars are missing, raise a clear exception (e.g., `KeyError` with message listing missing keys).

Implementation notes:
- Use `importlib.resources` (preferred) or filesystem relative paths.
- Keep dependency-free.

### 1.4 Export prompt helpers
Add file:
- `agent/prompts/__init__.py`

Export:
- IDs
- `render`, `system_message`, `user_message`

---

## 2) Files to modify (replace inline prompt constants)

### 2.1 `agent/agent_loop.py`

**What to change:**
- Remove inline constants `DEFAULT_SYSTEM_PROMPT` and `FINALIZE_PROMPT`.
- Import prompt helpers:
  - `from .prompts import PromptIds (or ids), system_message, render` (exact names depend on implementation).

**Where to update usage:**
1. `reset()`
   - Replace `{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}`
   - With `system_message(AGENT_SYSTEM)`

2. `_finalize_plan_response()`
   - Replace `{"role": "system", "content": FINALIZE_PROMPT}`
   - With `system_message(FINALIZE_PLAN)`

**Constraints:**
- Do not change prompt text content (copy verbatim into templates).
- Do not change message roles/structure beyond using helper functions.

### 2.2 `agent/planning/models.py`

**What to change:**
- Remove `PLANNING_PROMPT` constant from this file.
- Keep `Plan` and `PlanStep` dataclasses unchanged.

### 2.3 `agent/planning/detector.py`

**What to change:**
- Stop importing `PLANNING_PROMPT`.
- Import prompt helper(s): `render` and `PLANNING_DETECT` ID.

**Where to update usage:**
- Replace:
  - `prompt = PLANNING_PROMPT.format(user_request=user_text)`
- With:
  - `prompt = render(PLANNING_DETECT, user_request=user_text)`

**Constraints:**
- Keep the rest of planning logic unchanged.

### 2.4 `agent/planning/__init__.py`

**What to change:**
- Remove re-export of `PLANNING_PROMPT` from `__all__`.
- Ensure exports remain correct for `Plan`, `PlanStep`, `should_plan`, `generate_plan`.

---

## 3) Docs to update (keep docs consistent)

### 3.1 `docs/PLAN_GENERATION.md`

**What to change:**
- Update the “Customization” section that currently points to `agent/agent_loop.py` for `PLANNING_PROMPT`.
- Replace with:
  - Planning prompt template path: `agent/prompts/templates/planning_detect.md`
  - Mention prompt registry usage (briefly).

### 3.2 `docs/PLAN_IMPLEMENTATION.md`

**What to change:**
- Update references to `PLANNING_PROMPT` location.
- Optionally add a short section: “Prompt templates live under `agent/prompts/templates/`.”

---

## 4) Tests to add/update

### 4.1 Add new tests for prompt loading/rendering
Add file:
- `tests/test_prompts.py`

Test cases:
1. `test_render_agent_system_loads()`
   - `render(AGENT_SYSTEM)` returns non-empty string.

2. `test_render_finalize_plan_loads()`
   - `render(FINALIZE_PLAN)` returns non-empty string.

3. `test_render_planning_detect_requires_user_request()`
   - Calling `render(PLANNING_DETECT)` without `user_request` raises.

4. `test_render_planning_detect_renders_user_request()`
   - Render with `user_request="x"` contains `"Request: x"` (or another stable substring).

**Constraints:**
- Do not require network access.

### 4.2 Existing tests
- Leave `tests/test_live_openai_models.py` and `tests/test_llm_openai_compat.py` prompts inline (they are not product prompts).

---

## 5) Packaging / resource loading considerations

If using `importlib.resources`:
- Ensure `agent/prompts/templates/*.md` are included in the package.
- If this repo uses `pyproject.toml`, add package data configuration as needed.

If not packaging templates yet (running from source):
- A simple relative-path loader is acceptable, but document it.

---

## 6) Acceptance criteria

- No inline product prompt constants remain in:
  - `agent/agent_loop.py`
  - `agent/planning/models.py`
- Prompt text lives in:
  - `agent/prompts/templates/*.md`
- All call sites use the prompt registry/helpers.
- Unit tests cover prompt loading and required-variable validation.
- Docs no longer claim planning prompt is in `agent/agent_loop.py`.

---

## 7) Implementation order (recommended)

1. Add `agent/prompts/templates/*` with verbatim prompt text.
2. Add `agent/prompts/ids.py`, `agent/prompts/registry.py`, `agent/prompts/__init__.py`.
3. Update `agent/agent_loop.py` to use prompt helpers.
4. Update planning modules (`models.py`, `detector.py`, `planning/__init__.py`).
5. Add `tests/test_prompts.py`.
6. Update docs.
7. Run unit tests.
