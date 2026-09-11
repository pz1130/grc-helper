import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

async function mockAudit(page: Page, withAnswer = false) {
  await page.addInitScript(() => {
    localStorage.setItem("grc.token", "mock-token");
    localStorage.setItem("grc.lang", "en");
  });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { id: 1, email: "lead@example.com", name: "Lead", role: "grc_lead" } });
    if (url.pathname === "/api/audit/engagements") return route.fulfill({ json: [{ id: 1, name: "ISO audit", audit_type: "external", status: "preparing" }] });
    if (url.pathname === "/api/audit/engagements/1/questions/xlsx") return route.fulfill({ status: 201, json: [{ id: 9, seq: 2, question_text: "Imported question", language: "en", status: "pending" }] });
    if (url.pathname === "/api/audit/engagements/1/export.docx") return route.fulfill({ body: "fake-docx", contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
    if (url.pathname === "/api/audit/engagements/1/generate-all") return route.fulfill({ json: { job_id: "audit-job-1", question_count: 1 } });
    if (url.pathname === "/api/audit/engagements/1/questions") return route.fulfill({ json: [{ id: 2, seq: 1, question_text: "How is access reviewed?", language: "en", status: withAnswer ? "drafted" : "pending" }] });
    if (url.pathname === "/api/audit/questions/2/answer") return route.fulfill({ json: withAnswer ? { id: 3, question_id: 2, body: "Access is reviewed quarterly.", language: "en", gap_notes: "Evidence is not registered.", cited_clause_ids: [4], cited_control_ids: [5], suggested_evidence_ids: [], confidence: 0.9, final_body: null, finalized_at: null } : null });
    if (url.pathname === "/api/audit/questions/2/similar-history") return route.fulfill({ json: [{ answer_id: 8, question_id: 7, question_text: "How was access reviewed last year?", engagement_name: "Prior audit", answer: "Access was reviewed quarterly.", language: "en", finalized_at: "2026-01-01T00:00:00Z", similarity: 0.67 }] });
    if (url.pathname === "/api/audit/history") return route.fulfill({ json: [] });
    if (url.pathname === "/api/audit/answers/3/finalize") return route.fulfill({ json: {} });
    return route.fulfill({ status: 500, json: { message: `Unexpected API: ${url.pathname}` } });
  });
}

test("audit workspace shows engagement questions and guarded generation", async ({ page }) => {
  await mockAudit(page);
  await page.goto("/audit");
  await expect(page.getByRole("heading", { name: "Audit response workspace" })).toBeVisible();
  await expect(page.getByText("ISO audit")).toBeVisible();
  await expect(page.getByRole("heading", { name: "How is access reviewed?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Draft in English" })).toBeVisible();
  await expect(page.getByText("No formal draft yet. Generated answers enter the review queue first.")).toBeVisible();
  await expect(page.getByText("How was access reviewed last year?")).toBeVisible();
  await page.getByRole("button", { name: "Generate all drafts" }).click();
  await expect(page.getByRole("status")).toContainText("Queued 1 questions");
});

test("accepted draft can be edited and finalized", async ({ page }) => {
  await mockAudit(page, true);
  await page.goto("/audit");
  await expect(page.getByLabel("Answer body")).toHaveValue("Access is reviewed quarterly.");
  await expect(page.getByText("Evidence is not registered.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Finalize" })).toBeVisible();
});

test("questions can be imported from Excel and finalized answers exported", async ({ page }) => {
  await mockAudit(page, true);
  await page.goto("/audit");
  await page.getByLabel("Excel question file").setInputFiles({
    name: "questions.xlsx",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: Buffer.from("xlsx fixture"),
  });
  await page.getByRole("button", { name: "Import from Excel" }).click();
  await expect(page.getByRole("status")).toContainText("Imported 1 questions from Excel.");

  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export Word response package" }).click();
  const file = await downloaded;
  expect(file.suggestedFilename()).toBe("ISO audit-audit-responses.docx");
});
