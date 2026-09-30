---
name: security-guidance
description: >-
  General security practices covering OWASP Top 10 prevention, secure authentication flows, 
  encryption, and auditing.
---

# General Security Guidance

Ensure baseline security is never compromised.

## Key Directives
1. **Never Trust Input**: Validate all input on the server side, even if client-side validation exists.
2. **Authentication/Authorization**: Enforce least privilege. Ensure JWTs or session cookies are secure (HttpOnly, Secure, SameSite).
3. **Data Protection**: Encrypt sensitive data at rest and in transit (TLS 1.2+). Do not log passwords or PII.
4. **Error Handling**: Fail securely. Do not leak stack traces or internal system states in production error responses.
5. **Dependency Auditing**: Regularly check for and update vulnerable third-party packages.
