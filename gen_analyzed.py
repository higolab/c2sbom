#!/usr/bin/env python3

# Standard modules
import argparse, subprocess, sys

# Internal modules
import make_spdx


def run_ldd(file: str) -> set[str]:
    """
    Extract library files that the target executable depends on using the `ldd` tool.

    Raise `RuntimeError` if the call to `ldd` fails.
    """
    ldd = subprocess.run(f"ldd '{file}'", shell=True, capture_output=True, text=True)
    if ldd.returncode != 0:
        raise RuntimeError("'ldd' failed for", file)

    files: set[str] = set()
    for line in ldd.stdout.splitlines():
        if "linux-vdso" in line or "ld-linux" in line:
            continue

        line_splitted = line.split()
        if len(line_splitted) < 3:
            print("Not resolved:", line_splitted[0], file=sys.stderr)

        files.add(line_splitted[2])

    return files


def validate_name(name: str) -> str:
    """
    Validate if the given name starts with either `Person:` or `Organization:` as specified in SPDX 2.3.

    Raise `TypeError` if the validation fails.
    """
    if not name.startswith("Person:") and not name.startswith("Organization:"):
        raise TypeError()
    return name


parser = argparse.ArgumentParser(
    description="This script constructs an NTIA Minimum Elements conforming SPDX 2.3 document (SBOM) "
    "of a C/C++ project through analyzing a executable binaries. "
    "This is part of C2SBOM (Preview) from Software Engineering Laboratory, Osaka University. "
    "This project is still in the early development stage, "
    "and we are not in any way liable for the output or other behaviors of this program."
)
parser.add_argument("-i", "--input", nargs="+", help="Input files.")
parser.add_argument(
    "-o",
    "--output",
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
    "--include-individual-licenses",
    action="store_true",
    help="Include 'licenseInfoFromFiles' field (makes the SPDX document not standard conformant).",
)
parser.add_argument(
    "--include-files-section",
    action="store_true",
    help="Include incomplete 'files' section (makes the SPDX document not standard conformant).",
)
parser.add_argument(
    "-q", "--quiet",
    action="store_true",
    help="Suppress unimportant console output.",
)
args = parser.parse_args()

libs: set[str] = set()
for file in args.input:
    try:
        libs |= run_ldd(file)
    except RuntimeError as e:
        print("Error:", e, file=sys.stderr)

libs = make_spdx.normalize_resolve_path(libs, args.quiet)
packages = make_spdx.map_files_to_packages(libs, args.quiet)
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
    args.quiet,
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
