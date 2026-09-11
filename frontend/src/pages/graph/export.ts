/**
 * 导出前必须把 var(--token) 换成字面色值。
 * 序列化出去的 SVG 在浏览器外没有 CSS 变量，不换颜色会全丢。
 */
const COLOR_ATTRIBUTES = ["fill", "stroke"] as const;

export function serializeSvg(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const originals = [svg, ...Array.from(svg.querySelectorAll("*"))];
  const copies = [clone, ...Array.from(clone.querySelectorAll("*"))];

  copies.forEach((node, index) => {
    const computed = window.getComputedStyle(originals[index] as Element);
    for (const attribute of COLOR_ATTRIBUTES) {
      const value = node.getAttribute(attribute);
      if (value && value.includes("var(")) {
        node.setAttribute(attribute, computed.getPropertyValue(attribute));
      }
    }
    const inline = (node as HTMLElement).getAttribute("style");
    if (inline && inline.includes("var(")) {
      (node as HTMLElement).setAttribute("style", inline.replace(/var\([^)]*\)/g, "transparent"));
    }
  });

  const background = window.getComputedStyle(svg).backgroundColor;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("style", `background:${background}`);
  return new XMLSerializer().serializeToString(clone);
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function downloadGraph(svg: SVGSVGElement, format: "svg" | "png"): Promise<void> {
  const markup = serializeSvg(svg);
  if (format === "svg") {
    triggerDownload(new Blob([markup], { type: "image/svg+xml" }), "graph.svg");
    return;
  }

  const viewBox = (svg.getAttribute("viewBox") ?? "0 0 960 560").split(" ").map(Number);
  const width = viewBox[2];
  const height = viewBox[3];
  const source = URL.createObjectURL(new Blob([markup], { type: "image/svg+xml" }));
  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("SVG 渲染失败"));
      image.src = source;
    });
    const canvas = document.createElement("canvas");
    canvas.width = width * 2; // 2 倍图，截图进幻灯片不糊
    canvas.height = height * 2;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("canvas 不可用");
    context.scale(2, 2);
    context.drawImage(image, 0, 0, width, height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
    if (blob) triggerDownload(blob, "graph.png");
  } finally {
    URL.revokeObjectURL(source);
  }
}
