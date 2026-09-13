import { expect, test } from "@playwright/test";

test("文档页可以对条款拆分和合并", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("grc.token", "mock-token");
    localStorage.setItem("grc.lang", "en");
  });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") {
      return route.fulfill({
        json: { id: 1, email: "c@example.com", name: "Contrib", role: "contributor" },
      });
    }
    if (url.pathname === "/api/documents/3") {
      return route.fulfill({
        json: {
          id: 3, title: "Example Visitor Access Policy", doc_type: "policy",
          status: "active", version: "1", owner: null, parse_warnings: null, supersedes_id: null,
        },
      });
    }
    if (url.pathname === "/api/documents/3/clauses") {
      return route.fulfill({
        json: [{
          id: 11, number: "1", heading: "Scope", heading_path: "Scope",
          citation_label: "1", text: "First paragraph.\n\nSecond paragraph.",
          level: 1, page_ref: null, kind: "section", children: [],
        }],
      });
    }
    return route.fulfill({ json: [] });
  });

  await page.goto("/documents/3");
  await page.getByRole("button", { name: /Scope/ }).click();
  await expect(page.getByRole("button", { name: "Split at cursor" })).toBeVisible();
  await expect(page.getByLabel("Choose a clause")).toBeVisible();
});
