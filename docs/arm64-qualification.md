# Linux ARM64 qualification

Release audit: 2026-11-26. Linux ARM64 is not qualified for this package.
The Dockerfile rejects non-amd64 builds before downloading its executable.

## Executable and dependency chain

- The Dockerfile retains [Action Server 1.2.2](https://github.com/joshyorko/actions/releases/tag/action-server-v1.2.2).
  Its `action-server-linux64` is an x86-64 ELF, SHA-256
  `5fbd23582d003651b617be2518fccfd4865d71a495cf376709a90f36df15c880`.
  Its [RCC downloader](https://github.com/joshyorko/actions/blob/action-server-v1.2.2/action_server/src/sema4ai/action_server/_download_rcc.py)
  pins RCC 18.16.0. The macOS ARM64 executable is not a Linux executable.
- [Actions Runtime 1.1.1](https://github.com/joshyorko/actions/releases/tag/actions-runtime-1.1.1)
  publishes Linux x64, macOS ARM64 and Windows x64 executables. Its
  [binary workflow](https://github.com/joshyorko/actions/blob/actions-runtime-1.1.1/.github/workflows/actions_runtime_binary_release.yml)
  has Ubuntu 22.04, Windows 2022 and macOS 26 lanes, without Linux ARM64.
  Its [downloader](https://github.com/joshyorko/actions/blob/actions-runtime-1.1.1/action_server/src/actions/server/_download_rcc.py)
  pins RCC 18.19.8 and selects `rcc-linux64` for 64-bit Linux, including aarch64.
- [RCC 18.19.11](https://github.com/joshyorko/rcc/releases/tag/v18.19.11)
  publishes Linux x64, macOS x64/ARM64 and Windows x64. The
  [build workflow](https://github.com/joshyorko/rcc/blob/v18.19.11/.github/workflows/rcc.yaml)
  exports those targets, without Linux ARM64.
  It [embeds](https://github.com/joshyorko/rcc/blob/v18.19.11/blobs/micromamba_linux.go)
  the Linux amd64 micromamba executable. Its [micromamba pin and provenance](https://github.com/joshyorko/rcc/blob/v18.19.11/docs/micromamba.md)
  are 2.10.0, release build `2.10.0-0`; the build bootstrap uses
  `https://micro.mamba.pm/api/micromamba/linux-64/2.10.0` with pinned digests
  and an official GitHub fallback. It does not select `linux-aarch64`.
  RCC 18.19.8 instead pins micromamba 2.5.0; installing a newer standalone
  micromamba does not replace either RCC's embedded dependency.

## What micromamba proves

The [official 2.10.0-0 release](https://github.com/mamba-org/micromamba-releases/releases/tag/2.10.0-0)
includes `micromamba-linux-aarch64`. Its executable SHA-256 is
`3bb56786e21b9b24024f599fe9185b4a59dc3f9f59937a42311ee583adbbb23c`.
Checksum verification, aarch64 ELF inspection and native `--version` execution
passed on a 64-bit Raspberry Pi 5. This proves binary execution only, not conda
solving, RCC robots, Action Server import, or browser automation.

## Remaining gates

The smallest missing released layer is native Linux ARM64 RCC with the matching
embedded micromamba and architecture routing. A Python wheel can avoid a frozen
Action Server executable, but does not automatically replace its bundled RCC or
downloader. An amd64 container under emulation is not native qualification.

After an exact candidate is available, qualify a minimal RCC robot and a minimal
Action Server package import/run using isolated temporary homes. Bind fixtures
only to loopback and clean them up. Then resolve every pinned conda/PyPI package
in `package.yaml` on aarch64, install Chromium with its system libraries, and run
a synthetic browser fixture. A successful wheel install or CLI help is insufficient.
No live login or application is part of these checks.

## Offline safety smoke

`uv run --no-project --with actions-core==1.1.0 python tests/test_submission_disabled.py`
executes all five rejection paths using real pinned response models. It isolates
function bodies from module imports, so it proves early rejection without browser,
database or network dependencies; it does not qualify full package imports.
