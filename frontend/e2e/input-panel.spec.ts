import { expect, test } from "@playwright/test";

const realSupabaseConfigured = Boolean(
  process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
);

test.describe("input panel", () => {
  test.beforeEach(() => {
    test.skip(!realSupabaseConfigured, "Requires authenticated local Supabase session.");
  });

  test("switches between Template, Code, and Math tabs", async ({ page }) => {
    await page.goto("/new");
    await expect(page.getByRole("tab", { name: "Template" })).toBeVisible();
    await page.getByRole("tab", { name: "Code" }).click();
    await expect(page.getByText("NumPy source")).toBeVisible();
    await page.getByRole("tab", { name: "Math" }).click();
    await expect(page.getByText("Math builder")).toBeVisible();
  });

  test("template selection shows a selected template preview", async ({ page }) => {
    await page.goto("/new");
    await page.getByRole("button", { name: /Portfolio/i }).click();
    await expect(page.getByText('"input_source": "template"')).toBeVisible();
  });

  test("code validation shows extracted IR", async ({ page }) => {
    await page.goto("/new");
    await page.getByRole("tab", { name: "Code" }).click();
    await page.getByRole("button", { name: "Validate" }).click();
    await expect(page.getByText("Extracted IR")).toBeVisible();
  });

  test("run button explains disabled state before code validation", async ({ page }) => {
    await page.goto("/new");
    await page.getByRole("tab", { name: "Code" }).click();
    await expect(page.getByRole("button", { name: "Run pipeline" })).toBeDisabled();
  });
});
