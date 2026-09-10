import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

// Every API request is intercepted: these tests never access the application DB.
async function mockSession(page: Page, role = "grc_lead") {
  await page.addInitScript(() => {
    localStorage.setItem("grc.token", "mock-token");
    localStorage.setItem("grc.lang", "en");
  });
  await page.route("**/api/**", async (route) => {
    if (new URL(route.request().url()).pathname === "/api/auth/me") {
      await route.fulfill({ json: { id: 1, email: `${role}@example.com`, name: "User", role } });
    } else {
      await route.fulfill({ status: 500, json: { message: `Unexpected API: ${route.request().url()}` } });
    }
  });
}

const relationProposal = {
  id: 31,
  kind: "relation",
  payload: {
    from_control_id: 1,
    to_control_id: 2,
    relation_type: "depends_on",
    from_quote: "Approved by the CAB",
    to_quote: "Follow the plan",
    rationale: "ordering",
    confidence: 0.8,
  },
  citations: [],
  confidence: 0.8,
  document_id: null,
  status: "pending",
  bulk_acceptable: false,
  relation_context: {
    relation_type: "depends_on",
    from: { id: 1, code: "C-0001", title: "Approval", statement: "Changes are Approved by the CAB before release." },
    to: { id: 2, code: "C-0002", title: "Implementation", statement: "Follow the plan after CAB approval." },
  },
};

async function mockRelationQueue(page: Page) {
  await page.route("**/api/proposals**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/proposals/stats") {
      return route.fulfill({ json: { pending: 1, by_kind: { relation: 1 } } });
    }
    return route.fulfill({ json: [relationProposal] });
  });
}

test("relation proposals show both controls side by side with highlighted quotes", async ({ page }) => {
  await mockSession(page);
  await mockRelationQueue(page);
  await page.goto("/review?kind=relation");
  const card = page.locator("#proposal-31");
  await expect(card.getByRole("heading", { name: "Starting control · C-0001 Approval" })).toBeVisible();
  await expect(card.getByRole("heading", { name: "Ending control · C-0002 Implementation" })).toBeVisible();
  await expect(card.getByText("Changes are Approved by the CAB before release.")).toBeVisible();
  await expect(card.getByText("Follow the plan after CAB approval.")).toBeVisible();
  await expect(card.locator("mark").filter({ hasText: "Approved by the CAB" })).toHaveCount(1);
  await expect(card.locator("mark").filter({ hasText: "Follow the plan" })).toHaveCount(1);
});

test("relation type is shown as a translated label rather than depends_on", async ({ page }) => {
  await mockSession(page);
  await mockRelationQueue(page);
  await page.goto("/review?kind=relation");
  const card = page.locator("#proposal-31");
  await expect(card.getByText("Depends on", { exact: true })).toBeVisible();
  await expect(card).not.toContainText("depends_on");
});

test("contributors do not see the run relation inference button", async ({ page }) => {
  await mockSession(page, "contributor");
  await mockRelationQueue(page);
  await page.goto("/review");
  await expect(page.getByText("C-0001", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run relation inference" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Backfill control embeddings" })).toHaveCount(0);
});

test("relation proposals do not offer a bulk-accept checkbox", async ({ page }) => {
  await mockSession(page);
  await mockRelationQueue(page);
  await page.goto("/review?kind=relation");
  await expect(page.locator("#proposal-31")).toBeVisible();
  await expect(page.getByLabel("Select proposal 31")).toHaveCount(0);
});

test("relation cards show a payload textarea while editing", async ({ page }) => {
  await mockSession(page);
  await mockRelationQueue(page);
  await page.goto("/review?kind=relation");
  const card = page.locator("#proposal-31");
  await card.getByRole("button", { name: "Edit and accept" }).click();
  await expect(card.getByLabel("Proposed content (JSON)")).toBeVisible();
  await expect(card.getByRole("heading", { name: "Starting control · C-0001 Approval" })).toBeVisible();
  await expect(card.getByRole("heading", { name: "Ending control · C-0002 Implementation" })).toBeVisible();
});

test("a relation whose control was deleted still shows its payload and stays editable", async ({ page }) => {
  await mockSession(page);
  await page.route("**/api/proposals**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/proposals/stats") {
      return route.fulfill({ json: { pending: 1, by_kind: { relation: 1 } } });
    }
    // 一端控制点被删：后端给不出 relation_context，卡片不能因此变成空白。
    return route.fulfill({ json: [{ ...relationProposal, relation_context: null }] });
  });
  await page.goto("/review?kind=relation");
  const card = page.locator("#proposal-31");
  await expect(card.getByText("Depends on", { exact: true })).toBeVisible();
  await expect(card.getByText(/no longer exists/)).toBeVisible();
  await expect(card.getByText(/"from_quote": "Approved by the CAB"/)).toBeVisible();
  await card.getByRole("button", { name: "Edit and accept" }).click();
  await expect(card.getByLabel("Proposed content (JSON)")).toBeVisible();
});
