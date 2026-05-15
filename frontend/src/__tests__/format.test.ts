import { formatDate, formatDateTime } from "@/lib/format";

describe("formatDate", () => {
  it("returns a readable date string in Russian locale", () => {
    const result = formatDate("2024-03-15T10:30:00Z");
    // Should contain the day and year
    expect(result).toMatch(/15/);
    expect(result).toMatch(/2024/);
  });

  it("does not include time", () => {
    const result = formatDate("2024-03-15T10:30:00Z");
    expect(result).not.toMatch(/10:30/);
    expect(result).not.toMatch(/:/);
  });

  it("handles different months", () => {
    const jan = formatDate("2024-01-01T00:00:00Z");
    const dec = formatDate("2024-12-01T00:00:00Z");
    expect(jan).not.toBe(dec);
  });
});

describe("formatDateTime", () => {
  it("returns a string containing both date and time parts", () => {
    // Use a fixed UTC date; toLocaleString shifts to local tz, so just check structure
    const result = formatDateTime("2024-03-15T12:00:00Z");
    expect(result).toMatch(/2024/);
    expect(result).toMatch(/:/);
  });

  it("includes year and day", () => {
    const result = formatDateTime("2024-06-20T08:05:00Z");
    expect(result).toMatch(/2024/);
    expect(result).toMatch(/20/);
  });
});
