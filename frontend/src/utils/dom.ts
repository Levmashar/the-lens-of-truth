export function element<K extends keyof HTMLElementTagNameMap>(
  tag: K, className = "", content?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

export function append(parent: HTMLElement, ...children: (Node | null | undefined)[]): void {
  for (const child of children) if (child) parent.append(child);
}

export function labeledValue(label: string, value: string): HTMLElement {
  const item = element("div", "meta-item");
  append(item, element("dt", "meta-label", label), element("dd", "meta-value", value));
  return item;
}

export function clear(node: HTMLElement): void { node.replaceChildren(); }

export function safeExternalUrl(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch { return null; }
}
