import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

/**
 * Role and tool cards toggle from the card and from Select/Add.
 * Enablement progress stays inside step 3.
 */

function repoRoot(): string {
  let dir = __dirname;
  for (let i = 0; i < 6; i += 1) {
    if (existsSync(path.join(dir, "pyproject.toml"))) return dir;
    dir = path.dirname(dir);
  }
  throw new Error(`repo root not found from ${__dirname}`);
}

const SEEDED = ["intercom", "slack"] as const;

function seedTools(): void {
  const names = JSON.stringify(SEEDED);
  const body = `from core.identity import local_user
from core.tool_catalog import cache_tool, load_tool
user = local_user()
for name in ${names}:
    cap = load_tool(user, name)
    if cap is None:
        raise SystemExit(f"missing seed tool {name}")
    cache_tool(user, cap)
`;
  execFileSync(path.join(repoRoot(), ".venv/bin/python"), ["-c", body], {
    cwd: repoRoot(),
  });
}

test.beforeAll(() => {
  seedTools();
});

test("role and tool cards toggle from the card and from Select or Add", async ({
  page,
}) => {
  await page.goto("/");
  const roleButton = page.getByRole("button", { name: /^Developer Relations/ });
  await expect(roleButton).toBeVisible();
  const roleCard = roleButton.locator("xpath=..");
  const roleBox = await roleCard.boundingBox();
  if (!roleBox) throw new Error("role card has no box");
  await page.mouse.click(roleBox.x + 6, roleBox.y + 6);
  await expect(
    roleCard.getByRole("button", { name: "Selected", exact: true }),
  ).toBeVisible();

  await roleCard.getByRole("button", { name: "Selected", exact: true }).click();
  await expect(
    roleCard.getByRole("button", { name: "Select", exact: true }),
  ).toBeVisible();

  await roleCard.getByRole("button", { name: "Select", exact: true }).click();
  await expect(
    roleCard.getByRole("button", { name: "Selected", exact: true }),
  ).toBeVisible();

  const toolButton = page.getByRole("button", { name: /^Intercom/ });
  await expect(toolButton).toBeVisible();
  const toolRow = toolButton.locator("xpath=ancestor::li");
  await toolRow.getByRole("button", { name: "Add", exact: true }).click();
  await expect(
    toolRow.getByRole("button", { name: "Selected", exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/1 of \d+ selected/)).toBeVisible();

  const toolBox = await toolRow.boundingBox();
  if (!toolBox) throw new Error("tool row has no box");
  await page.mouse.click(toolBox.x + 8, toolBox.y + 8);
  await expect(toolRow.getByRole("button", { name: "Add", exact: true })).toBeVisible();
  await expect(page.getByText(/0 of \d+ selected/)).toBeVisible();

  await page.mouse.click(toolBox.x + 8, toolBox.y + 8);
  await expect(
    toolRow.getByRole("button", { name: "Selected", exact: true }),
  ).toBeVisible();
});

test("enablement progress stays inside step 3", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /^Developer Relations/ }).click();
  await page.getByRole("button", { name: /^Intercom/ }).click();
  await page.getByRole("button", { name: /^Slack/ }).click();

  await page.route("**/api/jobs/*", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const url = new URL(route.request().url());
    const id = url.pathname.split("/").pop() ?? "job";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id,
        kind: "enablement",
        status: "running",
        started_at: new Date().toISOString(),
        result: null,
        error: null,
      }),
    });
  });

  await page.getByRole("button", { name: /Run \(demo\)/i }).click();
  const step3 = page.locator("section").filter({
    has: page.getByRole("heading", { name: "3. Run the Enablement Agent" }),
  });
  await expect(step3.getByText("Running Enablement Agent…")).toBeVisible();
  await expect(page.getByRole("heading", { name: "4. In progress" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "4. Plan" })).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "5. Pick one recommendation" }),
  ).toHaveCount(0);
});

test("finished plan shows relationships and a research kit", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /^Developer Relations/ }).click();
  await page.getByRole("button", { name: /^Intercom/ }).click();
  await page.getByRole("button", { name: /^Slack/ }).click();
  await page.getByRole("button", { name: /Run \(demo\)/i }).click();

  await expect(
    page.getByRole("heading", { name: "How these tools work together" }),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "4. Plan" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Research kit" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /6\. Hand / })).toHaveCount(0);
});
