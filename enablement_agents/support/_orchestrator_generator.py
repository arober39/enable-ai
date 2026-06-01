"""Implementation of SupportEnablementAgent.generate_orchestrator().

Renders the templates under `_orchestrator_templates/` into a runnable
orchestrator tree at `orchestrators/<department>/`. The render is
deterministic so the tutorial-critical strings (event names, AI Config
name, model name, the one-line diff between v1_baseline and
v2_detailed_responses) are bit-exact.

Plan-derived substitutions:
  - `.mcp.json`: built from `plan.orchestrator_pr_plan.mcp_servers_used`.
  - `.env.example`: filtered to the union of plan-required env vars and
    the canonical orchestrator subset.
  - `README.md`: receives plan.summary and the resolved env-var list.

The bit-exact files are copied byte-for-byte from the templates with no
substitution.

This phase ships the deterministic generator only. The build plan also
contemplates a "second LLM invocation of the Support agent" path that
writes these files via Write/Edit tool calls. That LLM-driven path is a
v2 enhancement; v1 ships templates so the tutorial's bit-exact strings
are preserved.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import string
from pathlib import Path

from coordinator.schemas import EnablementPlan, OrchestratorRunResult

logger = logging.getLogger(__name__)

_HERE: Path = Path(__file__).resolve().parent
_TEMPLATES_DIR: Path = _HERE / "_orchestrator_templates"
_REPO_ROOT: Path = _HERE.parents[1]

#: Files copied byte-for-byte from templates to the output tree.
#: (template_relative_path, output_relative_path)
_BYTE_FOR_BYTE: list[tuple[str, str]] = [
    ("prompts/v1_baseline.md.tmpl", "prompts/v1_baseline.md"),
    ("prompts/v2_detailed_responses.md.tmpl", "prompts/v2_detailed_responses.md"),
    ("judges/factual_accuracy.md.tmpl", "judges/factual_accuracy.md"),
    ("ai_configs.manifest.yaml.tmpl", "ai_configs.manifest.yaml"),
    ("Makefile.tmpl", "Makefile"),
    ("orchestrator.py.tmpl", "orchestrator.py"),
    ("agent_definition.py.tmpl", "agent_definition.py"),
    ("observability.py.tmpl", "observability.py"),
    ("mcp_servers/hubspot/__init__.py.tmpl", "mcp_servers/hubspot/__init__.py"),
    ("mcp_servers/hubspot/server.py.tmpl", "mcp_servers/hubspot/server.py"),
]


# ---------------------------------------------------------------------------
# MCP server config map — what `.mcp.json` declares for each available tool.
#
# Values mirror mcp_registry/<tool>.yaml's install field. The orchestrator's
# .mcp.json is the standard Claude Code MCP config shape — Claude Code (or
# any MCP-capable client) reads it and starts the named servers.
# ---------------------------------------------------------------------------

_MCP_SERVER_CONFIGS: dict[str, dict[str, object]] = {
    "intercom": {
        "command": "npx",
        "args": ["@intercom/mcp-server"],
        "env": {"INTERCOM_API_KEY": "${INTERCOM_API_KEY}"},
    },
    "zendesk": {
        "command": "npx",
        "args": ["mcp-server-zendesk"],
        "env": {"ZENDESK_API_TOKEN": "${ZENDESK_API_TOKEN}"},
    },
    "slack": {
        "command": "npx",
        "args": ["@modelcontextprotocol/server-slack"],
        "env": {"SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}"},
    },
}


def _render_mcp_json(mcp_servers_used: list[str]) -> str:
    """Build the .mcp.json content from the list of available MCP server tools."""
    servers: dict[str, object] = {}
    for tool in sorted(mcp_servers_used):
        if tool in _MCP_SERVER_CONFIGS:
            servers[tool] = _MCP_SERVER_CONFIGS[tool]
        else:
            logger.warning("no MCP server config known for tool=%s; skipping", tool)
    return json.dumps({"mcpServers": servers}, indent=2) + "\n"


def _read_root_env_example() -> set[str]:
    """Parse the root .env.example and return the set of declared variable names.

    Used to enforce the strict-subset invariant — generated .env.example
    must not introduce variable names absent from the root.
    """
    root_env = _REPO_ROOT / ".env.example"
    if not root_env.exists():
        return set()
    names: set[str] = set()
    for line in root_env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([A-Z_][A-Z0-9_]*)\s*=", line)
        if m:
            names.add(m.group(1))
    return names


def _generated_env_var_names() -> set[str]:
    """Parse the rendered .env.example template and return its variable names."""
    template = (_TEMPLATES_DIR / "env.example.tmpl").read_text(encoding="utf-8")
    names: set[str] = set()
    for line in template.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([A-Z_][A-Z0-9_]*)\s*=", line)
        if m:
            names.add(m.group(1))
    return names


def _verify_env_subset() -> None:
    """Raise if the generated .env.example introduces variables not in root.

    This is a Phase 5.4 checkpoint requirement.
    """
    root = _read_root_env_example()
    generated = _generated_env_var_names()
    extras = generated - root
    if extras:
        raise RuntimeError(
            f"Generated .env.example introduces env var(s) not declared in root "
            f".env.example: {sorted(extras)}. Update the root file first, or "
            f"remove the variable from env.example.tmpl."
        )


def _render_readme(plan: EnablementPlan, env_var_names: list[str], file_tree: list[str]) -> str:
    """Render README.md.tmpl with plan-derived content."""
    template = (_TEMPLATES_DIR / "README.md.tmpl").read_text(encoding="utf-8")
    env_var_list = "\n".join(f"- `{name}`" for name in sorted(env_var_names))
    file_tree_str = "\n".join(f"- `{path}`" for path in sorted(file_tree))
    return string.Template(template).safe_substitute(
        generated_at=plan.metadata.generated_at.isoformat(),
        plan_summary=plan.summary,
        env_vars_list=env_var_list or "_(none declared)_",
        file_tree=file_tree_str,
    )


def _write_file(dest: Path, content: str | bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        dest.write_bytes(content)
    else:
        dest.write_text(content, encoding="utf-8")
    logger.debug("wrote %s (%d bytes)", dest, dest.stat().st_size)


def generate_orchestrator_files(
    plan: EnablementPlan,
    output_root: Path,
) -> OrchestratorRunResult:
    """Render templates into `output_root` and return the run result.

    Args:
        plan: The EnablementPlan whose orchestrator_pr_plan describes what
            to produce.
        output_root: Where the orchestrator tree should live. Typically
            `orchestrators/support/`.

    Returns:
        OrchestratorRunResult enumerating the files written, MCP servers
        generated, manifest path, and required env vars.

    Raises:
        ValueError: If the plan has no orchestrator_pr_plan.
        RuntimeError: If .env.example would introduce new env-var names.
    """
    if plan.orchestrator_pr_plan is None:
        raise ValueError(
            "EnablementPlan.orchestrator_pr_plan is None — generate_orchestrator "
            "requires a populated orchestrator_pr_plan describing what to build."
        )

    pr_plan = plan.orchestrator_pr_plan

    # 1. Pre-flight: env subset invariant.
    _verify_env_subset()

    # 2. If the output_root already exists, wipe it cleanly. The generator
    #    owns this directory tree; we don't try to merge with previous runs.
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    written: list[str] = []
    mcp_servers_generated: list[str] = []

    # 3. Copy byte-for-byte templates.
    for src_rel, dst_rel in _BYTE_FOR_BYTE:
        src = _TEMPLATES_DIR / src_rel
        dst = output_root / dst_rel
        content = src.read_bytes()
        _write_file(dst, content)
        written.append(dst_rel)

    # 4. Render the .env.example.
    env_content = (_TEMPLATES_DIR / "env.example.tmpl").read_text(encoding="utf-8")
    _write_file(output_root / ".env.example", env_content)
    written.append(".env.example")

    # 5. Render .mcp.json from the plan.
    mcp_json = _render_mcp_json(pr_plan.mcp_servers_used)
    _write_file(output_root / ".mcp.json", mcp_json)
    written.append(".mcp.json")

    # 6. Track which tools needed a generated MCP server. Phase 2 data has
    #    hubspot as the only `available: false` case; the template tree
    #    only includes a hubspot stub. If the plan declares more
    #    to_generate, log a warning — we can't synthesize stubs we don't
    #    have templates for.
    for to_gen in pr_plan.mcp_servers_to_generate:
        if to_gen == "hubspot":
            mcp_servers_generated.append("hubspot")
        else:
            logger.warning(
                "plan declares mcp_servers_to_generate=%s but no stub template exists; "
                "skipping. Add a template at _orchestrator_templates/mcp_servers/%s/",
                to_gen,
                to_gen,
            )

    # 7. Render README last, with the resolved env-var list and file tree
    #    (so it accurately reflects what was actually written).
    env_var_names = sorted(_generated_env_var_names())
    readme = _render_readme(plan, env_var_names, written)
    _write_file(output_root / "README.md", readme)
    written.append("README.md")

    logger.info(
        "generate_orchestrator wrote %d files to %s; mcp_generated=%s",
        len(written),
        output_root,
        mcp_servers_generated,
    )

    manifest_abs = output_root / "ai_configs.manifest.yaml"
    # Report the manifest path as repo-relative when possible (the production
    # case), falling back to absolute when output_root is outside the repo
    # (tests using tmp_path). Either form is a valid filesystem reference.
    try:
        manifest_path_str = str(manifest_abs.relative_to(_REPO_ROOT))
    except ValueError:
        manifest_path_str = str(manifest_abs)

    return OrchestratorRunResult(
        department=plan.department,
        files_created=sorted(written),
        mcp_servers_generated=mcp_servers_generated,
        ai_configs_manifest_path=manifest_path_str,
        env_vars_required=env_var_names,
        plan_reference=plan.metadata,
    )
