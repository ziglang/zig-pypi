Zig PyPI distribution
=====================

This repository contains the script used to repackage the [releases][zigdl] of the [Zig programming language][zig] as [Python binary wheels][wheel]. This document is intended for maintainers; see the [package README][pkgreadme] for rationale and usage instructions.

The repackaged artifacts are published as the [ziglang PyPI package][pypi].

[zig]: https://ziglang.org/
[zigdl]: https://ziglang.org/download/
[wheel]: https://github.com/pypa/wheel
[pkgreadme]: README.pypi.md
[pypi]: https://pypi.org/project/ziglang/

Preparation
-----------

The script requires Python 3.8 or later and [PDM](https://pdm.fming.dev/latest/#installation).

Install the dependencies:

```shell
pdm install
```

Building wheels
---------------

Run the repackaging script:

```shell
$ pdm run make_wheels.py --help
usage: make_wheels.py [-h] [--version VERSION] [--suffix SUFFIX] [--outdir OUTDIR]
                                                  [--platform {x86_64-windows,x86_64-macos,aarch64-macos,i386-linux,x86-linux,x86_64-linux,aarch64-linux,armv7a-linux}]

Repackage official Zig downloads as Python wheels

options:
  -h, --help            show this help message and exit
  --version VERSION     version to package, use `latest` for latest release, `master` for nightly build
  --suffix SUFFIX       wheel version suffix
  --outdir OUTDIR       target directory
  --platform {x86_64-windows,x86_64-macos,aarch64-macos,i386-linux,x86-linux,x86_64-linux,aarch64-linux,armv7a-linux}
                        platform to build for, can be repeated
```

This command will download the Zig release archives for every supported platform and convert them to binary wheels, which are placed under `dist/`. The Zig version and platforms can be passed as arguments.

The process of converting release archives to binary wheels is deterministic, and the output of the script should be bit-for-bit identical regardless of the environment and platform it runs under. To this end, it prints the SHA256 hashes of inputs and outputs; the hashes of the inputs will match the ones on the [Zig downloads page][zigdl], and the hashes of the outputs will match the ones on the [PyPI downloads page][pypidl].

[pypidl]: https://pypi.org/project/ziglang/#files

Uploading wheels to PyPI
------------------------

Trigger the publishing workflow from this repository manually (requires authorization)
with the necessary inputs as mentioned in the [workflow file](.github/workflows/cd.yml)
or in the GitHub Actions UI. The wheels are checked with `twine` before they are uploaded.

The workflow will upload the wheels to PyPI to make them available for installation. It
is possible to trigger it multiple times to upload wheels for different versions or
platforms.

Verifying the provenance of wheels uploaded to PyPI
---------------------------------------------------

To establish build provenance, the workflow generates attestations for the uploaded wheels
using the [GitHub Actions Attestations feature](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds)
when it is run. Please navigate to the [Attestations interface](https://github.com/ziglang/zig-pypi/attestations)
to view the attestations for the uploaded wheels.

The attestations may be verified via the [GitHub (`gh`) CLI](https://cli.github.com/manual/gh_attestation_verify)
or via the [GitHub API](https://docs.github.com/en/rest/users/attestations).

License
-------

This script is distributed under the terms of the [MIT (Expat) license](LICENSE.txt).
