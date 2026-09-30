---
name: anthropic-security-audit
description: >-
  Perform rigorous security checks focusing on LLM integrations, prompt injection vulnerabilities, 
  and general web application security (OWASP).
---

# Anthropic Security Audit

## Audit Protocol
1. **Prompt Injection Defense**: Review all LLM prompts to ensure user input is isolated. Look for missing delimiters (e.g., `<user_input>`) and system prompt overrides.
2. **Data Leakage**: Ensure that sensitive PII or internal system architecture details are not leaked in error messages or LLM responses.
3. **Access Control**: Verify that all endpoints, especially those triggering AI actions, have robust authorization checks.
4. **Input Sanitization**: Check for XSS, SQLi, and command injection vulnerabilities in all user-facing inputs.
5. **Dependency Scanning**: Audit `package.json` or equivalent for known vulnerable packages.
