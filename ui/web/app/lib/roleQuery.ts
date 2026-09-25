/** Shared with the role picker. A typed fragment of an existing title is not a new role. */

const _MIN_PREFIX = 2;

export function normalizeRoleQuery(value: string): string {
  return value.trim().toLowerCase().split(/\s+/).filter(Boolean).join(" ");
}

export function rolesPrefixedBy<T extends { display_name: string }>(
  query: string,
  roles: T[],
): T[] {
  const q = normalizeRoleQuery(query);
  if (q.length < _MIN_PREFIX) return [];
  return roles.filter((role) => {
    const display = normalizeRoleQuery(role.display_name);
    return display.startsWith(q) && display !== q;
  });
}
