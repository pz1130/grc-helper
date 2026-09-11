import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const conflictProposal = {
  id: 501,
  kind: "conflict",
  status: "pending",
  confidence: 0.82,
  payload: {
    clause_a_id: 91,
    clause_b_id: 92,
    topic: "Password rotation period",
    difference: "The policy requires 90 days; the standard allows 180 days.",
    quote_a: "every 90 days",
    quote_b: "every 180 days",
  },
  citations: [
    { clause_id: 91, quote: "every 90 days" },
    { clause_id: 92, quote: "every 180 days" },
  ],
};

export async function mockConflicts(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("grc.token", "mock-token");
    localStorage.setItem("grc.lang", "en");
  });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me")
      return route.fulfill({ json: { id: 1, email: "lead@example.com", name: "Lead", role: "grc_lead" } });
    if (url.pathname === "/api/proposals/stats")
      return route.fulfill({ json: { pending: 1, by_kind: { conflict: 1 } } });
    if (url.pathname === "/api/proposals")
      return route.fulfill({ json: [conflictProposal] });
    if (url.pathname === "/api/clauses/91")
      return route.fulfill({ json: {
        id: 91, document_id: 3, document_title: "Password Policy", number: "4.2",
        heading: "Rotation", heading_path: "Password › Rotation", citation_label: "4.2",
        text: "Passwords rotate every 90 days.", level: 2, page_ref: 4 } });
    if (url.pathname === "/api/clauses/92")
      return route.fulfill({ json: {
        id: 92, document_id: 5, document_title: "Access Standard", number: "7.1",
        heading: "Credentials", heading_path: "Access › Credentials", citation_label: "7.1",
        text: "Passwords rotate every 180 days.", level: 2, page_ref: 9 } });
    return route.fulfill({ status: 500, json: { message: `Unexpected API: ${url.pathname}` } });
  });
}

test("a conflict card shows both clause texts side by side", async ({ page }) => {
  await mockConflicts(page);
  await page.goto("/review");

  const card = page.locator('[data-proposal-kind="conflict"]');
  await expect(card).toBeVisible();
  await expect(card.getByText("Password rotation period")).toBeVisible();
  await expect(card.getByText("Passwords rotate every 90 days.")).toBeVisible();
  await expect(card.getByText("Passwords rotate every 180 days.")).toBeVisible();
  await expect(card.getByText("Password Policy")).toBeVisible();
  await expect(card.getByText("Access Standard")).toBeVisible();
});

test("a conflict card states what each side requires", async ({ page }) => {
  await mockConflicts(page);
  await page.goto("/review");

  await expect(
    page.getByText("The policy requires 90 days; the standard allows 180 days."),
  ).toBeVisible();
});

test("conflict cards offer no bulk accept checkbox", async ({ page }) => {
  await mockConflicts(page);
  await page.goto("/review");

  // 与 relation 提案一致：冲突要逐条看原文，不给批量确认。
  await expect(
    page.locator('[data-proposal-kind="conflict"] input[type="checkbox"]'),
  ).toHaveCount(0);
});
