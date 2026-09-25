import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

/**
 * Step 5 selects a recommendation, or a recommendation the user writes.
 * Step 6 (the Grok Bot handoff) stays on the last submitted recommendation
 * until Submit is pressed again.
 */

function repoRoot(): string {
  let dir = __dirname;
  for (let i = 0; i < 6; i += 1) {
    if (existsSync(path.join(dir, "pyproject.toml"))) return dir;
    dir = path.dirname(dir);
  }
  throw new Error(`repo root not found from ${__dirname}`);
}

const REPO = repoRoot();
const PYTHON = path.join(REPO, ".venv/bin/python");
const SEEDED = ["intercom", "zendesk"] as const;

function seedTools(remove: boolean): void {
  const names = JSON.stringify(SEEDED);
  const body = remove
    ? `from core.identity import local_user
from core.tool_catalog import delete_cached_tool
user = local_user()
for name in ${names}:
    delete_cached_tool(user, name)
`
    : `from core.identity import local_user
from core.tool_catalog import cache_tool, load_tool
user = local_user()
for name in ${names}:
    cap = load_tool(user, name)
    if cap is None:
        raise SystemExit(f"missing seed tool {name}")
    cache_tool(user, cap)
`;
  execFileSync(PYTHON, ["-c", body], { cwd: REPO });
}

test.beforeAll(() => {
  seedTools(false);
});

test.afterAll(() => {
  seedTools(true);
});

test("handoff appears only after submit and keeps the last submitted recommendation", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: /^Developer Relations/ })).toBeVisible();
  await page.getByRole("button", { name: /^Developer Relations/ }).click();
  await page.getByRole("button", { name: /^Intercom/ }).click();
  await page.getByRole("button", { name: /^Zendesk/ }).click();

  await page.getByRole("button", { name: /Run \(demo\)/i }).click();
  await expect(page.getByRole("heading", { name: /Plan summary/i })).toBeVisible({
    timeout: 90_000,
  });

  await expect(
    page.getByRole("heading", { name: "5. Pick one recommendation" }),
  ).toBeVisible();
  const submit = page.getByRole("button", { name: "Submit", exact: true });
  await expect(submit).toBeDisabled();
  await expect(page.getByRole("heading", { name: /6\. Hand / })).toHaveCount(0);
  await expect(
    page.getByText("Select a recommendation and press Submit to hand it to Grokbot."),
  ).toBeVisible();

  const cards = page.locator("ul li").filter({ has: page.getByRole("radio") });
  await expect(cards).toHaveCount(2);
  const firstId = (await cards.nth(0).locator(".font-mono").innerText()).trim();
  const secondId = (await cards.nth(1).locator(".font-mono").innerText()).trim();
  expect(firstId).not.toEqual(secondId);

  await cards.nth(0).getByRole("radio").check();
  await expect(page.getByRole("heading", { name: /6\. Hand / })).toHaveCount(0);
  await expect(submit).toBeEnabled();

  await submit.click();
  const firstHeading = page.getByRole("heading", {
    name: `6. Hand ${firstId} to Grokbot`,
  });
  await expect(firstHeading).toBeVisible();
  await expect(page.getByText("Preparing the assignment…")).toHaveCount(0);
  const botName = page.getByText("Bot name", { exact: true }).locator("..");
  await expect(botName).toContainText("Developer Relations");
  await expect(botName).not.toContainText(firstId);
  await expect(page.getByText(/add this to existing bot R-/)).toHaveCount(0);
  // Next.js dev strict mode runs the handoff fetch twice. The first request
  // remembers the bot, so the line may already be visible here.
  const remembered = page.getByText("Using bots remembered from earlier handoffs.", {
    exact: true,
  });

  await cards.nth(1).getByRole("radio").check();
  await expect(firstHeading).toBeVisible();
  await expect(
    page.getByRole("heading", { name: `6. Hand ${secondId} to Grokbot` }),
  ).toHaveCount(0);
  await expect(
    page.getByText(
      `The Grokbot handoff stays on ${firstId} until you submit again.`,
    ),
  ).toBeVisible();

  await submit.click();
  await expect(
    page.getByRole("heading", { name: `6. Hand ${secondId} to Grokbot` }),
  ).toBeVisible();
  await expect(firstHeading).toHaveCount(0);
  await expect(remembered).toBeVisible();
});

