import { expect, test } from "@playwright/test";

const realSupabaseConfigured = Boolean(
  process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
);

test.describe("auth flow", () => {
  test("accessing dashboard while logged out redirects to login", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login\?returnUrl=%2Fdashboard/);
  });

  test("login with wrong password shows error", async ({ page }) => {
    test.skip(!realSupabaseConfigured, "Requires local Supabase env vars.");
    await page.goto("/login");
    await page.getByLabel("Email").fill("wrong-password@example.com");
    await page.getByLabel("Password").fill("incorrect-password");
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page.getByText("Invalid email or password.")).toBeVisible();
  });

  test("signup with new email lands on dashboard", async ({ page }) => {
    test.skip(!realSupabaseConfigured, "Requires local Supabase env vars.");
    const marker = Date.now();
    await page.goto("/signup");
    await page.getByLabel("Email").fill(`qsim-e2e-${marker}@example.com`);
    await page.getByLabel("Password").fill("QsimE2ePassword99");
    await page.getByRole("button", { name: "Sign up" }).click();
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test("logout returns to landing", async ({ page }) => {
    test.skip(!realSupabaseConfigured, "Requires a seeded authenticated session.");
    await page.goto("/dashboard");
    await page.getByLabel("Open account menu").click();
    await page.getByText("Sign out").click();
    await expect(page).toHaveURL("/");
  });
});
