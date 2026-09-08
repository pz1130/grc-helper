import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const ADMIN = { email: "admin@example.com", password: "pw123456" };
const SECRET = "sk-e2e-supersecret-value";
const PROVIDER_NAME = `e2e-${Date.now()}`;

async function signIn(page: Page) {
  await page.goto("/");
  await page.getByLabel("邮箱").fill(ADMIN.email);
  await page.getByLabel("密码").fill(ADMIN.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page.getByRole("heading", { name: "总览" })).toBeVisible();
}

test("管理员能登录并看到总览", async ({ page }) => {
  await signIn(page);
});

test("语言可切换到英文", async ({ page }) => {
  await signIn(page);
  await page.getByLabel("语言").selectOption("en");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
});

test("新建的 provider 只显示掩码后的 key", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings/providers");

  await page.getByPlaceholder("name").fill(PROVIDER_NAME);
  await page.getByPlaceholder("api key").fill(SECRET);
  await page.getByRole("button", { name: "保存" }).first().click();

  // 名字在路由下拉的 option 里也会出现，且历次冒烟会在库里留下多行，
  // 所以一律锁定到本次创建的那一行。
  const row = page.getByRole("row", { name: new RegExp(PROVIDER_NAME) });
  await expect(row).toBeVisible();
  await expect(page.getByText(SECRET)).toHaveCount(0);
  await expect(row.getByRole("code")).toHaveText("…alue");
});

test("脱敏预览显示实际会发出去的内容", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings/redaction");

  await page.getByLabel("发送预览输入").fill("跳板机 10.20.30.40 需季度复核");
  await page.getByRole("button", { name: "预览" }).click();

  const preview = page.locator("pre");
  await expect(preview).toContainText("[[IP_1]]");
  await expect(preview).not.toContainText("10.20.30.40");
});

test("阈值顺序错误会被拒绝", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings/thresholds");

  await page.getByLabel("自动接受阈值（高于此值允许批量接受）").fill("0.3");
  await page.getByLabel("强制人工阈值（低于此值必须逐条确认）").fill("0.8");
  await page.getByRole("button", { name: "保存" }).click();

  await expect(page.getByRole("alert")).toContainText("必须高于");
});

test("配置变更留下了审计日志且不含明文密钥", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings/audit-log");

  await expect(page.getByText("provider.create").first()).toBeVisible();
  await expect(page.getByText(SECRET)).toHaveCount(0);
});

test("GRC Lead 看不到也进不去 AI 配置页", async ({ page, request }) => {
  await signIn(page);
  await page.goto("/settings/users");

  const lead = `lead-${Date.now()}@example.com`;
  await page.getByPlaceholder("email").fill(lead);
  await page.getByPlaceholder("name").fill("Lead");
  await page.getByLabel("new user role").selectOption("grc_lead");
  await page.getByPlaceholder("初始密码（至少 8 位）").fill("pw123456");
  await page.getByRole("button", { name: "保存" }).click();
  // exact 必需：启用状态那格的 aria-label 里也带着邮箱
  await expect(page.getByRole("cell", { name: lead, exact: true })).toBeVisible();

  // 换成 GRC Lead 登录：菜单里不该出现 AI 配置入口
  await page.getByRole("button", { name: "退出" }).click();
  await expect(page.getByRole("heading", { name: "登录" })).toBeVisible();

  await page.getByLabel("邮箱").fill(lead);
  await page.getByLabel("密码").fill("pw123456");
  await page.getByRole("button", { name: "登录" }).click();
  // 登录成功后停在退出前的 URL，不会回首页——用"退出按钮出现"当已登录的标志。
  // 不等这一步就 goto，会赶在 token 写入之前。
  await expect(page.getByRole("button", { name: "退出" })).toBeVisible();
  await page.goto("/settings");
  await expect(page.getByRole("link", { name: "AI Provider" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "操作日志" })).toBeVisible();

  // 前端只是藏入口，真正的拦截在后端——直接打 API 必须 403
  const token = await page.evaluate(() => localStorage.getItem("grc.token"));
  const denied = await request.get("http://localhost:8000/api/settings/providers", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(denied.status()).toBe(403);
});