test("a custom recommendation submits into the same handoff", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: /^Developer Relations/ })).toBeVisible();
  await page.getByRole("button", { name: /^Developer Relations/ }).click();
  await page.getByRole("button", { name: /^Intercom/ }).click();
  await page.getByRole("button", { name: /^Zendesk/ }).click();

  await page.getByRole("button", { name: /Run \(demo\)/i }).click();
  await expect(page.getByRole("heading", { name: /Plan summary/i })).toBeVisible({
    timeout: 90_000,
  });

  const submit = page.getByRole("button", { name: "Submit", exact: true });
  const custom = page.getByRole("radio", { name: /Suggest your own/ });
  const recommendation = page.getByRole("textbox", { name: "Recommendation" });
  const title = page.getByRole("textbox", { name: /Title/ });
  const cards = page.locator("ul li").filter({ has: page.getByRole("radio") });
  await expect(cards).toHaveCount(2);
  const systemId = (await cards.nth(0).locator(".font-mono").innerText()).trim();

  await expect(page.getByRole("heading", { name: /6\. Hand / })).toHaveCount(0);
  await custom.check();
  await expect(submit).toBeDisabled();
  await recommendation.fill("   ");
  await expect(submit).toBeDisabled();
  await expect(page.getByRole("heading", { name: /6\. Hand / })).toHaveCount(0);

  const body = "Draft a Friday forum recap from unread threads.";
  await title.fill("Friday forum recap");
  await recommendation.fill(body);
  await expect(custom).toBeChecked();
  await expect(cards.nth(0).getByRole("radio")).not.toBeChecked();
  await expect(submit).toBeEnabled();

  await cards.nth(0).getByRole("radio").check();
  await expect(custom).not.toBeChecked();
  await expect(page.getByRole("heading", { name: /6\. Hand / })).toHaveCount(0);

  await custom.check();
  await expect(cards.nth(0).getByRole("radio")).not.toBeChecked();
  await submit.click();

  const customHeading = page.getByRole("heading", {
    name: "6. Hand R-CUSTOM to Grokbot",
  });
  await expect(customHeading).toBeVisible();
  await expect(page.getByText("Preparing the assignment…")).toHaveCount(0);
  const assignment = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: /6\. Hand / }) })
    .locator("pre");
  await expect(assignment).toContainText(body);
  await expect(assignment).toContainText("Friday forum recap");
  await expect(assignment).not.toContainText("R-CUSTOM");
  const botName = page.getByText("Bot name", { exact: true }).locator("..");
  await expect(botName).toContainText("Developer Relations");
  await expect(botName).not.toContainText("R-CUSTOM");

  await cards.nth(0).getByRole("radio").check();
  await expect(customHeading).toBeVisible();
  await expect(
    page.getByText("The Grokbot handoff stays on R-CUSTOM until you submit again."),
  ).toBeVisible();

  await submit.click();
  const systemHeading = page.getByRole("heading", {
    name: `6. Hand ${systemId} to Grokbot`,
  });
  await expect(systemHeading).toBeVisible();
  await expect(customHeading).toHaveCount(0);

  await recommendation.fill(`${body} Add the unanswered questions.`);
  await expect(custom).toBeChecked();
  await expect(systemHeading).toBeVisible();
  await expect(
    page.getByText(
      `The Grokbot handoff stays on ${systemId} until you submit again.`,
    ),
  ).toBeVisible();

  await submit.click();
  await expect(customHeading).toBeVisible();
  await expect(systemHeading).toHaveCount(0);
  await expect(assignment).toContainText("Add the unanswered questions.");
});
