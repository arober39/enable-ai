import type {
  CapabilityFinding,
  EnablementPlan,
  Recommendation,
} from "./types";

function findingLine(finding: CapabilityFinding): string {
  const tools =
    finding.tools_involved.length > 0
      ? ` Tools involved: ${finding.tools_involved.join(", ")}.`
      : "";
  const notes = finding.notes ? ` ${finding.notes}` : "";
  return `${finding.capability}. Status: ${finding.status}.${tools}${notes}`;
}

function recommendationLine(rec: Recommendation): string {
  const kind = rec.kind.replaceAll("_", " ");
  const tools =
    rec.tools_affected.length > 0
      ? ` Tools affected: ${rec.tools_affected.join(", ")}.`
      : "";
  const notes = rec.notes ? ` ${rec.notes}` : "";
  return `${rec.description} Kind: ${kind}. Effort: ${rec.effort}.${tools}${notes}`;
}

export function findingsSpeech(plan: EnablementPlan): string {
  if (plan.capability_coverage.length === 0) return "No capability findings.";
  return ["Capability findings.", ...plan.capability_coverage.map(findingLine)].join(
    " ",
  );
}

export function recommendationsSpeech(plan: EnablementPlan): string {
  if (plan.recommendations.length === 0) return "No recommendations.";
  const lines = plan.recommendations.map(
    (rec, index) => `Recommendation ${index + 1}. ${recommendationLine(rec)}`,
  );
  return ["Recommendations.", ...lines].join(" ");
}

export function planSpeech(plan: EnablementPlan): string {
  return [
    `Plan summary. ${plan.summary}`,
    findingsSpeech(plan),
    recommendationsSpeech(plan),
  ].join(" ");
}
