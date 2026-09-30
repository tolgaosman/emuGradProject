---
name: code-review
description: >-
  Apply this skill to perform a systematic, rigorous code review of PRs or newly written code, 
  checking for performance, security, style, and logic.
---

# Systematic Code Review

Perform a thorough analysis of code changes.

## Review Checklist
1. **Security**: Are there any new injection vectors? Is user input sanitized? Are dependencies secure?
2. **Performance**: Will this change degrade performance at scale? Are there N+1 query problems or expensive synchronous operations?
3. **Readability**: Is the code easy to understand? Are variable names clear? Is complex logic documented?
4. **Testing**: Are there sufficient unit and integration tests for this change? Do tests cover edge cases and failure modes?
5. **Architecture**: Does this change align with the overall system architecture? Is it introducing technical debt?
