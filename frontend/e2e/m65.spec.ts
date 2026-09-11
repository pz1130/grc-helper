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
    if (url.pathname === "/api/controls/1") return route.fulfill({ json: {
      id: 1, code: "C-0001", title: "CAB approval", statement: "Changes must be approved by the CAB.",
      category: null, owner_user_id: null, status: "active", created_at: "2026-09-01T00:00:00Z",
      sources: [{ clause_id: 91, document_id: 3, document_title: "Change Management Procedure", citation_label: "4.2", heading_path: "Change › Approval", relation: "defines" }],
      relations: [], mappings: [], implementations: [], evidence: [],
    } });
    if (url.pathname === "/api/clauses/91") return route.fulfill({ json: {
      id: 91, document_id: 3, document_title: "Change Management Procedure", number: "4.2",
      heading: "Approval", heading_path: "Change › Approval", citation_label: "4.2",
      text: "All normal changes are approved by the CAB before implementation.", level: 2, page_ref: 7,
    } });
    if (url.pathname === "/api/graph/relations") {
      if (url.searchParams.get("include_pending") === "true") {
        return route.fulfill({ json: {
          ...relationGraph,
          nodes: relationGraph.nodes.map((node) => node.key === "control:3" ? { ...node, pending_edges: 1 } : node),
          edges: [
            ...relationGraph.edges,
            { key: "proposal:31", source: "control:1", target: "control:3", kind: "depends_on", status: "pending", confidence: 0.8, rationale: "model said so", proposal_id: 31 },
          ],
          stats: { nodes: 3, edges: 3, pending_edges: 1, truncated: false },
        } });
      }
      return route.fulfill({ json: relationGraph });
    }
    if (url.pathname === "/api/graph/mappings") return route.fulfill({ json: {
      nodes: [
        { key: "control:1", kind: "control", code: "C-0001", title: "CAB approval", group: null, group_extra: [], functions: [], pending_edges: 0, is_gap: false },
        { key: "item:100", kind: "framework_item", code: "GV.PO-01", title: "Policy", group: null, group_extra: [], functions: [], pending_edges: 0, is_gap: false },
        { key: "item:200", kind: "framework_item", code: "PR.AA-01", title: "Access", group: null, group_extra: [], functions: [], pending_edges: 0, is_gap: true },
      ],
      edges: [
        { key: "mapping:5", source: "control:1", target: "item:100", kind: "full", status: "confirmed", confidence: 0.9, rationale: "covers it", proposal_id: null },
      ],
      groups: [],
      stats: { nodes: 3, edges: 1, pending_edges: 0, truncated: false },
    } });
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
  await expect(page.getByRole("list").getByText("Change Management Procedure")).toBeVisible();
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

test("clicking a node opens a drawer with the source clause text", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");

  await page.locator('[data-node-key="control:1"]').click();

  const drawer = page.getByRole("complementary", { name: "Details" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("C-0001")).toBeVisible();
  await expect(drawer.getByText("Changes must be approved by the CAB.")).toBeVisible();
  await expect(drawer.getByText("4.2")).toBeVisible();
  await expect(
    drawer.getByText("All normal changes are approved by the CAB before implementation."),
  ).toBeVisible();
  await expect(drawer.getByRole("link", { name: "Open in document" })).toHaveAttribute(
    "href",
    "/documents/3#clause-91",
  );
});

test("clicking an edge shows the model's rationale", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");

  await page.locator('[data-edge-key="relation:11"]').click();

  const drawer = page.getByRole("complementary", { name: "Details" });
  await expect(drawer.getByText("approval precedes rollback")).toBeVisible();
  await expect(drawer.getByText("0.90")).toBeVisible();
});

test("focus and hop count travel to the API", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");

  const requested = page.waitForRequest((request) => {
    if (!request.url().includes("/api/graph/relations?")) return false;
    const url = new URL(request.url());
    return url.searchParams.get("focus") === "control:1" && url.searchParams.get("hops") === "2";
  });
  await page.getByLabel("Focus").selectOption("control:1");
  await page.getByLabel("Hops").selectOption("2");
  const url = new URL((await requested).url());
  expect(url.searchParams.get("hops")).toBe("2");
});

test("pending edges are dashed and counted apart from confirmed ones", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");

  await page.getByLabel("Show pending proposals").check();

  await expect(page.locator('[data-edge-key="proposal:31"]')).toHaveAttribute("data-status", "pending");
  await expect(page.locator('[data-edge-key="proposal:31"]')).toHaveAttribute("stroke-dasharray", "5 4");
  await expect(page.getByText("1 pending")).toBeVisible();
});

test("only-unconfirmed hides the confirmed edges without another request", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");
  await page.getByLabel("Show pending proposals").check();
  await expect(page.locator("[data-edge-key]")).toHaveCount(3);

  await page.getByLabel("Only unconfirmed").check();

  await expect(page.locator("[data-edge-key]")).toHaveCount(1);
  await expect(page.locator('[data-edge-key="proposal:31"]')).toBeVisible();
});

test("conflicts-only narrows the requested relation types", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");

  const requested = page.waitForRequest((request) => request.url().includes("types=conflicts_with"));
  await page.getByLabel("Only conflicts").check();
  await requested;
});

test("the mapping view puts controls and framework items in two columns and flags gaps", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");

  await page.getByRole("button", { name: "Framework mapping" }).click();

  await expect(page.locator('[data-node-key="item:200"]')).toHaveAttribute("data-gap", "true");
  await expect(page.locator('[data-node-key="item:100"]')).toHaveAttribute("data-gap", "false");
  const x = async (key: string) => {
    const transform = await page.locator(`[data-node-key="${key}"]`).getAttribute("transform");
    return Number(transform!.match(/translate\((-?\d+(?:\.\d+)?)/)![1]);
  };
  expect(await x("control:1")).toBeLessThan(await x("item:100"));
  expect(await x("item:100")).toBe(await x("item:200"));
  await expect(page.getByText("1 gap")).toBeVisible();
});

test("the layout buttons are gone in the mapping view", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");
  await page.getByRole("button", { name: "Framework mapping" }).click();

  await expect(page.getByRole("button", { name: "Force" })).toHaveCount(0);
});

test("panorama thins labels down to the busiest nodes", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");

  // 三个节点里 control:2 度数最高（两条边），标签上限设为 1 时只剩它带标签。
  await page.getByLabel("Thin labels").check();

  await expect(page.locator("[data-node-label]")).toHaveCount(1);
  await expect(page.locator("[data-node-label]")).toHaveText("C-0002");
});

test("exporting produces an svg file with literal colours", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export SVG" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("graph.svg");

  const stream = await file.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(chunk as Buffer);
  const content = Buffer.concat(chunks).toString("utf8");
  expect(content).toContain("<svg");
  expect(content).not.toContain("var(--");
});

test("exporting png triggers a download", async ({ page }) => {
  await mockGraph(page);
  await page.goto("/graph");

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export PNG" }).click();
  expect((await download).suggestedFilename()).toBe("graph.png");
});
