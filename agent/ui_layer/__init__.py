"""UI layer module for terminal rendering and theme management."""

from .theme import (
	Theme,
	THEMES,
	supports_color,
	clear_screen,
	get_theme,
	render_app_banner,
	render_system_info,
	render_plan_banner,
	render_markdown,
	render_theme_screen,
	render_preview,
	load_ui_config,
	save_ui_config,
	run_onboarding,
)

__all__ = [
	"Theme",
	"THEMES",
	"supports_color",
	"clear_screen",
	"get_theme",
	"render_app_banner",
	"render_system_info",
	"render_plan_banner",
	"render_markdown",
	"render_theme_screen",
	"render_preview",
	"load_ui_config",
	"save_ui_config",
	"run_onboarding",
]
