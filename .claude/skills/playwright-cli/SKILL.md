---
name: playwright-cli
description: >-
  Runbook for Playwright CLI: driving the Vite frontend + Flask API for E2E tests, screenshots, traces and
  codegen. Use to verify UI changes in a real browser.
---

# Playwright CLI

Playwright is not a project dependency yet; install it dev-only in `frontend/` when needed:
```
cd frontend
npm i -D @playwright/test
npx playwright install chromium
```
(Browser download is a one-time setup step, outside the offline runtime of the app.)

## Start the stack
```
# terminal 1 (set APP_PORT if 5000 is taken)
backend/venv/Scripts/python.exe backend/app.py
# terminal 2
cd frontend && npm run dev          # http://localhost:5173
```
Use `webServer` in `playwright.config.ts` to start both automatically and `reuseExistingServer: true`.

## Commands
- `npx playwright test` run all; `--headed`, `--ui`, `--debug`, `-g "name"`, `--project=chromium`.
- `npx playwright codegen http://localhost:5173` record a flow.
- `npx playwright show-report` / `show-trace trace.zip` inspect failures.
- Screenshot: `npx playwright screenshot --viewport-size=1440,900 http://localhost:5173 out.png`.

## Config essentials
`use: { baseURL, trace: 'on-first-retry', screenshot: 'only-on-failure' }`; viewports 360x800 and 1440x900; `colorScheme: 'dark'` project too; `reducedMotion: 'reduce'` for stable screenshots.

## Writing tests
- Locators by role/label/text: `getByRole('button', { name: 'Run scan' })`; no CSS/XPath unless unavoidable.
- Upload with `setInputFiles` using `samples/` fixtures (`sample_a.txt`, `sample_b.txt`, `sample_code_a.py`, `sample_code_b.py`).
- Assert on web-first conditions (`expect(locator).toBeVisible()`); no `waitForTimeout`.
- Key flows: upload two files -> results ranked -> open inspector -> highlights present; reject >10 MB / wrong extension; API down -> status pill + error state; threshold slider re-flags without a new request; reopen from history.
- Accessibility: `@axe-core/playwright` optional.

## Hygiene
Keep test artefacts (`test-results/`, `playwright-report/`) out of git. Tests must not hit external hosts.
