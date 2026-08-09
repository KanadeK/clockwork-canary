# Security policy

## Supported versions

The latest release receives security fixes. Version `0.1.x` is currently supported.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do not include real secrets, private workflow files, or proprietary logs in a public issue.

Include:

- the affected version and operating system;
- a minimal synthetic workflow that reproduces the problem;
- the expected and actual trust boundary;
- whether file disclosure, command execution, path traversal, or report injection is possible.

You should receive an initial response within seven days.

## Trust model

Clockwork Canary treats workflow YAML, policy JSON, paths, and Action inputs as untrusted data.

- Scans read workflow files but never execute workflow steps.
- YAML uses `SafeLoader` with a GitHub-specific resolver; arbitrary Python objects are not constructed.
- The composite Action moves `${{ inputs.* }}` into environment variables before the shell parses them.
- HTML is not emitted. Markdown, JSON, and SARIF preserve data as content rather than executable markup.
- `init --force` is the only intentional overwrite operation. `scan` writes only the explicit `--output` path.
- The tool makes no network requests and does not read GitHub credentials.
