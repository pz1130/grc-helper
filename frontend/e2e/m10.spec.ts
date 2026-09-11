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

const impact = {
  previous_document: { id: 3, title: "Password Policy", version: "1.0" },
  added: [{ clause_id: 21, citation_label: "4.4", text: "Passwords must not be reused." }],
  removed: [{ clause_id: 11, citation_label: "4.2", text: "Passwords rotate every 90 days." }],
  matched: [{ old_clause_id: 12, new_clause_id: 22, citation_label: "4.3" }],
  affected_controls: [{ id: 7, code: "C-0007", title: "Password rotation" }],
  affected_mappings: [{ id: 31, control_id: 7, framework_item_code: "PR.AA-01" }],
  affected_evidence: [{ id: 41, control_id: 7, title: "AD rotation export" }],
};

async function mockImpact(page: Page, options: { noPrevious?: boolean } = {}) {
  await page.addInitScript(() => {
    localStorage.setItem("grc.token", "mock-token");
    localStorage.setItem("grc.lang", "en");
  });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me")
      return route.fulfill({ json: { id: 1, email: "lead@example.com", name: "Lead", role: "grc_lead" } });
    if (url.pathname === "/api/documents/5")
      return route.fulfill({ json: {
        id: 5, title: "Password Policy", status: "active", version: "2.0",
        owner: null, parse_warnings: null, supersedes_id: options.noPrevious ? null : 3,
      } });
    if (url.pathname === "/api/documents/5/clauses")
      return route.fulfill({ json: [] });
    if (url.pathname === "/api/documents/5/change-impact") {
      if (options.noPrevious)
        return route.fulfill({ status: 400, json: { message: "该文档没有上一版本" } });
      return route.fulfill({ json: impact });
    }
    return route.fulfill({ status: 500, json: { message: `Unexpected API: ${url.pathname}` } });
  });
}

test("the document page offers importing a new version", async ({ page }) => {
  await mockImpact(page);
  await page.goto("/documents/5");

  await expect(page.getByRole("button", { name: "Import new version" })).toBeVisible();
});

test("the change impact page shows added, removed and matched clauses", async ({ page }) => {
  await mockImpact(page);
  await page.goto("/documents/5/change-impact");

  await expect(page.getByText("Passwords must not be reused.")).toBeVisible();
  await expect(page.getByText("Passwords rotate every 90 days.")).toBeVisible();
  await expect(page.locator('[data-impact-section="added"] li')).toHaveCount(1);
  await expect(page.locator('[data-impact-section="removed"] li')).toHaveCount(1);
  await expect(page.locator('[data-impact-section="matched"] li')).toHaveCount(1);
});

test("the change impact page lists what the removed clauses were holding up", async ({ page }) => {
  await mockImpact(page);
  await page.goto("/documents/5/change-impact");

  await expect(page.getByText("C-0007")).toBeVisible();
  await expect(page.getByText("PR.AA-01")).toBeVisible();
  await expect(page.getByText("AD rotation export")).toBeVisible();
});

test("a document with no previous version says so instead of erroring", async ({ page }) => {
  await mockImpact(page, { noPrevious: true });   // 让接口回 400
  await page.goto("/documents/5/change-impact");

  await expect(page.getByText("no previous version")).toBeVisible();
});

function daysFromToday(days: number): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

const documents = [
  { id: 1, title: "Overdue Policy", review_due_date: daysFromToday(-365), status: "active" },
  { id: 2, title: "Due Soon Standard", review_due_date: daysFromToday(9), status: "active" },
  { id: 3, title: "Fresh Guideline", review_due_date: daysFromToday(400), status: "active" },
  { id: 4, title: "Undated Procedure", review_due_date: null, status: "active" },
];

async function mockDocuments(page: Page, docs: typeof documents) {
  await page.addInitScript(() => {
    localStorage.setItem("grc.token", "mock-token");
    localStorage.setItem("grc.lang", "en");
  });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me")
      return route.fulfill({ json: { id: 1, email: "lead@example.com", name: "Lead", role: "grc_lead" } });
    if (url.pathname === "/api/settings/usage")
      return route.fulfill({ json: { month_to_date_cost: 0, budget: null, by_task: [] } });
    if (url.pathname === "/api/evidence/stats")
      return route.fulfill({ json: { expired: 0 } });
    if (url.pathname === "/api/documents")
      return route.fulfill({ json: docs });
    if (url.pathname === "/api/documents/coverage")
      return route.fulfill({ json: [] });
    return route.fulfill({ status: 500, json: { message: `Unexpected API: ${url.pathname}` } });
  });
}

test("the overview counts overdue and soon-due policies", async ({ page }) => {
  await mockDocuments(page, documents);
  await page.goto("/");

  const card = page.locator('[data-card="review-due"]');
  await expect(card).toBeVisible();
  await expect(card.getByText("1 overdue")).toBeVisible();
  await expect(card.getByText("1 due within 30 days")).toBeVisible();
});

test("the overview card links into the filtered document list", async ({ page }) => {
  await mockDocuments(page, documents);
  await page.goto("/");

  await page.locator('[data-card="review-due"]').getByRole("link").first().click();

  await expect(page).toHaveURL(/\/documents\?review=overdue/);
});

test("the document list can show only the overdue ones", async ({ page }) => {
  await mockDocuments(page, documents);
  await page.goto("/documents?review=overdue");

  await expect(page.getByText("Overdue Policy")).toBeVisible();
  await expect(page.getByText("Fresh Guideline")).toHaveCount(0);
  await expect(page.getByText("Undated Procedure")).toHaveCount(0);
});

test("documents without a review date are not counted as overdue", async ({ page }) => {
  await mockDocuments(page, documents);
  await page.goto("/");

  // 没填日期 ≠ 逾期。填不填是人的事，系统不替他判。
  await expect(page.locator('[data-card="review-due"]').getByText("1 overdue")).toBeVisible();
});
