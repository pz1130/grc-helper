import { expect, test } from "@playwright/test";

test("failed real login does not enter the demo session", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("grc.lang", "en"));
  await page.route("**/api/auth/login", (route) => route.fulfill({ status: 401, json: { message: "Invalid credentials" } }));
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("pw123456");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("grc.token"))).toBeNull();
});

test("offline demo remains an explicit option", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("grc.lang", "en"));
  await page.goto("/login");
  await page.getByRole("button", { name: "Enter demo" }).click();
  await expect(page).not.toHaveURL(/\/login$/);
  expect(await page.evaluate(() => localStorage.getItem("grc.token"))).toBe("demo-mock-token");
});
