import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

async function mockMaturity(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("grc.token", "mock-token");
    localStorage.setItem("grc.lang", "en");
  });
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { id: 1, email: "lead@example.com", name: "Lead", role: "grc_lead" } });
    if (url.pathname === "/api/frameworks") return route.fulfill({ json: [{ id: 7, name_zh: "网络安全框架", name_en: "Cybersecurity Framework", version: "2.0" }] });
    if (url.pathname === "/api/maturity/assessments" && request.method() === "GET") return route.fulfill({ json: [{ id: 3, framework_id: 7, name: "2026 baseline", as_of_date: "2026-09-11", status: "draft" }] });
    if (url.pathname === "/api/maturity/assessments/3/summary") return route.fulfill({ json: {
      assessment_id: 3,
      framework_id: 7,
      overall: { total_items: 4, scored_items: 3, doc_average: 3, impl_average: 2 },
      groups: [
        { framework_item_id: 10, code: "GV", title: "Govern", total_items: 2, scored_items: 1, doc_average: 4, impl_average: 3 },
        { framework_item_id: 20, code: "PR", title: "Protect", total_items: 1, scored_items: 1, doc_average: 3, impl_average: 2 },
        { framework_item_id: 30, code: "DE", title: "Detect", total_items: 1, scored_items: 1, doc_average: 2, impl_average: 1 },
      ],
      items: [
        { framework_item_id: 11, parent_id: 10, group_id: 10, code: "GV.PO-01", title: "Policy", doc_score: 4, impl_score: 3, doc_rationale: "Approved policy", impl_rationale: "Operating evidence" },
        { framework_item_id: 12, parent_id: 10, group_id: 10, code: "GV.RR-01", title: "Roles", doc_score: null, impl_score: null, doc_rationale: "", impl_rationale: "" },
        { framework_item_id: 21, parent_id: 20, group_id: 20, code: "PR.AA-01", title: "Access", doc_score: 3, impl_score: 2, doc_rationale: "Defined", impl_rationale: "Partially implemented" },
        { framework_item_id: 31, parent_id: 30, group_id: 30, code: "DE.CM-01", title: "Monitoring", doc_score: 2, impl_score: 1, doc_rationale: "Partial", impl_rationale: "Ad hoc" },
      ],
    } });
    if (url.pathname === "/api/maturity/assessments/3/scores" && request.method() === "PUT") return route.fulfill({ json: { id: 99 } });
    if (url.pathname === "/api/maturity/assessments/3/finalize") return route.fulfill({ json: { id: 3, framework_id: 7, name: "2026 baseline", as_of_date: "2026-09-11", status: "final" } });
    return route.fulfill({ status: 500, json: { message: `Unexpected API: ${url.pathname}` } });
  });
}

test("maturity workspace shows dual rollups and saves leaf scores", async ({ page }) => {
  await mockMaturity(page);
  await page.goto("/maturity");

  await expect(page.getByRole("heading", { name: "Maturity assessment" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Dual-line maturity radar chart" })).toBeVisible();
  await expect(page.getByText("3.00").first()).toBeVisible();
  await expect(page.getByText("75%")).toBeVisible();

  await page.getByLabel("GV.RR-01 Document score").selectOption("3");
  await page.getByLabel("GV.RR-01 Implementation score").selectOption("2");
  await page.getByLabel("GV.RR-01 Documentation rationale").fill("Roles are documented");
  await page.getByRole("row").filter({ hasText: "GV.RR-01" }).getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("row").filter({ hasText: "GV.RR-01" }).getByRole("status")).toHaveText("Saved.");
});
