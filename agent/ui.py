from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from typing import Any


def _isatty() -> bool:
	try:
		return bool(sys.stdin.isatty() and sys.stdout.isatty())
	except Exception:
		return False


def supports_color() -> bool:
	if os.environ.get("NO_COLOR") is not None:
		return False
	if os.environ.get("TERM", "") == "dumb":
		return False
	return _isatty()


def clear_screen() -> None:
	# ANSI clear screen + move cursor to home.
	if _isatty():
		print("\033[2J\033[H", end="")


def _ansi(code: str) -> str:
	if not supports_color():
		return ""
	return code


def _bold(s: str) -> str:
	return f"{_ansi('\033[1m')}{s}{_ansi('\033[0m')}" if supports_color() else s


def _underline(s: str) -> str:
	return f"{_ansi('\033[4m')}{s}{_ansi('\033[0m')}" if supports_color() else s


@dataclass(frozen=True)
class Theme:
	id: str
	name: str
	border: str
	accent: str
	dim: str
	text: str
	success: str
	error: str
	reset: str = "\033[0m"

	def _wrap(self, s: str, code: str) -> str:
		if not supports_color():
			return s
		return f"{code}{s}{self.reset}"

	def b(self, s: str) -> str:
		return self._wrap(s, self.border)

	def a(self, s: str) -> str:
		return self._wrap(s, self.accent)

	def d(self, s: str) -> str:
		return self._wrap(s, self.dim)

	def t(self, s: str) -> str:
		return self._wrap(s, self.text)

	def ok(self, s: str) -> str:
		return self._wrap(s, self.success)

	def err(self, s: str) -> str:
		return self._wrap(s, self.error)


THEMES: list[Theme] = [
	Theme(
		id="dark",
		name="Dark mode",
		border="\033[38;5;208m",
		accent="\033[38;5;214m",
		dim="\033[38;5;245m",
		text="\033[38;5;252m",
		success="\033[38;5;42m",
		error="\033[38;5;196m",
	),
	Theme(
		id="light",
		name="Light mode",
		border="\033[38;5;25m",
		accent="\033[38;5;27m",
		dim="\033[38;5;242m",
		text="\033[38;5;236m",
		success="\033[38;5;28m",
		error="\033[38;5;160m",
	),
	Theme(
		id="dark_cb",
		name="Dark mode (colorblind-friendly)",
		border="\033[38;5;33m",
		accent="\033[38;5;33m",
		dim="\033[38;5;245m",
		text="\033[38;5;252m",
		success="\033[38;5;33m",
		error="\033[38;5;203m",
	),
	Theme(
		id="light_cb",
		name="Light mode (colorblind-friendly)",
		border="\033[38;5;24m",
		accent="\033[38;5;24m",
		dim="\033[38;5;244m",
		text="\033[38;5;235m",
		success="\033[38;5;24m",
		error="\033[38;5;160m",
	),
	Theme(
		id="dark_ansi",
		name="Dark mode (ANSI colors only)",
		border="\033[33m",
		accent="\033[33m",
		dim="\033[90m",
		text="\033[37m",
		success="\033[32m",
		error="\033[31m",
	),
	Theme(
		id="light_ansi",
		name="Light mode (ANSI colors only)",
		border="\033[34m",
		accent="\033[34m",
		dim="\033[90m",
		text="\033[30m",
		success="\033[32m",
		error="\033[31m",
	),
]


def get_theme(theme_id: str | None) -> Theme:
	if theme_id:
		for t in THEMES:
			if t.id == theme_id:
				return t
	return THEMES[0]


def _term_width(default: int = 80) -> int:
	try:
		return shutil.get_terminal_size((default, 24)).columns
	except Exception:
		return default


def _box(lines: list[str], *, theme: Theme, pad_x: int = 1) -> str:
	width = max((len(_strip_ansi(l)) for l in lines), default=0)
	inner_w = width + pad_x * 2
	top = theme.b("┌" + "─" * inner_w + "┐")
	bot = theme.b("└" + "─" * inner_w + "┘")
	out = [top]
	for l in lines:
		pad = " " * pad_x
		plain_len = len(_strip_ansi(l))
		out.append(theme.b("│") + pad + l + " " * (inner_w - plain_len - pad_x) + theme.b("│"))
	out.append(bot)
	return "\n".join(out)


