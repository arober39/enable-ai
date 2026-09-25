import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

/**
 * Step 5 selects a recommendation. Step 6 (the Grok Bot handoff) stays
 * on the last submitted recommendation until Submit is pressed again.
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
