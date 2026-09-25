import assert from "node:assert/strict";
import { test } from "node:test";

import { rolesPrefixedBy } from "./roleQuery.ts";

const roles = [
  { id: "devrel", display_name: "Developer Relations" },
  { id: "support", display_name: "Customer Support" },
  { id: "customer_success", display_name: "Customer Success" },
];

test("a prefix of Developer Relations is not a new role", () => {
  const matches = rolesPrefixedBy("deve", roles);
  assert.deepEqual(
    matches.map((role) => role.id),
    ["devrel"],
  );
});

test("the full title is not treated as a prefix", () => {
  assert.deepEqual(rolesPrefixedBy("Developer Relations", roles), []);
});

test("a distinct title can still be researched", () => {
  assert.deepEqual(rolesPrefixedBy("developer advocate", roles), []);
});

test("one fragment can match more than one title", () => {
  const matches = rolesPrefixedBy("customer", roles);
  assert.deepEqual(
    matches.map((role) => role.id),
    ["support", "customer_success"],
  );
});