def _strip_ansi(s: str) -> str:
	# Tiny ANSI stripper for width calculations.
	out = []
	i = 0
	while i < len(s):
		if s[i] == "\033" and i + 1 < len(s) and s[i + 1] == "[":
			i += 2
			while i < len(s) and s[i] != "m":
				i += 1
			i += 1
			continue
		out.append(s[i])
		i += 1
	return "".join(out)


def _render_inlines(s: str, theme: Theme) -> str:
	"""Very small inline markdown renderer.

	Handles:
	- `code`
	- **bold** and *italic* (stripped or styled)
	- [text](url)
	"""
	# Links: [text](url) -> text (url)
	out: list[str] = []
	i = 0
	while i < len(s):
		# Inline code `...`
		if s[i] == "`":
			j = s.find("`", i + 1)
			if j != -1:
				code = s[i + 1 : j]
				styled = theme.a(code) if supports_color() else f"`{code}`"
				out.append(styled)
				i = j + 1
				continue
		# Link [text](url)
		if s[i] == "[":
			j = s.find("]", i + 1)
			k = s.find("(", j + 1) if j != -1 else -1
			m = s.find(")", k + 1) if k != -1 else -1
			if j != -1 and k == j + 1 and m != -1:
				text = s[i + 1 : j]
				url = s[k + 1 : m]
				out.append(text)
				if url:
					out.append(" ")
					out.append(theme.d(f"({url})") if supports_color() else f"({url})")
				i = m + 1
				continue
		out.append(s[i])
		i += 1

	res = "".join(out)

	# Bold/italic: apply simple stripping first to avoid complex nesting.
	# **bold**
	while "**" in res:
		start = res.find("**")
		end = res.find("**", start + 2)
		if end == -1:
			break
		inner = res[start + 2 : end]
		repl = _bold(inner) if supports_color() else inner
		res = res[:start] + repl + res[end + 2 :]

	# *italic* (only when surrounded by non-space; best-effort)
	while "*" in res:
		start = res.find("*")
		end = res.find("*", start + 1)
		if end == -1:
			break
		inner = res[start + 1 : end]
		if not inner or inner.strip() != inner:
			# Likely list marker or whitespace emphasis; skip this '*'
			res = res[:start] + "\u0001" + res[start + 1 :]
			continue
		repl = _underline(inner) if supports_color() else inner
		res = res[:start] + repl + res[end + 1 :]

	# Restore skipped asterisks
	res = res.replace("\u0001", "*")
	return res


def render_markdown(text: str, theme: Theme) -> str:
	"""Render a subset of Markdown to a readable terminal format.

	This is intentionally lightweight (stdlib-only). It's designed for LLM responses:
	headings, lists, blockquotes, code fences, and basic inlines.
	"""
	lines = text.splitlines()
	out_lines: list[str] = []
	in_code = False
	code_lang = ""

	for raw in lines:
		line = raw.rstrip("\n")
		stripped = line.strip()

		# Fenced code blocks
		if stripped.startswith("```"):
			if not in_code:
				in_code = True
				code_lang = stripped[3:].strip()
				label = f"code" + (f" ({code_lang})" if code_lang else "")
				out_lines.append(theme.d(label) if supports_color() else label)
			else:
				in_code = False
				code_lang = ""
				out_lines.append("")
			continue

		if in_code:
			# Preserve code verbatim, with a small indent.
			out_lines.append(theme.d("  " + line) if supports_color() else "  " + line)
			continue

		# Headings: #, ##, ###...
		if stripped.startswith("#"):
			hash_count = len(stripped) - len(stripped.lstrip("#"))
			head = stripped[hash_count:].strip()
			head = _render_inlines(head, theme)
			head_line = theme.a(_bold(head) if supports_color() else head)
			out_lines.append(head_line)
			if not supports_color():
				out_lines.append("-" * max(len(head), 3))
			continue

		# Blockquote
		if stripped.startswith(">"):
			q = stripped[1:].lstrip()
			q = _render_inlines(q, theme)
			prefix = theme.d("│ ") if supports_color() else "| "
			out_lines.append(prefix + q)
			continue

		# Lists: -, *, 1.
		bullet = None
		content = None
		if stripped.startswith("- ") or stripped.startswith("* "):
			bullet = "•"
			content = stripped[2:]
		else:
			# ordered list: "1. "
			dot = stripped.find(". ")
			if dot != -1 and stripped[:dot].isdigit():
				bullet = stripped[:dot] + "."
				content = stripped[dot + 2 :]

		if bullet is not None and content is not None:
			content = _render_inlines(content, theme)
			b = theme.a(bullet) if supports_color() else bullet
			out_lines.append(f"{b} {content}")
			continue

		# Normal paragraph/text
		out_lines.append(_render_inlines(line, theme))

	return "\n".join(out_lines).rstrip() + ("\n" if text.endswith("\n") else "")


