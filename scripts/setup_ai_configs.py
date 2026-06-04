"""Provision the LaunchDarkly AI Config for the support orchestrator.

Reads `orchestrators/support/ai_configs.manifest.yaml` (generated in Phase 5)
and creates/updates the `support-orchestrator-config` AI Config on the
configured LD project. Two variations: `v1-baseline` (the default) and
`v2-detailed-responses`. Both use claude-sonnet-4-6 in completion mode.

Initial traffic: 100% v1-baseline, 0% v2-detailed-responses. The
multi-signal guardrails tutorial then walks the user through ramping v2
behind a guarded rollout.

Idempotent: if the AI Config already exists, the script attempts to update
its variations rather than failing.

Demo mode (`ENABLE_AI_DEMO_MODE=true`, default) and `--dry-run` both
suppress real API calls.

Alternative: the same provisioning can be performed by hand via the
LaunchDarkly AI Configs MCP server in an AI client. See README.

Reads:
  - LAUNCHDARKLY_API_KEY        (required for real-mode)
  - LAUNCHDARKLY_PROJECT_KEY    (required)
  - ENABLE_AI_DEMO_MODE         (optional; default true)

Exit codes:
  0  success (or demo-mode dry run)
  1  validation / config-file error
  2  upstream LD API error
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

logger = logging.getLogger("setup_ai_configs")

_REPO_ROOT: Path = Path(__file__).resolve().parent.parent
_DEFAULT_MANIFEST_PATH: Path = (
    _REPO_ROOT / "orchestrators" / "support" / "ai_configs.manifest.yaml"
)
_DEFAULT_PROMPTS_DIR: Path = _REPO_ROOT / "orchestrators" / "support"
_LD_API_BASE = "https://app.launchdarkly.com/api/v2"


@dataclass
class VariationSpec:
    name: str
    is_default: bool
    model: str
    max_tokens: int
    temperature: float
    messages_file: str  # relative to the orchestrator dir


@dataclass
class AIConfigSpec:
    name: str
    mode: str
    description: str
    variations: list[VariationSpec]
    initial_traffic: dict[str, int]


def _demo_mode() -> bool:
    return os.environ.get("ENABLE_AI_DEMO_MODE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _load_manifest(path: Path) -> AIConfigSpec:
    """Parse ai_configs.manifest.yaml into typed specs."""
    if not path.exists():
        raise FileNotFoundError(
            f"AI Config manifest not found at {path}. Run "
            "`make install` and Phase 5's generate_orchestrator() first."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "ai_config" not in raw:
        raise ValueError(
            f"Manifest at {path} is missing top-level 'ai_config' key."
        )
    cfg = raw["ai_config"]
    variations = [
        VariationSpec(
            name=v["name"],
            is_default=bool(v.get("is_default", False)),
            model=v["model"],
            max_tokens=int(v.get("max_tokens", 1024)),
            temperature=float(v.get("temperature", 0.3)),
            messages_file=v["messages_file"],
        )
        for v in cfg.get("variations", [])
    ]
    initial = cfg.get("initial_traffic", {})
    return AIConfigSpec(
        name=cfg["name"],
        mode=cfg.get("mode", "completion"),
        description=cfg.get("description", ""),
        variations=variations,
        initial_traffic={k: int(v) for k, v in initial.items()},
    )


def _load_prompt(rel_path: str, prompts_dir: Path) -> str:
    """Read a variation's prompt body from disk."""
    full = prompts_dir / rel_path
    if not full.exists():
        raise FileNotFoundError(
            f"Prompt file {full} referenced from the manifest does not exist."
        )
    return full.read_text(encoding="utf-8")


def _api_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": api_key,
        "Content-Type": "application/json",
        "LD-API-Version": "beta",
    }


def _variation_payload(
    variation: VariationSpec, prompt_body: str
) -> dict[str, Any]:
    """Build the variation payload accepted by the LD AI Configs API."""
    return {
        "key": variation.name,
        "name": variation.name,
        "model": {
            "name": variation.model,
            "parameters": {
                "max_tokens": variation.max_tokens,
                "temperature": variation.temperature,
            },
        },
        "messages": [{"role": "system", "content": prompt_body}],
    }


def _ai_config_payload(
    spec: AIConfigSpec, prompts_dir: Path
) -> dict[str, Any]:
    """Build the create/update payload for the AI Config itself."""
    return {
        "key": spec.name,
        "name": spec.name,
        "description": spec.description,
        "mode": spec.mode,
        "variations": [
            _variation_payload(v, _load_prompt(v.messages_file, prompts_dir))
            for v in spec.variations
        ],
        "defaultVariationKey": next(
            (v.name for v in spec.variations if v.is_default),
            spec.variations[0].name if spec.variations else None,
        ),
    }


