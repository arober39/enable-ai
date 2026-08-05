"""Role-specific domain knowledge for the Enablement Agent.

Each role gets its own directory under `enablement_agents/roles/<role>/`:
  - role.yaml — metadata (id, display name, capability list, etc.)
  - domain_knowledge.md — what AI enablement looks like in this domain

The loader lives in `core/roles.py` so UI/API/runner layers depend on a
single import path. New roles are added by dropping a directory here +
populating the two files; the loader picks them up via filesystem scan.
"""
