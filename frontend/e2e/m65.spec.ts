import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const relationGraph = {
  nodes: [
    { key: "control:1", kind: "control", code: "C-0001", title: "CAB approval", group: "document:3", group_extra: [], functions: ["GV"], pending_edges: 0, is_gap: false },
    { key: "control:2", kind: "control", code: "C-0002", title: "Rollback plan", group: "document:3", group_extra: [], functions: ["PR"], pending_edges: 0, is_gap: false },
    { key: "control:3", kind: "control", code: "C-0003", title: "Incident logging", group: "document:4", group_extra: [], functions: [], pending_edges: 0, is_gap: false },
  ],
  edges: [
    { key: "relation:11", source: "control:1", target: "control:2", kind: "depends_on", status: "confirmed", confidence: 0.9, rationale: "approval precedes rollback", proposal_id: null },
    { key: "relation:12", source: "control:2", target: "control:3", kind: "duplicates", status: "confirmed", confidence: 0.95, rationale: "same requirement", proposal_id: null },
  ],
  groups: [
    { key: "document:3", kind: "document", label: "Change Management Procedure" },
    { key: "document:4", kind: "document", label: "Incident Management Guideline" },
  ],
  stats: { nodes: 3, edges: 2, pending_edges: 0, truncated: false },
};

export async function mockGraph(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("grc.token", "mock-token");
    localStorage.setItem("grc.lang", "en");
  });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { id: 1, email: "lead@example.com", name: "Lead", role: "grc_lead" } });
    if (url.pathname === "/api/frameworks") return route.fulfill({ json: [{ id: 7, name_zh: "网络安全框架", name_en: "Cybersecurity Framework", version: "2.0" }] });
    if (url.pathname === "/api/documents") return route.fulfill({ json: [{ id: 3, title: "Change Management Procedure" }, { id: 4, title: "Incident Management Guideline" }] });
    if (url.pathname === "/api/controls") return route.fulfill({ json: [{ id: 1, code: "C-0001", title: "CAB approval" }, { id: 2, code: "C-0002", title: "Rollback plan" }, { id: 3, code: "C-0003", title: "Incident logging" }] });
    if (url.pathname === "/api/graph/relations") return route.fulfill({ json: relationGraph });
    return route.fulfill({ status: 500, json: { message: `Unexpected API: ${url.pathname}` } });
  });
}

test("the relation graph renders nodes and edges grouped by document", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");

  await expect(page.getByRole("heading", { name: "Graph" })).toBeVisible();
  await expect(page.locator("[data-node-key]")).toHaveCount(3);
  await expect(page.locator("[data-edge-key]")).toHaveCount(2);
  await expect(page.locator('[data-edge-key="relation:11"]')).toHaveAttribute("data-kind", "depends_on");
  await expect(page.locator('[data-edge-key="relation:11"]')).toHaveAttribute("data-status", "confirmed");
  await expect(page.getByText("3 nodes · 2 edges")).toBeVisible();
  await expect(page.getByText("Change Management Procedure")).toBeVisible();
});

test("nodes in the same document share a lane", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");

  const first = await page.locator('[data-node-key="control:1"]').getAttribute("transform");
  const second = await page.locator('[data-node-key="control:2"]').getAttribute("transform");
  const third = await page.locator('[data-node-key="control:3"]').getAttribute("transform");
  const x = (value: string | null) => value!.match(/translate\((-?\d+(?:\.\d+)?)/)![1];
  expect(x(first)).toBe(x(second));
  expect(x(first)).not.toBe(x(third));
});

test("grouping by function separates mapped controls from unmapped ones", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");
  await page.getByRole("button", { name: "By function" }).click();

  const x = async (key: string) => {
    const transform = await page.locator(`[data-node-key="${key}"]`).getAttribute("transform");
    return transform!.match(/translate\((-?\d+(?:\.\d+)?)/)![1];
  };
  // GV / PR / 未覆盖各一条泳道，三个节点两两不同列。
  expect(new Set([await x("control:1"), await x("control:2"), await x("control:3")]).size).toBe(3);
});

test("the force layout lands on the same coordinates every time", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");

  await page.getByRole("button", { name: "Force" }).click();
  const first = await page.locator("[data-node-key]").evaluateAll((nodes) =>
    nodes.map((node) => `${node.getAttribute("data-node-key")}@${node.getAttribute("transform")}`),
  );

  await page.getByRole("button", { name: "By document" }).click();
  await page.getByRole("button", { name: "Force" }).click();
  const second = await page.locator("[data-node-key]").evaluateAll((nodes) =>
    nodes.map((node) => `${node.getAttribute("data-node-key")}@${node.getAttribute("transform")}`),
  );

  expect(second).toEqual(first);

  await page.reload();
  await page.getByRole("button", { name: "Force" }).click();
  const third = await page.locator("[data-node-key]").evaluateAll((nodes) =>
    nodes.map((node) => `${node.getAttribute("data-node-key")}@${node.getAttribute("transform")}`),
  );
  expect(third).toEqual(first);
});
