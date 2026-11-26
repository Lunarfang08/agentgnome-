import { test, expect } from "@playwright/test";

test("authentication rejects an invalid token", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Access token").fill("invalid-token");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Invalid credentials" }),
  ).toBeVisible();
});

test("publish, execute, approve and inspect real persisted result", async ({
  page,
}) => {
  const token = process.env.AG_DEV_TOKEN;
  if (!token)
    throw new Error("AG_DEV_TOKEN is required for local browser verification");
  await page.goto("/");
  await page.getByLabel("Access token").fill(token);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Run explorer" }),
  ).toBeVisible();
  const runLinks = () => page.getByRole("link", { name: "Inspect trace" });
  const oldLinks = new Set(
    await runLinks().evaluateAll((links) =>
      links.map((a) => a.getAttribute("href")),
    ),
  );
  await page
    .getByRole("button", { name: "Publish genome and start run" })
    .click();
  const newLinks = async () =>
    (
      await runLinks().evaluateAll((links) =>
        links.map((a) => a.getAttribute("href")),
      )
    ).filter((href): href is string => href !== null && !oldLinks.has(href));
  await expect.poll(newLinks).toHaveLength(1);
  const id = (await newLinks())[0].split("/").pop()!;
  await expect
    .poll(
      async () => {
        await page.reload();
        await page.getByRole("heading", { name: "Run explorer" }).waitFor();
        return page
          .locator("article")
          .filter({ hasText: id })
          .getByRole("button", { name: "Approve simulated order" })
          .count();
      },
      { timeout: 30000 },
    )
    .toBeGreaterThan(0);
  await page
    .locator("article")
    .filter({ hasText: id })
    .getByRole("button", { name: "Approve simulated order" })
    .click();
  await expect
    .poll(
      async () => {
        await page.reload();
        await page.getByRole("heading", { name: "Run explorer" }).waitFor();
        return page
          .getByRole("row")
          .filter({ hasText: id })
          .getByText("SUCCEEDED", { exact: true })
          .count();
      },
      { timeout: 30000 },
    )
    .toBeGreaterThan(0);
  await page.screenshot({
    path: test.info().outputPath("studio.png"),
    fullPage: true,
  });
  if (process.env.AG_UPDATE_SCREENSHOTS === "1") {
    await page.screenshot({ path: "../../docs/screenshots/studio.png" });
  }
  await page
    .getByRole("row")
    .filter({ hasText: id })
    .getByRole("link", { name: "Inspect trace" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Persisted checkpoint" }),
  ).toBeVisible();
  await expect(
    page.getByText(/Approved simulated purchase order submitted once/),
  ).toBeVisible();
  if (process.env.AG_UPDATE_SCREENSHOTS === "1") {
    await page.screenshot({
      path: "../../docs/screenshots/run-evidence.png",
      fullPage: true,
    });
  }
});

test("dashboard sends security headers and exposes liveness", async ({
  request,
}) => {
  const response = await request.get("/healthz");
  expect(response.ok()).toBeTruthy();
  expect(await response.json()).toEqual({ status: "alive" });
  expect(response.headers()["x-frame-options"]).toBe("DENY");
  expect(response.headers()["x-content-type-options"]).toBe("nosniff");
  expect(response.headers()["content-security-policy"]).toContain(
    "frame-ancestors 'none'",
  );
  expect(response.headers()["x-powered-by"]).toBeUndefined();
});
