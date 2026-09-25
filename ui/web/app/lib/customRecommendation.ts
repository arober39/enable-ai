/** Session-stable id for the recommendation the user writes on step 5. */
export const CUSTOM_RECOMMENDATION_ID = "R-CUSTOM";

/** Sent to the handoff. This is not one of the plan's recommendation kinds. */
export const CUSTOM_RECOMMENDATION_KIND = "custom";

export interface CustomRecommendationDraft {
  title: string;
  body: string;
}

/** Fields Step 6 needs. A plan recommendation and a custom one both match. */
export interface HandoffRecommendation {
  id: string;
  kind: string;
  description: string;
  notes: string | null;
  tools_affected: string[];
}

export function isCustomRecommendationId(id: string | null | undefined): boolean {
  return id === CUSTOM_RECOMMENDATION_ID;
}

/**
 * The recommendation Submit hands to Grok Bot.
 * An optional title is placed above the body so the pasted assignment includes it.
 * Returns null when the body is blank.
 */
export function buildCustomRecommendation(
  draft: CustomRecommendationDraft,
  tools: string[],
): HandoffRecommendation | null {
  const body = draft.body.trim();
  if (!body) return null;
  const title = draft.title.trim();
  return {
    id: CUSTOM_RECOMMENDATION_ID,
    kind: CUSTOM_RECOMMENDATION_KIND,
    description: title ? `${title}\n\n${body}` : body,
    notes: null,
    tools_affected: [...tools],
  };
}

export function sameHandoffRecommendation(
  left: HandoffRecommendation | null,
  right: HandoffRecommendation | null,
): boolean {
  if (left == null || right == null) return left === right;
  return (
    left.id === right.id &&
    left.kind === right.kind &&
    left.description === right.description &&
    left.notes === right.notes &&
    left.tools_affected.join("\n") === right.tools_affected.join("\n")
  );
}
