---
name: playwright-cli
description: >-
  Runbook for utilizing the Playwright CLI for End-to-End (E2E) testing, debugging, 
  and trace viewing.
---

# Playwright CLI Runbook

Effectively manage and execute E2E tests.

## Common Operations
1. **Running Tests**: 
   - `npx playwright test` (all tests)
   - `npx playwright test --ui` (open UI mode)
   - `npx playwright test --headed` (run visibly in browser)
2. **Debugging**: 
   - `npx playwright test --debug` (open Playwright inspector)
3. **Test Generation**: 
   - `npx playwright codegen <url>` (record interactions and generate test code)
4. **Trace Viewer**: 
   - `npx playwright show-trace trace.zip` (analyze test failures with full DOM snapshots and network logs)
5. **Best Practices**: Use user-facing locators (`getByRole`, `getByText`) instead of CSS selectors for resilient tests.
