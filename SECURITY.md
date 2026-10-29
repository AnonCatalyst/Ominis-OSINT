# Security policy

Ominis-OSINT is a small, dependency-light tool that runs on your own machine.
We take reports about the code, the package and the release artefacts
seriously.

## Supported versions

| Version | Supported |
| --- | --- |
| `1.x` (current) | Yes |
| `0.5.x` (legacy) | Security fixes only |
| Older tags | No |

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Use GitHub's private reporting flow:

1. Open the **Security** tab of this repository.
2. Choose **Report a vulnerability**.
3. Include the affected version or commit, a description, and a minimal
   reproduction (command, input and observed output).

If you cannot use GitHub, write to <support@wintergate.org>. Encrypting the
message is welcome but not required. Never include live API keys, proxy
credentials or personal data in a report; redact them.

## What to expect

- We aim to acknowledge a report within 5 working days.
- We will confirm the issue, agree a disclosure date, and credit you unless you
  prefer to stay anonymous.
- Fixes ship in a normal release. Release bundles are unsigned; we publish
  SHA-256 digests and never claim a signature we do not have.

## Out of scope

- Findings that require a modified local build or a compromised machine.
- Rate limits, CAPTCHAs or blocks applied by third-party search engines.
- The legality of how you use the tool. Ominis only queries public pages; you
  remain responsible for lawful use and for respecting each site's terms.
- Missing hardening headers on a static README or documentation page.

## Safe contribution rules

- Never commit API keys, tokens, cookies, proxy lists or personal data.
- Keep proxies **off by default**. A change that turns them on implicitly will
  be rejected.
- Keep the runtime dependencies to the ones listed in `requirements.txt`; the
  test-only packages live in `requirements-test.txt`.
- Reporters and contributors are expected to follow `CODE_OF_CONDUCT.md`.
