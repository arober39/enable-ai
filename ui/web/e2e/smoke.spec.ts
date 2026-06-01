import { expect, test } from "@playwright/test";

/**
 * Smoke test for the Enable AI test UI.
 *
 * One happy-path test that walks the user flow end-to-end in demo mode:
 *
 *   1. Loads the home page
 *   2. Confirms the catalog renders (4 tools)
 *   3. Confirms backend health reports demo_mode=true (no LLM cost)
 *   4. Confirms the default two-tool pre-selection
 *   5. Clicks "Run (demo)"
 *   6. Verifies the synthetic EnablementPlan renders with all sections
 *
 * Plus two narrower tests for the form's interactive states.
 */

test.describe("Enable AI test UI", () => {
  test("happy path: load → run → see plan", async ({ page }) => {
    await page.goto("/");

    // Page header
    await expect(
      page.getByRole("heading", { name: /Enable AI/i })
    ).toBeVisible();

    // Catalog renders (4 tools)
    await expect(page.getByText(/4 of 4 selected|of 4 selected/)).toBeVisible();
    for (const tool of ["intercom", "zendesk", "slack", "hubspot"]) {
      await expect(page.getByRole("button", { name: new RegExp(tool, "i") }))
        .toBeVisible();
    }

    // Health shows demo mode
    await expect(page.getByText(/demo_mode=true/)).toBeVisible();
    await expect(page.getByText(/anthropic_key=false/)).toBeVisible();

    // Default selection (Intercom + Zendesk pre-selected)
    await expect(page.getByText(/2 of 4 selected/)).toBeVisible();

    // Click the run button
    const runButton = page.getByRole("button", { name: /Run \(demo\)/i });
    await expect(runButton).toBeEnabled();
    await runButton.click();

    // Plan renders — wait up to 10s for the backend round-trip
    await expect(
      page.getByRole("heading", { name: /Plan summary/i })
    ).toBeVisible({ timeout: 10_000 });

    // Synthetic plan label
    await expect(page.getByText(/DEMO\/SYNTHETIC/i)).toBeVisible();

    // Both other sections render
    await expect(
      page.getByRole("heading", { name: /Capability findings/i })
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /Recommendations/i })
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /Orchestrator PR plan/i })
    ).toBeVisible();

    // Demo-mode badge
    await expect(page.getByText(/demo mode/i).first()).toBeVisible();
  });

  test("submit disabled with zero tools selected", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/2 of 4 selected/)).toBeVisible();

    // Deselect the two pre-selected tools
    await page.getByRole("button", { name: /intercom/i }).click();
    await page.getByRole("button", { name: /zendesk/i }).click();

    await expect(page.getByText(/0 of 4 selected/)).toBeVisible();

    // Run button should be disabled
    const runButton = page.getByRole("button", { name: /Run \(demo\)/i });
    await expect(runButton).toBeDisabled();
  });

  test("selecting hubspot only yields the MCP-stub recommendation", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByText(/2 of 4 selected/)).toBeVisible();

    // Deselect Intercom + Zendesk, select Hubspot only
    await page.getByRole("button", { name: /intercom/i }).click();
    await page.getByRole("button", { name: /zendesk/i }).click();
    await page.getByRole("button", { name: /hubspot/i }).click();
    await expect(page.getByText(/1 of 4 selected/)).toBeVisible();

    await page.getByRole("button", { name: /Run \(demo\)/i }).click();

    await expect(
      page.getByRole("heading", { name: /Plan summary/i })
    ).toBeVisible({ timeout: 10_000 });

    // HubSpot has no MCP server in the registry — the synthetic plan should
    // produce an "augment_with_custom_ai" recommendation about generating a stub.
    await expect(page.getByText(/augment with custom ai/i)).toBeVisible();
  });
});