def _ai_config_exists(
    client: httpx.Client, project_key: str, config_key: str, api_key: str
) -> bool:
    resp = client.get(
        f"{_LD_API_BASE}/projects/{project_key}/ai-configs/{config_key}",
        headers=_api_headers(api_key),
    )
    if resp.status_code == 404:
        return False
    if resp.status_code == 200:
        return True
    raise RuntimeError(
        f"Unexpected status {resp.status_code} checking AI Config "
        f"'{config_key}': {resp.text[:300]}"
    )


def _provision(
    client: httpx.Client,
    project_key: str,
    spec: AIConfigSpec,
    prompts_dir: Path,
    api_key: str,
) -> str:
    """Create or update the AI Config. Returns 'created' or 'updated'."""
    payload = _ai_config_payload(spec, prompts_dir)
    if _ai_config_exists(client, project_key, spec.name, api_key):
        resp = client.put(
            f"{_LD_API_BASE}/projects/{project_key}/ai-configs/{spec.name}",
            headers=_api_headers(api_key),
            json=payload,
        )
        if resp.status_code not in (200, 204):
            raise RuntimeError(
                f"Failed to update AI Config '{spec.name}': "
                f"status={resp.status_code} body={resp.text[:500]}"
            )
        return "updated"

    resp = client.post(
        f"{_LD_API_BASE}/projects/{project_key}/ai-configs",
        headers=_api_headers(api_key),
        json=payload,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Failed to create AI Config '{spec.name}': "
            f"status={resp.status_code} body={resp.text[:500]}"
        )
    return "created"


def _print_would_do(
    spec: AIConfigSpec, prompts_dir: Path, project_key: str
) -> None:
    payload = _ai_config_payload(spec, prompts_dir)
    # Truncate the embedded prompt bodies for readability.
    for v in payload["variations"]:
        for msg in v.get("messages", []):
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 200:
                msg["content"] = content[:200] + "...(truncated)"
    logger.info(
        "WOULD provision AI Config on project=%s:\n%s",
        project_key,
        json.dumps(payload, indent=2),
    )
    logger.info(
        "WOULD set initial traffic: %s",
        json.dumps(spec.initial_traffic, indent=2),
    )


def run(*, dry_run: bool, manifest_path: Path, prompts_dir: Path) -> int:
    project_key = os.environ.get("LAUNCHDARKLY_PROJECT_KEY", "").strip()
    if not project_key:
        logger.error(
            "LAUNCHDARKLY_PROJECT_KEY is not set. Add it to your .env "
            "(see root .env.example) and re-run."
        )
        return 1

    try:
        spec = _load_manifest(manifest_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Manifest error: %s", exc)
        return 1

    if _demo_mode() or dry_run:
        logger.info(
            "Demo mode active (ENABLE_AI_DEMO_MODE=%s, --dry-run=%s). "
            "No real API calls will be made.",
            os.environ.get("ENABLE_AI_DEMO_MODE", "true"),
            dry_run,
        )
        try:
            _print_would_do(spec, prompts_dir, project_key)
        except FileNotFoundError as exc:
            logger.error("Prompt file error: %s", exc)
            return 1
        logger.info("Dry-run complete.")
        return 0

    api_key = os.environ.get("LAUNCHDARKLY_API_KEY", "").strip()
    if not api_key:
        logger.error(
            "LAUNCHDARKLY_API_KEY is not set. Add it to your .env (see root "
            ".env.example) and re-run, or set ENABLE_AI_DEMO_MODE=true to "
            "preview without provisioning."
        )
        return 1

    try:
        with httpx.Client(timeout=20.0) as client:
            verb = _provision(client, project_key, spec, prompts_dir, api_key)
        logger.info(
            "AI Config '%s' %s on project=%s.", spec.name, verb, project_key
        )
        logger.info(
            "Reminder: initial traffic split is configured separately via "
            "the targeting tab in the LD UI: %s",
            json.dumps(spec.initial_traffic),
        )
    except RuntimeError as exc:
        logger.error("LD API error: %s", exc)
        return 2
    except FileNotFoundError as exc:
        logger.error("Prompt file error: %s", exc)
        return 1
    except httpx.HTTPError as exc:
        logger.error("HTTP error talking to LaunchDarkly: %s", exc)
        return 2

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be provisioned without calling the LD API.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_DEFAULT_MANIFEST_PATH,
        help=f"Path to ai_configs.manifest.yaml (default: {_DEFAULT_MANIFEST_PATH}).",
    )
    parser.add_argument(
        "--prompts-dir",
        type=Path,
        default=_DEFAULT_PROMPTS_DIR,
        help=(
            f"Base directory for variation prompt files (default: "
            f"{_DEFAULT_PROMPTS_DIR}). The manifest's `messages_file` paths "
            f"are resolved relative to this directory."
        ),
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    sys.exit(run(dry_run=args.dry_run, manifest_path=args.manifest, prompts_dir=args.prompts_dir))


if __name__ == "__main__":
    main()
