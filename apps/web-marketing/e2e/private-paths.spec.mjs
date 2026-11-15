import { test, expect } from "@playwright/test";

const HIDDEN = [
  "/build.py",
  "/legal_copy.py",
  "/serve.py",
  "/e2e/run.sh",
  "/e2e/signin.spec.mjs",
  "/README.md",
  "/package.json",
  "/package-lock.json",
];

for (const hidden of HIDDEN) {
  test(`${hidden} is not served`, async ({ request }) => {
    const response = await request.get(hidden, { maxRedirects: 0 });
    expect(response.status()).toBe(404);
    const body = await response.text();
    expect(body).not.toMatch(/Bitwarden|bitwarden_license/);
  });
}

test("the home page is still served", async ({ request }) => {
  const response = await request.get("/");
  expect(response.status()).toBe(200);
});
