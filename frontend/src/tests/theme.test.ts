// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createThemeToggle } from "../components/themeToggle";

let dispose: (() => void) | null = null;
let systemChange: ((event: MediaQueryListEvent) => void) | undefined;

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  systemChange = undefined;
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true,
    addEventListener: vi.fn((_type, callback) => { systemChange = callback; }),
    removeEventListener: vi.fn(),
  })));
});
afterEach(() => { dispose?.(); dispose = null; vi.unstubAllGlobals(); });

describe("theme preferences", () => {
  it("follows the system until a choice is made, then remembers it", () => {
    const toggle = createThemeToggle();
    dispose = toggle.dispose;
    expect(document.documentElement.dataset.theme).toBe("dark");
    systemChange?.({ matches: false } as MediaQueryListEvent);
    expect(document.documentElement.dataset.theme).toBe("light");
    toggle.node.click();
    expect(localStorage.getItem("lens-theme")).toBe("dark");
    expect(toggle.node.getAttribute("aria-pressed")).toBe("true");
    expect(toggle.node.getAttribute("aria-label")).toBe("Switch to light mode");
    systemChange?.({ matches: false } as MediaQueryListEvent);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("restores a saved choice instead of overriding it with the system", () => {
    localStorage.setItem("lens-theme", "light");
    const toggle = createThemeToggle();
    dispose = toggle.dispose;
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(toggle.node.getAttribute("aria-label")).toBe("Switch to dark mode");
  });

  it("still switches when preference storage is blocked", () => {
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    try {
      const toggle = createThemeToggle();
      dispose = toggle.dispose;
      expect(() => toggle.node.click()).not.toThrow();
      expect(document.documentElement.dataset.theme).toBe("light");
    } finally { get.mockRestore(); set.mockRestore(); }
  });
});
