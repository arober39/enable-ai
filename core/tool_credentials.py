"""Credential keys a tool needs before its adapter leaves stub mode."""

from __future__ import annotations

REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "intercom": ("INTERCOM_API_TOKEN",),
    "zendesk": ("ZENDESK_SUBDOMAIN", "ZENDESK_EMAIL", "ZENDESK_API_TOKEN"),
    "slack": ("SLACK_BOT_TOKEN",),
    "hubspot": ("HUBSPOT_API_KEY",),
    "gainsight": ("GAINSIGHT_API_KEY",),
    "gong": ("GONG_API_KEY",),
    "vitally": ("VITALLY_API_KEY",),
    "github": ("GITHUB_TOKEN",),
    "klaviyo": ("KLAVIYO_API_KEY",),
    "marketo": ("MARKETO_API_KEY",),
    "discord": ("DISCORD_BOT_TOKEN",),
    "discourse": ("DISCOURSE_API_KEY",),
}


def keys_for_tools(tool_names: list[str]) -> list[tuple[str, str]]:
    """Return (tool, credential key) pairs for tools that have a vault key."""
    pairs: list[tuple[str, str]] = []
    for name in tool_names:
        for key in REQUIRED_KEYS.get(name, ()):
            pairs.append((name, key))
    return pairs


def keys_for_workflow(
    step_tools: list[str],
    declared: list[str],
) -> list[tuple[str, str]]:
    """Credential keys a built workflow needs, including model steps.

    A step that calls `llm` needs ANTHROPIC_API_KEY even when the
    generator left `env_vars_required` empty. Declared names are kept
    so a workflow can ask for a key that is not in the tool catalog.
    """
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(source: str, key: str) -> None:
        if key in seen:
            return
        seen.add(key)
        pairs.append((source, key))

    for name in step_tools:
        if name == "llm":
            add("llm", "ANTHROPIC_API_KEY")
        for key in REQUIRED_KEYS.get(name, ()):
            add(name, key)
    for key in declared:
        add("workflow", key)
    return pairs


def missing_keys(tool_names: list[str], present: set[str]) -> list[str]:
    """Credential names still absent from the vault, in tool order."""
    missing: list[str] = []
    for _tool, key in keys_for_tools(tool_names):
        if key not in present and key not in missing:
            missing.append(key)
    return missing
