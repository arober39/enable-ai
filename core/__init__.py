"""Cross-cutting abstractions: identity, state paths, credentials.

These three modules exist to keep Enable AI's single-user-local phase 1
upgradable to multi-user-hosted later without rewriting the call sites.
See ../BUILD_PLAN_PHASE1.md (or session memory) for the four locked
abstractions this package implements.
"""
