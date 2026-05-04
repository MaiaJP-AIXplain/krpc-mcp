# Security Policy

## Supported Versions

This project is in pre-release. Only the **latest published version** receives security fixes.

| Version | Supported |
|---------|-----------|
| latest  | ✅        |
| older   | ❌        |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities by emailing **jmaia@aixplain.com** with:

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- Any suggested mitigation or fix

You can expect an acknowledgement within **48 hours** and a resolution timeline within **7 days** for critical issues.

We will coordinate disclosure timing with you. Public disclosure will not happen before a fix is available, unless you request otherwise.

## Scope

This MCP server connects to a locally-running kRPC server inside KSP. The primary attack surface is:

- The local network socket used to reach kRPC (default `127.0.0.1:50000`)
- Any environment variables or config files that store connection details

API keys and credentials should never be committed to the repository. If you discover such a leak, follow the reporting process above.
