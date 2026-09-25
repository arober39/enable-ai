"""ToolCapability accepts stringified LLM lists without weakening the schema."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from core.identity import local_user
from core.tool_catalog import ToolCapability, load_tool

_FEATURES = [
    {
        "name": "Insights",
        "description": "Natural-language analysis of product usage.",
        "maturity": "ga",
        "coverage": "high",
    },
    {
        "name": "Spark AI",
        "description": "Report and cohort summaries inside Mixpanel.",
        "maturity": "beta",
        "coverage": "medium",
    },
]


def _base(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "canonical_name": "mixpanel",
        "vendor": "Mixpanel",
        "categories": ["product_analytics"],
        "native_ai_features": [],
        "api_surface": {
            "has_rest_api": True,
            "has_webhooks": True,
            "rate_limits": "standard",
        },
        "integration_patterns": ["augment_with_custom_ai"],
        "notes": "Product analytics with a few in-product assistants.",
        "mcp_server": {"available": False, "tools_exposed": []},
        "fallback_if_unavailable": "direct_api",
        "source": "researched",
    }
    payload.update(overrides)
    return payload


def test_stringified_native_ai_features_validate() -> None:
    capability = ToolCapability.model_validate(
        _base(native_ai_features=json.dumps(_FEATURES))
    )

    assert isinstance(capability, ToolCapability)
    assert [feature.name for feature in capability.native_ai_features] == [
        "Insights",
        "Spark AI",
    ]
    assert capability.native_ai_features[0].maturity == "ga"
    assert capability.native_ai_features[0].coverage == "high"
    assert capability.native_ai_features[1].description.startswith("Report and cohort")


def test_messy_native_ai_features_string_ignores_trailing_markup() -> None:
    # Mirrors the Mixpanel research failure: a JSON list left as a string,
    # with HTML/XML debris after the array (the UI showed this tail as
    # unavailable">direct_api).
    messy = (
        '[\n {\n "name": "Insights",\n "description": '
        '"Natural-language analysis of product usage.",\n '
        '"maturity": "ga",\n "coverage": "high"\n }\n]'
        '</parameter name="fallback_if_unavailable">direct_api'
    )
    capability = ToolCapability.model_validate(_base(native_ai_features=messy))

    assert len(capability.native_ai_features) == 1
    feature = capability.native_ai_features[0]
    assert feature.name == "Insights"
    assert feature.maturity == "ga"
    assert feature.coverage == "high"
    assert capability.fallback_if_unavailable == "direct_api"


def test_partial_stringified_feature_defaults_unknown_maturity() -> None:
    raw = json.dumps(
        [{"name": "Insights", "description": "Natural-language analysis."}]
    )
    capability = ToolCapability.model_validate(_base(native_ai_features=raw))

    feature = capability.native_ai_features[0]
    assert feature.name == "Insights"
    assert feature.description == "Natural-language analysis."
    assert feature.maturity == "unknown"
    assert feature.coverage == "unknown"


def test_garbage_native_ai_features_does_not_fail_validation() -> None:
    capability = ToolCapability.model_validate(
        _base(native_ai_features='<div>not a feature list</div> unavailable">direct_api')
    )

    assert capability.native_ai_features == []
    assert capability.vendor == "Mixpanel"


def test_string_items_inside_feature_list_are_parsed() -> None:
    capability = ToolCapability.model_validate(
        _base(native_ai_features=[json.dumps(_FEATURES[0]), _FEATURES[1]])
    )

    assert [feature.name for feature in capability.native_ai_features] == [
        "Insights",
        "Spark AI",
    ]


def test_sibling_list_and_object_fields_accept_json_strings() -> None:
    capability = ToolCapability.model_validate(
        _base(
            categories='["product_analytics", "experimentation"]',
            integration_patterns="use_native_ai, augment_with_custom_ai",
            api_surface=json.dumps(
                {
                    "has_rest_api": True,
                    "has_webhooks": False,
                    "rate_limits": "generous",
                }
            ),
            mcp_server={
                "available": True,
                "origin": "community",
                "tools_exposed": '["query", "export"]</tool>',
            },
        )
    )

    assert capability.categories == ["product_analytics", "experimentation"]
    assert capability.integration_patterns == [
        "use_native_ai",
        "augment_with_custom_ai",
    ]
    assert capability.api_surface.has_webhooks is False
    assert capability.api_surface.rate_limits == "generous"
    assert capability.mcp_server.tools_exposed == ["query", "export"]


def test_structured_feature_list_still_requires_fields() -> None:
    with pytest.raises(ValidationError):
        ToolCapability.model_validate(
            _base(native_ai_features=[{"name": "Insights"}])
        )


def test_schema_keeps_native_ai_features_as_an_array() -> None:
    schema = ToolCapability.model_json_schema()
    for key in ("native_ai_features", "categories", "integration_patterns"):
        assert schema["properties"][key]["type"] == "array"
    tools_exposed = schema["$defs"]["MCPServerInfo"]["properties"]["tools_exposed"]
    assert tools_exposed["type"] == "array"


def test_seed_catalog_lists_are_unchanged() -> None:
    capability = load_tool(local_user(), "slack")
    assert capability is not None
    assert [feature.name for feature in capability.native_ai_features] == [
        "Slack AI",
        "Slack Workflow Builder",
    ]
    assert capability.native_ai_features[0].description == (
        "Channel summaries, thread recaps, and search answers grounded in "
        "the user's Slack workspace."
    )
    assert capability.categories == [
        "internal_messaging",
        "internal_handoff",
        "team_collaboration",
    ]
