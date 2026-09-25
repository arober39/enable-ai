/**
 * Which picker rows to show.
 *
 * Unfiltered lists keep a short preview so the search box stays the way in.
 * Selected rows are pinned so a researched role or tool cannot vanish behind
 * that preview, and a selection stays visible while the query is cleared.
 */

export function visiblePickerItems<T>(options: {
  items: T[];
  query: string;
  matches: (item: T, query: string) => boolean;
  isSelected: (item: T) => boolean;
  previewCount: number;
  pinSelected: boolean;
}): T[] {
  const query = options.query.trim().toLowerCase();
  const matching = query
    ? options.items.filter((item) => options.matches(item, query))
    : options.items;
  if (!options.pinSelected) {
    return query ? matching : matching.slice(0, options.previewCount);
  }
  const selected = options.items.filter(options.isSelected);
  const selectedSet = new Set(selected);
  if (!query) {
    const rest = matching.filter((item) => !selectedSet.has(item));
    return [...selected, ...rest.slice(0, options.previewCount)];
  }
  const matchingSet = new Set(matching);
  const hiddenSelected = selected.filter((item) => !matchingSet.has(item));
  return [...hiddenSelected, ...matching];
}