def render_theme_screen(*, theme: Theme, selected_index: int) -> str:
	header = _box([theme.a("* Welcome to Tiny Agent"), theme.d("Choose the text style that looks best with your terminal."), theme.d("To change this later, run /theme")], theme=theme)

	items: list[str] = []
	for i, t in enumerate(THEMES, start=1):
		prefix = "  "
		mark = " "
		if i - 1 == selected_index:
			prefix = theme.a("> ")
			mark = theme.ok("✓")
		items.append(f"{prefix}{i}. {t.name} {mark}".rstrip())

	preview = render_preview(theme)
	return "\n\n".join([header, "\n".join(items), preview, theme.d("Enter a number to change theme, or press Enter to continue")])


def render_preview(theme: Theme) -> str:
	# Keep this generic: a small diff preview inside a box.
	old = theme.err('-  console.log("Hello, World!");')
	new = theme.ok('+  console.log("Hello, Agent!");')
	lines = [
		theme.d("Preview"),
		"",
		theme.d("  1") + " function greet() {",
		"  2 " + old,
		"  2 " + new,
		"  3 }",
	]
	return _box(lines, theme=theme)


def load_ui_config(path: str) -> dict[str, Any]:
	try:
		with open(path, "r", encoding="utf-8") as f:
			data = json.load(f)
		if isinstance(data, dict):
			return data
	except FileNotFoundError:
		return {}
	except Exception:
		return {}
	return {}


def save_ui_config(path: str, data: dict[str, Any]) -> None:
	os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
	with open(path, "w", encoding="utf-8") as f:
		json.dump(data, f, indent=2, sort_keys=True)
		f.write("\n")


def run_onboarding(*, ui_config_path: str) -> Theme:
	cfg = load_ui_config(ui_config_path)
	theme = get_theme(cfg.get("theme"))
	selected = next((i for i, t in enumerate(THEMES) if t.id == theme.id), 0)

	# Skip onboarding in non-interactive contexts.
	if os.environ.get("AGENT_NO_ONBOARDING") is not None or not _isatty():
		return theme

	if cfg.get("onboarded") is True:
		return theme

	while True:
		clear_screen()
		theme = THEMES[selected]
		print(render_theme_screen(theme=theme, selected_index=selected))
		try:
			raw = input(theme.a("> ") if supports_color() else "> ").strip()
		except (EOFError, KeyboardInterrupt):
			raw = ""

		if raw == "":
			break
		if raw.isdigit():
			n = int(raw)
			if 1 <= n <= len(THEMES):
				selected = n - 1
				continue
		# Invalid input: re-render (no extra UI clutter)

	cfg["theme"] = THEMES[selected].id
	cfg["onboarded"] = True
	save_ui_config(ui_config_path, cfg)
	clear_screen()
	print(THEMES[selected].ok("Login successful.") + " " + THEMES[selected].d("Press Enter to continue"))
	try:
		input("")
	except (EOFError, KeyboardInterrupt):
		pass
	clear_screen()
	return THEMES[selected]
