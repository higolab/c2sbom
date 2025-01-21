#!/usr/bin/env python3

# Standard modules
import argparse, os, sys, typing

# Internal modules
import make_spdx


def extract_file_names(stream: typing.TextIO) -> set[str]:
    """
    Extract library file names from the `make` console output.
    Only system library files are collected and all local libraries are ignored.

    System library files are files that is in absolute path, and others are considered local library files.
    """
    sys_libs: set[str] = set()

    for line in stream:
        # Handle ". /path/to/file.h"
        index = 0
        done = False
        while index < len(line):
            if line[index].isspace():
                path = line[index + 1 :].strip()
                if path[0] == os.path.sep:
                    sys_libs.add(path)
                done = True
                break
            if line[index] != "." and line[index] != "!":
                break
            index += 1
        if done:
            continue

        # Handle "/path/to/file.so"
        if line[0] == os.path.sep:
            sys_libs.add(line.rstrip())

    return sys_libs


def extract_file_names_verbose(stream: typing.TextIO) -> tuple[set[str], set[str]]:
    """
    Extract file names from the linker (`ld`) verbose console output and
    return sets of system library files and local library files in this order (legacy).

    System library files are files that is in absolute path, and others are considered local library files.
    """
    sys_libs: set[str] = set()
    local_libs: set[str] = set()
    current_path: str = os.getcwd()

    for line in stream:
        # Handle "make[x]: Entering directory '/path/to/xxx'"
        index = line.find("Entering directory")
        if index >= 0:
            index += 20  # Seek to the path component
            end = index
            while end < len(line):
                if line[end] == "'":
                    current_path = line[index:end]
                    if current_path[-1] != os.path.sep:
                        current_path += os.path.sep
                    break
                end += 1
            else:
                print("Parse error:", line, file=sys.stderr)

        line = line.strip()

        # Handle "attempt to open /path/to/xxx succeeded"
        if line.startswith("attempt to open") and line.endswith("succeeded"):
            path = line[16:-10]
            if path[0] == os.path.sep:
                sys_libs.add(path)
            else:
                local_libs.add(current_path + path)
            continue

        # Handle "found xxx at /path/to/xxx"
        if line.startswith("found"):
            for i in range(len(line) - 4):
                if line[i : i + 4] == " at ":
                    path = line[i + 4 :]
                    if path[0] == os.path.sep:
                        sys_libs.add(path)
                    else:
                        local_libs.add(current_path + path)
            continue

    return sys_libs, local_libs


def validate_name(name: str) -> str:
    """
    Validate if the given name starts with either `Person:` or `Organization:` as specified in SPDX 2.3.

    Raise `TypeError` if the validation fails.
    """
    if not name.startswith("Person:") and not name.startswith("Organization:"):
        raise TypeError()
    return name


def process_file_extension(name: str) -> str:
    """
    Add `.spdx.json` if the given file name doesn't have any extension.
    """
    return name if "." in name else name + ".spdx.json"


parser = argparse.ArgumentParser(
    description="This script constructs an NTIA Minimum Elements conforming SPDX 2.3 document (SBOM) "
    "of a C/C++ project through analyzing a build process. "
    "This is part of C2SBOM (Preview) from Software Engineering Laboratory, Osaka University. "
    "This project is still in the early development stage, "
    "and we are not in any way liable for the output or other behaviors of this program."
)
parser.add_argument("-i", "--input", help="Input file. Defaults to stdin.")
parser.add_argument(
    "-o",
    "--output",
    type=process_file_extension,
    help="Output file. Defaults to stdout.",
)
parser.add_argument("-p", "--project", help="Target project name.", required=True)
parser.add_argument(
    "-d",
    "--developer",
    type=validate_name,
    help="Target project developer name. Must start with either 'Person:' or 'Organization:'.",
    required=True,
)
parser.add_argument(
    "-l",
    "--license",
    help="Target project license in SPDX license expression.",
)
parser.add_argument("-v", "--version", help="Target project version string.", required=True)
parser.add_argument("-c", "--copyright", help="Target project copyright string.")
parser.add_argument(
    "-u",
    "--user",
    type=validate_name,
    nargs="*",
    help="SBOM Creator. Must start with either 'Person:' or 'Organization:'.",
)
parser.add_argument(
    "--no-license-heuristic",
    action="store_true",
    help="Disable the simple heuristic for license name matching.",
)
parser.add_argument(
    "--verbose-input",
    action="store_true",
    help="Use the linker '--verbose' output parser for the input instead of the '-t' output (deprecated).",
)
parser.add_argument(
    "--include-individual-licenses",
    action="store_true",
    help="Include 'licenseInfoFromFiles' field (makes the SPDX document not standard conformant).",
)
parser.add_argument(
    "--include-files-section",
    action="store_true",
    help="Include incomplete 'files' section (makes the SPDX document not standard conformant).",
)
args = parser.parse_args()

if args.input is None:
    if args.verbose_input:
        sys_libs, local_libs = extract_file_names_verbose(sys.stdin)
        local_libs = [  # Filter out internal files
            x for x in make_spdx.normalize_resolve_path(local_libs) if "lib" in x
        ]
    else:
        sys_libs = extract_file_names(sys.stdin)
else:
    try:
        with open(args.input, encoding="utf-8", errors="ignore") as fd:
            if args.verbose_input:
                sys_libs, local_libs = extract_file_names_verbose(fd)
                local_libs = [  # Filter out internal files
                    x for x in make_spdx.normalize_resolve_path(local_libs) if "lib" in x
                ]
            else:
                sys_libs = extract_file_names(fd)
    except OSError as e:
        print(f"Cannot open '{args.input}', {e}", file=sys.stderr)
        exit(-1)

sys_libs = make_spdx.normalize_resolve_path(sys_libs)
packages = make_spdx.map_files_to_packages(sys_libs)
spdx = make_spdx.make_spdx(
    packages,
    args.project,
    args.developer,
    args.version,
    args.license,
    args.copyright,
    [] if args.user is None else args.user,
    args.no_license_heuristic,
    args.include_individual_licenses,
    args.include_files_section,
)

if args.output is None:
    print(spdx)
else:
    try:
        with open(args.output, mode="w", encoding="utf-8") as fd:
            fd.write(spdx + "\n")
    except OSError as e:
        print(f"Cannot open '{args.output}', {e}", file=sys.stderr)
        exit(-1)
