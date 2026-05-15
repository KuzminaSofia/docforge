import { cn } from "@/lib/utils";

describe("cn", () => {
  it("merges class strings", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("deduplicates conflicting tailwind classes (last wins)", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("ignores falsy values", () => {
    expect(cn("foo", false, undefined, null, "bar")).toBe("foo bar");
  });

  it("supports conditional objects", () => {
    expect(cn("base", { active: true, disabled: false })).toBe("base active");
  });

  it("returns empty string for no arguments", () => {
    expect(cn()).toBe("");
  });
});
