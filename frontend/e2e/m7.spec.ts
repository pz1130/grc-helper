import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

async function mockSession(page: Page, role = "contributor") {
  await page.addInitScript(() => {
    localStorage.setItem("grc.token", "mock-token");
    localStorage.setItem("grc.lang", "en");
  });
  await page.route("**/api/auth/me", (route) => route.fulfill({
    json: { id: 7, email: `${role}@example.com`, name: "User", role },
  }));
}

const asset = {
  id: 4, name: "VaultKeeper", category: "pam", vendor: "VaultKeeper", environment: "prod",
  owner_user_id: 7, scope_note: "Privileged accounts", status: "active", created_at: "2026-09-10T00:00:00Z",
};

test("tech asset registry expands to show supported controls", async ({ page }) => {
  await mockSession(page);
  await page.route("**/api/tech-assets", (route) => route.fulfill({ json: [asset] }));
  await page.route("**/api/tech-assets/4/controls", (route) => route.fulfill({ json: [{
    id: 10, control_id: 12, tech_asset_id: 4, description: "Session review", how_enforced: "automated",
    status: "implemented", na_justification: null, owner_user_id: 7, last_verified_at: null,
    control_code: "AC-01", control_title: "Privileged access review",
  }] }));
  await page.goto("/tech-assets");
  await expect(page.getByRole("cell", { name: "VaultKeeper", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Show controls" }).click();
  await expect(page.getByText("AC-01")).toBeVisible();
  await expect(page.getByText("Privileged access review")).toBeVisible();
});

test("evidence library combines status and owner filters", async ({ page }) => {
  await mockSession(page, "viewer");
  const requested: string[] = [];
  await page.route("**/api/evidence**", async (route) => {
    if (new URL(route.request().url()).pathname !== "/api/evidence") return route.fallback();
    requested.push(route.request().url());
    await route.fulfill({ json: [{
      id: 9, evidence_type_id: 2, control_id: 12, tech_asset_id: 4, title: "Quarterly PAM sample",
      owner_user_id: 7, location_hint: "VaultKeeper", last_collected_at: "2026-01-01T00:00:00Z",
      valid_until: "2026-03-31T00:00:00Z", file_path: null, status: "expired", intent_status: "collected",
      display_status: "expired", created_at: "2026-01-01T00:00:00Z", evidence_type_name: "PAM sample",
      control_code: "AC-01", control_title: "Privileged access review", tech_asset_name: "VaultKeeper",
    }] });
  });
  await page.goto("/evidence");
  await expect(page.getByText("Quarterly PAM sample")).toBeVisible();
  await page.getByLabel("Display status").selectOption("expired");
  await page.getByLabel("Owner user ID").fill("7");
  await expect.poll(() => requested.at(-1) ?? "").toContain("status=expired");
  await expect.poll(() => requested.at(-1) ?? "").toContain("owner_user_id=7");
  await expect(page.getByRole("table").getByText("Expired", { exact: true })).toBeVisible();
});

test("overview shows the live expired evidence count", async ({ page }) => {
  await mockSession(page, "viewer");
  await page.route("**/api/settings/usage", (route) => route.fulfill({ json: { month_to_date_cost: 0, budget: null, by_task: [] } }));
  await page.route("**/api/evidence/stats", (route) => route.fulfill({ json: { expired: 3 } }));
  await page.goto("/");
  await expect(page.getByText("Expired evidence", { exact: true })).toBeVisible();
  await expect(page.getByText("3", { exact: true })).toBeVisible();
  await expect(page.getByText("Needs attention", { exact: true })).toBeVisible();
});

// ── 冷启动空状态 ── OQ-24 ──────────────────────────────────────────
//
// 新部署时控制点库和证据类型都是空的，"新增证据"的保存按钮因而永久置灰
// （disabled 条件里有 !form.control_id 和 !form.evidence_type_id），
// 界面上不给任何解释。每个新租户上线第一天必撞。
//
// 验的是**它说出缺什么**，不是"按钮是灰的"——按钮灰着是对的，
// 缺的是那句话。

test("empty control library explains what to create first instead of a dead grey button", async ({ page }) => {
  await mockSession(page, "contributor");
  await page.route("**/api/evidence**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/evidence-types", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/controls**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/tech-assets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/users", (route) => route.fulfill({ json: [] }));

  await page.goto("/evidence");
  await page.getByRole("button", { name: "Add", exact: true }).click();

  const notice = page.getByRole("note");
  await expect(notice).toBeVisible();
  // 两个前置都空，两个都要点名——只说一个会让人补完还是存不了
  await expect(notice).toContainText("control");
  await expect(notice).toContainText("evidence type");
  // 并且给得出去处
  await expect(notice.getByRole("link", { name: /control/i })).toBeVisible();
});

test("a satisfied prerequisite is not listed as missing", async ({ page }) => {
  await mockSession(page, "contributor");
  await page.route("**/api/evidence**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/evidence-types", (route) => route.fulfill({
    json: [{ id: 1, name: "Screenshot", default_validity_days: 90 }],
  }));
  await page.route("**/api/controls**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/tech-assets", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/users", (route) => route.fulfill({ json: [] }));

  await page.goto("/evidence");
  await page.getByRole("button", { name: "Add", exact: true }).click();

  const notice = page.getByRole("note");
  await expect(notice).toContainText("control");
  await expect(notice).not.toContainText("evidence type");
});
