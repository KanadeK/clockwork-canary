# Clockwork Canary v0.1.1

This portability release keeps the v0.1.0 analyzer behavior and closes the final cross-machine reproducibility gap found by downloading the first public assets.

Changes:

- JSON reports now use the stable repository-root label `.` instead of exposing a checkout-specific absolute path;
- setuptools, wheel, and the build frontend are pinned so package metadata is identical on Windows and Linux;
- sdist and wheel ownership, permissions, timestamps, ordering, and ZIP metadata remain normalized;
- official GitHub workflow dependencies are current at v7;
- the full 62-test suite, branch coverage gate, clean install, Action smoke, and CodeQL remain required.

Verify both artifacts against `SHA256SUMS` or `release-manifest.json` before installation.
