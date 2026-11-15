# Komboe marketing site (komboe.com) — STAGING ONLY

Static site (no build step required; `python3 build.py` regenerates the HTML from one template). Serve with any static host: `python3 -m http.server`.

Pages: Home, Features, Security, Pricing (placeholder prices), Downloads (`/downloads`, generated from `distribution/komboe-downloads.json` with version, size, SHA-256, release date, and install notes), Log in, Sign up.

Branding: padlock-K logo from `branding/logo` (shape untouched, color variant only), Sora font (OFL), every password field has a show/hide toggle.

## Accounts: one Komboe account
The home page sign-in form uses the same server flow as the web vault: prelogin, a local password hash, `/identity/connect/token`, and a two-step code when the account has one. A correct sign-in opens `/vault`, which loads the account from the server. A signed-in visitor sees Open dashboard instead of the form. Create account stays on `signup.html`. The master password is not stored on this site.

Serve with CSP headers: `python3 serve.py --api http://127.0.0.1:8080`. `/downloads` is the downloads page; `/downloads.html` redirects there. Mount release files with `KOMBOE_DOWNLOADS_DIR` (or `--downloads-dir`) so `android/latest.json` and APKs are served from the same origin. The end-to-end check is `bash e2e/run.sh`.

## SEO
Per-page title/description/canonical/OG/Twitter, JSON-LD (Organization, SoftwareApplication with Free offer only, FAQPage, BreadcrumbList), sitemap.xml, robots.txt, 404.html, hreflang en + x-default.
Build for staging (default): `python3 build.py` → noindex + robots `Disallow: /`. Production: `KOMBOE_ENV=production python3 build.py`.

Production deploy is the `marketing` service in `deploy/coolify/docker-compose.pull.yml`. Richard routes `/downloads*` on komboe.com to that service (port 4173) and copies the publish tree into the `komboe-downloads` volume at `/var/komboe-downloads`. Do not create a downloads.komboe.com DNS record. Build the site with `KOMBOE_ENV=production python3 build.py`. Publish new files with `python3 scripts/publish-downloads.py`.
