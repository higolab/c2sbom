# C2SBOM Preview (Proof-of-Concept)

This is an experimental, proof-of-concept version of C2SBOM to automatically generate an SPDX 2.3 Document for a C/C++ project in JSON format. These scripts construct [valid](https://tools.spdx.org/app/validate/) and [NTIA Minimum Elements Conformant](https://tools.spdx.org/app/ntia_checker/) SBOMs. This project comes with two distinct scripts:

- `gen_build.py`: Reads output from build tools (`gcc`/`g++` and `ld`) and generates an SPDX document of build-time dependencies (i.e., compiled/linked into the resulting binaries).
  - Thus constructs a "Build SBOM" by the [CISA (Cybersecurity and Infrastructure Security Agency) definition](https://www.cisa.gov/sites/default/files/2023-04/sbom-types-document-508c.pdf)
- `gen_analyzed.py`: Reads executable binaries and generates an SPDX document of run-time dependencies.
  - Thus constructs an "Analyzed SBOM" by the [CISA definition](https://www.cisa.gov/sites/default/files/2023-04/sbom-types-document-508c.pdf)

`gen_build.py` needs output that is made with

- `-H` option enabled for `gcc`/`g++`, and
  - Header file dependencies will not be included if you omit this option
- `-t` option enabled for `ld` (or `-Wl,-t` option enabled for `gcc`/`g++`).
  - Library file dependencies will not be included if you omit this option

Make sure to include not only stdout but also stderr output.

## Requirements

- Debian-based Linux distribution (Debian, Ubuntu, Linux Mint, etc)
- Python 3.9 or later (tested until Python 3.12)

This PoC doesn't have any external dependencies and uses only standard libraries which are included in a default Python installation, so it should just run out of the box. Just download everything and invoke the one you want.

## Usage

`gen_build.py`:

```
$ ./gen_build.py -h
usage: gen_build.py [-h] [-i INPUT] [-o OUTPUT] -p PROJECT -d DEVELOPER [-l LICENSE] -v VERSION [-c COPYRIGHT] [-u [USER ...]] [-s SOURCE_TREE] [--no-license-heuristic] [--verbose-input] [--include-individual-licenses] [--include-files-section] [-q]

This script constructs an NTIA Minimum Elements conforming SPDX 2.3 document (SBOM) of a C/C++ project through analyzing a build process. This is a part of C2SBOM (Preview) from Software Engineering Laboratory, Osaka University. This is an experimental proof-of-concept release, and we are not in any way liable for the output or any other behaviors of this program.

options:
  -h, --help            show this help message and exit
  -i, --input INPUT     Input file. Defaults to stdin.
  -o, --output OUTPUT   Output file. Defaults to stdout.
  -p, --project PROJECT
                        Target project name.
  -d, --developer DEVELOPER
                        Target project developer name. Must start with either 'Person:' or 'Organization:'.
  -l, --license LICENSE
                        Target project license in SPDX license expression.
  -v, --version VERSION
                        Target project version string.
  -c, --copyright COPYRIGHT
                        Target project copyright string.
  -u, --user [USER ...]
                        SBOM Creator. Must start with either 'Person:' or 'Organization:'.
  -s SOURCE_TREE, --source-tree SOURCE_TREE
                        Root path of the target project's source tree. Defaults to the current directory.
  --no-license-heuristic
                        Disable the simple heuristic for license name matching.
  --verbose-input       Use the linker '--verbose' output parser for the input instead of the '-t' output (deprecated).
  --include-individual-licenses
                        Include 'licenseInfoFromFiles' field (makes the SPDX document not standard conformant).
  --include-files-section
                        Include incomplete 'files' section (makes the SPDX document not standard conformant).
  -q, --quiet           Suppress unimportant console output.
```

`gen_analyzed.py`:

```
$ ./gen_analyzed.py -h
usage: gen_analyzed.py [-h] [-i INPUT [INPUT ...]] [-o OUTPUT] -p PROJECT -d DEVELOPER [-l LICENSE] -v VERSION [-c COPYRIGHT] [-u [USER ...]] [--no-license-heuristic] [--include-individual-licenses] [--include-files-section] [-q]

This script constructs an NTIA Minimum Elements conforming SPDX 2.3 document (SBOM) of a C/C++ project through analyzing a executable binaries. This is a part of C2SBOM (Preview) from Software Engineering Laboratory, Osaka University. This is an experimental proof-of-concept release, and we are not in any way liable for the output or any other behaviors of this program.

options:
  -h, --help            show this help message and exit
  -i, --input INPUT [INPUT ...]
                        Input files.
  -o, --output OUTPUT   Output file. Defaults to stdout.
  -p, --project PROJECT
                        Target project name.
  -d, --developer DEVELOPER
                        Target project developer name. Must start with either 'Person:' or 'Organization:'.
  -l, --license LICENSE
                        Target project license in SPDX license expression.
  -v, --version VERSION
                        Target project version string.
  -c, --copyright COPYRIGHT
                        Target project copyright string.
  -u, --user [USER ...]
                        SBOM Creator. Must start with either 'Person:' or 'Organization:'.
  --no-license-heuristic
                        Disable the simple heuristic for license name matching.
  --include-individual-licenses
                        Include 'licenseInfoFromFiles' field (makes the SPDX document not standard conformant).
  --include-files-section
                        Include incomplete 'files' section (makes the SPDX document not standard conformant).
  -q, --quiet           Suppress unimportant console output.
```

## Samples

Following sample SBOMs are generated on Ubuntu 24.04 LTS AMD64.

- Build SBOMs
  - [curl 8.12.1](samples/curl-build.spdx.json)
  - [Apache HTTP Server 2.4.63](samples/apache-build.spdx.json)
  - [nginx 1.27.4](samples/nginx-build.spdx.json)
  - [PHP 8.4.4](samples/php-build.spdx.json)
  - [Python 3.13.2](samples/python-build.spdx.json)
- Analyzed SBOMs
  - [curl 8.12.1](samples/curl-analyzed.spdx.json)
  - [Apache HTTP Server 2.4.63](samples/apache-analyzed.spdx.json)
  - [nginx 1.27.4](samples/nginx-analyzed.spdx.json)
  - [PHP 8.4.4](samples/php-analyzed.spdx.json)
  - [Python 3.13.2](samples/python-analyzed.spdx.json)

## SPDX License List

This PoC uses SPDX License List JSON to map Debian license notation to SPDX License Identifier. Although the JSON file is included in this PoC, it may be out of date by the time you try it. In that case download the new one from <https://github.com/spdx/license-list-data/blob/main/json/licenses.json> and replace the existing one. Be noted that if you use a version of the license list that is newer than the official validators internally reference, they may complain you about unknown license identifiers.

## License

This project is licensed under the [MIT License](LICENSE).

**This is an experimental proof-of-concept release, and we are not in any way liable for the output or any other behaviors of this program.**
