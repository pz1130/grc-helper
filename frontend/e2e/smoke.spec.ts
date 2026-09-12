import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const ADMIN = { email: "admin@example.com", password: "pw123456" };
const SECRET = "sk-e2e-supersecret-value";
const PROVIDER_NAME = `e2e-${Date.now()}`;
// 后端直连地址：`make e2e` 把整套栈开在另一组端口上，别写死 8000。
const API = process.env.E2E_API_BASE ?? "http://localhost:8000";

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
  // 语言切换在改造后是「可见的分段按钮 + 隐藏的原生 select」，两者同名，
  // getByLabel 会命中两个。按 combobox 角色取那个 select——它正是为可驱动性留的。
  await page.getByRole("combobox", { name: "语言" }).selectOption("en");
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

  // 停用与删除都在这一行上。删除走两步，误点一下不会真的没了。
  await row.getByRole("button", { name: "停用" }).click();
  await expect(row.getByRole("button", { name: "启用" })).toBeVisible();
  await row.getByRole("button", { name: "删除" }).click();
  await row.getByRole("button", { name: "确认删除" }).click();
  await expect(row).toHaveCount(0);
  // 这张表此前只进不出：每跑一次冒烟就留一行。现在用例自己收尾。
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
  const denied = await request.get(`${API}/api/settings/providers`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(denied.status()).toBe(403);
});

test("侧栏导航再长，退出按钮也留在视口里", async ({ page }) => {
  await signIn(page);

  // 导航项每加一个就把底部的退出/主题/语言往下顶。侧栏本身必须能滚，
  // 否则 720 高的屏幕上这些控件直接够不着——2026-09-11 图谱项就顶出去过一次。
  const box = await page.getByRole("button", { name: "退出" }).boundingBox();
  const viewport = page.viewportSize()!;
  expect(box).not.toBeNull();
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height);
});
