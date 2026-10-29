# Code signing

## Current status

Ominis-OSINT releases are **not code-signed**. The release bundles are source
archives plus a Python wheel. Python does not verify publisher signatures when
installing from a downloaded file, so SmartScreen or your browser may still show
an "unknown publisher" warning the first time you run an installer or extract an
archive.

That is expected, not a sign of tampering. Certificate authorities issue
publicly trusted code-signing certificates to verified organizations or
verified individuals. WinterGate Intelligence Collective is an independent,
privacy-first collective that has deliberately chosen not to incorporate as a
conventional company. That operating choice does not make the project less
legitimate or its authorship less real; it only means a CA cannot currently
issue an OV certificate in the collective's name. Self-signed certificates do
not help: Windows and Python do not trust them, and they can make the warning
worse.

## Verify what you downloaded

Every release publishes the SHA-256 of each bundle in three places:

1. the release notes;
2. the attached `SHA256SUMS.txt`;
3. the digest GitHub shows next to the release asset.

Check the file you downloaded:

```powershell
Get-FileHash .\Ominis-OSINT-<version>.zip -Algorithm SHA256
```

```sh
sha256sum -c SHA256SUMS.txt
```

The output must match the release digest exactly. If it does not, do not run the
file. Report it through [SECURITY.md](SECURITY.md) instead.

The most reliable check is to read the code and run the test suite:

```sh
python -m pip install -r requirements-test.txt
python -m pytest -q
```

## Why we do not use a self-signed certificate

A self-signed certificate only changes who is named in the signature; Windows
still cannot chain it to a trusted root, so SmartScreen still warns and may also
flag the file as invalidly signed. It would look more official while providing
no verification. We would rather stay unsigned and publish reproducible source,
hashes and the build instructions.

Note that since 2024, even EV certificates no longer skip SmartScreen entirely.
Any new certificate must build reputation through clean downloads.

## Path to signed releases

If the collective decides to form a signing entity, signing is a small,
well-defined change:

1. Form the entity the CA requires (or a sole-proprietor/DBA name, if the CA
   accepts it).
2. Buy an OV code-signing certificate (roughly **$120–350/year**; private key in
   a cloud HSM or FIPS 140-2 token; maximum validity is 460 days for
   certificates issued after March 2026).
3. Store the signing credentials in the CI secret store or the CA's cloud HSM.
   Never commit them and never add them as repository files.
4. Sign the built `.whl` and any installer with SHA-256 and an RFC 3161
   timestamp, then verify before publishing.
5. Update this file and the release notes. Do not describe a build as signed
   until verification succeeds on the artifacts that were uploaded.

## Free options and why they are not used

- **SignPath Foundation** issues the certificate to *SignPath Foundation*, so
  the publisher shown would be SignPath Foundation, not WinterGate. Their terms
  also exclude projects with proprietary or commercially dual-licensed
  components; the private Pro edition conflicts with that.
- **Certum's open-source / individual certificate** is issued to an individual's
  legal name and is restricted to non-commercial open source. It cannot carry
  the WinterGate name, and the Pro edition makes the non-commercial condition
  doubtful.

The public source, the test suite and the published hashes remain the
authoritative way to check what a release contains.
