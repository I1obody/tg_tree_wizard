# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in `tg-tree-wizard`, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities.
2. Email the maintainer at the address associated with the repository, or use GitHub's private vulnerability reporting feature.
3. Include a description of the vulnerability, steps to reproduce, and potential impact.

We will acknowledge your report within 48 hours and work on a fix promptly. If the issue is confirmed, we will release a patch in a timely manner.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.x     | :white_check_mark: |
| 1.x     | :x:                |
| < 0.1   | :x:                |

Please upgrade to the latest version whenever possible. Security fixes are only applied to the current major line (2.x).

## What We Consider a Vulnerability

- Code execution via crafted `callback_data` or tree definitions
- State leakage between users through FSMContext
- Injection of arbitrary data into Telegram message content
- Bypassing callback_data length limits leading to unexpected behavior

## What We Do Not Consider a Vulnerability

- Using outdated Python versions (< 3.10)
- Misconfiguring the bot token or FSM storage
- Issues in upstream dependencies (report them to the respective maintainers)
