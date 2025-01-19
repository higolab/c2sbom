# C2SBOM Preview (Proof-of-Concept)

This is an experimental, proof-of-concept version of C2SBOM to automatically generate an SPDX 2.3 Document for a C/C++ project in JSON format. These scripts construct [valid](https://tools.spdx.org/app/validate/) and [NTIA Minimum Elements Conformant](https://tools.spdx.org/app/ntia_checker/) SBOMs. This project comes with two distinct scripts:

- `build_sbom.py`: Reads output from build tools (`gcc`/`g++` and `ld`) and generates an SPDX document of build-time dependencies (i.e., compiled/linked into the resulting binaries).
  - Thus constructs a "Build SBOM" by the [CISA (Cybersecurity and Infrastructure Security Agency) definition](https://www.cisa.gov/sites/default/files/2023-04/sbom-types-document-508c.pdf)
- `analyzed_sbom.py`: Reads executable binaries and generates an SPDX document of run-time dependencies.
  - Thus constructs an "Analyzed SBOM" by the [CISA definition](https://www.cisa.gov/sites/default/files/2023-04/sbom-types-document-508c.pdf)

`build_sbom.py` needs output that is made with

- `-H` option enabled for `gcc`/`g++`, and
  - Header file dependencies will be excluded without this option
- `-t` option enabled for `ld` (or `-Wl,-t` option enabled for `gcc`/`g++`).
  - Library file dependencies will be excluded without this option

Make sure to include not only stdout but also stderr output.

## Requirements

- Debian-based Linux distribution (Debian, Ubuntu, Linux Mint, etc)
- Python 3.9 or later (tested until Python 3.12)

This PoC doesn't have any external dependencies and uses only standard libraries which are included in a default Python installation, so it should just run out of the box. Just download everything and invoke the one you want.

## Usage

`build_sbom.py`:

```
$ ./build_sbom.py -h
usage: build_sbom.py [-h] [-i INPUT] [-o OUTPUT] -p PROJECT -d DEVELOPER [-l LICENSE] -v VERSION [-c COPYRIGHT] [-u [USER ...]]

This script constructs an NTIA conforming SPDX 2.3 document (SBOM) of a C/C++ project through analyzing a build process. This is part of C2SBOM (Preview) from Software Engineering Laboratory, Osaka University. This project is still in the early development stage, and we are not in any way liable for the output or other behaviors of this program.

options:
  -h, --help            show this help message and exit
  -i INPUT, --input INPUT
                        Input file. Defaults to stdin.
  -o OUTPUT, --output OUTPUT
                        Output file. Defaults to stdout.
  -p PROJECT, --project PROJECT
                        Target project name.
  -d DEVELOPER, --developer DEVELOPER
                        Target project developer name. Must start with either 'Person:' or 'Organization:'.
  -l LICENSE, --license LICENSE
                        Target project license in SPDX license expression.
  -v VERSION, --version VERSION
                        Target project version string.
  -c COPYRIGHT, --copyright COPYRIGHT
                        Target project copyright string.
  -u [USER ...], --user [USER ...]
                        SBOM Creator. Must start with either 'Person:' or 'Organization:'.
```

`analyzed_sbom.py`:

```
$ ./analyzed_sbom.py -h
usage: analyzed_sbom.py [-h] [-i INPUT [INPUT ...]] [-o OUTPUT] -p PROJECT -d DEVELOPER [-l LICENSE] -v VERSION [-c COPYRIGHT] [-u [USER ...]]

This script constructs an NTIA conforming SPDX 2.3 document (SBOM) of a C/C++ project through analyzing a executable binaries. This is part of C2SBOM (Preview) from Software Engineering Laboratory, Osaka University. This project is still in the early development stage, and we are not in any way liable for the output or other behaviors of this program.

options:
  -h, --help            show this help message and exit
  -i INPUT [INPUT ...], --input INPUT [INPUT ...]
                        Input files.
  -o OUTPUT, --output OUTPUT
                        Output file. Defaults to stdout.
  -p PROJECT, --project PROJECT
                        Target project name.
  -d DEVELOPER, --developer DEVELOPER
                        Target project developer name. Must start with either 'Person:' or 'Organization:'.
  -l LICENSE, --license LICENSE
                        Target project license in SPDX license expression.
  -v VERSION, --version VERSION
                        Target project version string.
  -c COPYRIGHT, --copyright COPYRIGHT
                        Target project copyright string.
  -u [USER ...], --user [USER ...]
                        SBOM Creator. Must start with either 'Person:' or 'Organization:'.
```

## Samples

- [Build SBOM for curl 8.10.1](samples/curl-build.spdx.json) (Ubuntu 24.04 LTS)
- [Analyzed SBOM for curl 8.10.1](samples/curl-analyzed.spdx.json) (Ubuntu 24.04 LTS)

## SPDX License List

This PoC uses SPDX License List JSON to map Debian license notation to SPDX License Identifier. Although the JSON file is included in this PoC, it may be out of date by the time you try it. In that case download the new one from <https://github.com/spdx/license-list-data/blob/main/json/licenses.json> and replace the existing one. Be noted that if you use a version of the license list that is newer than the official validators internally reference, they may complain you about unknown license identifiers.

## License

Currently not determined. Be patient until we decide the licensing terms. You are at least allowed to just download this PoC, make it create some SBOMs for you, and inspect the implementation.

**This project is still in the early development stage, and we are not in any way liable for the output or any other behaviors of this program.**
