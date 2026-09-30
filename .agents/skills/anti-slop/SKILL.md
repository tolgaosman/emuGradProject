---
name: anti-slop
description: >-
  Use this skill to aggressively prevent and eliminate lazy coding habits, spaghetti code, 
  and "hacky" workarounds.
---

# Anti-Slop Enforcement

Prevent the degradation of the codebase by enforcing strict discipline.

## Rules of Anti-Slop
1. **No Dead Code**: Remove unused imports, variables, and commented-out code blocks immediately.
2. **No Magic Numbers**: Extract all literal numbers and strings into well-named constants.
3. **No `any` Types**: In TypeScript or typed languages, using `any` is strictly forbidden. Use `unknown` if the type is truly unknown, and narrow it with type guards.
4. **No Deep Nesting**: Avoid arrow code. Return early to keep the happy path at the lowest possible indentation level.
5. **Refactor as You Go**: If you touch a messy file, apply the Boy Scout Rule and leave it cleaner than you found it.
