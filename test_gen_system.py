#!/usr/bin/env python3

# Standard modules
import argparse, sys, subprocess

# Internal modules
import make_spdx


def validate_name(name: str) -> str:
    """
    Validate if the given name starts with either `Person:` or `Organization:` as specified in SPDX 2.3.

    Raise `TypeError` if the validation fails.
    """
    if not name.startswith("Person:") and not name.startswith("Organization:"):
        raise TypeError()
    return name


parser = argparse.ArgumentParser(
    description="This is a test script for evaluation. "
    "Just searches for all installed packages and collects metadata. "
    "This is a part of C2SBOM (Preview) from Software Engineering Laboratory, Osaka University. "
    "This is an experimental proof-of-concept release, "
    "and we are not in any way liable for the output or any other behaviors of this program."
)
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
    "-q",
    "--quiet",
    action="store_true",
    help="Suppress unimportant console output.",
)
args = parser.parse_args()

dpkg = subprocess.run(f"dpkg-query -W", shell=True, capture_output=True, text=True)
if dpkg.returncode != 0:
    print("'dpkg-query -W' failed.", file=sys.stderr)
    exit(-1)

packages: list[tuple[str, set[str]]] = []

for line in dpkg.stdout.splitlines():
    packages.append((line.split()[0], set()))

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
