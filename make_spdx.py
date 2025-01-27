# Standard Modules
import datetime, glob, hashlib, json, os, pathlib, re, subprocess, sys, uuid

# Internal Modules
import get_metadata, get_copyright


def divide_package_name(package: str) -> tuple[str, str | None]:
    """
    Divide the given package name into a basename and an ISA (ex. `"libpsl5t64:amd64"` -> `("libpsl5t64", "amd64")`).

    The ISA part can be `None` if the package is ISA independent.
    """
    colonIndex = package.rfind(":")

    if colonIndex >= 0:
        return package[:colonIndex], package[colonIndex + 1 :]
    else:
        return package, None


def stat_line(value: int, size: int) -> str:
    """
    Construct a statistic line consisting of a value, a size, and a percentage (if the size is nonzero).
    """
    return f"{value} out of {size}" if size == 0 else f"{value} out of {size} ({value / size * 100:.2f}%)"


def normalize_resolve_path(files: set[str]) -> set[str]:
    """
    For the given set of file pathes,

    - normalize `/./`, `//`, and `/../` notations,
    - resolve symlinks, and
    - find actual versioned files (ex. `libpsl.so` -> `libpsl.so.5` -> `libpsl.so.5.3.4`).
    """
    normalized_files: set[str] = set()
    ok_count = 0

    for file in files:
        p = pathlib.Path(file)

        try:
            resolved = str(p.resolve(strict=True))
        except OSError:  # Look for a versioned file instead.
            globbed_path = glob.glob(file + "*")
            if len(globbed_path) == 0:
                print("Not found:", file, file=sys.stderr)
                continue
            p = pathlib.Path(globbed_path[0])
            try:
                resolved = str(p.resolve(strict=True))
            except OSError:
                print("Not found:", file, file=sys.stderr)
                continue

        normalized_files.add(resolved)
        ok_count += 1

    print(
        f"{stat_line(ok_count, len(files))} files are resolved, "
        f"resulting in {len(normalized_files)} files excluding repetition.",
        file=sys.stderr,
    )
    return normalized_files


def map_files_to_packages(files: set[str]) -> list[tuple[str, set[str]]]:
    """
    Map files to their packages using the `dpkg-query -S` tool.

    Return a list of tuples that contain a package name as the first tuple item and
    a set of file names which belong to the package as the second tuple item.
    """
    packages: dict[str, set[str]] = {}
    ok_count = 0

    for file in files:
        dpkg = subprocess.run(f"dpkg-query -S '{file}'", shell=True, capture_output=True, text=True)
        if dpkg.returncode != 0:
            print("'dpkg-query -S' failed for", file, file=sys.stderr)
            continue
        pkg_name = dpkg.stdout.split()[0][:-1]

        packages.setdefault(pkg_name, set())
        packages[pkg_name].add(file)
        ok_count += 1

    print(
        f"{stat_line(ok_count, len(files))} files are mapped to {len(packages)} packages.",
        file=sys.stderr,
    )
    return sorted(packages.items())


def print_stats(
    packages: list,
    list_package_stats: list[dict[str, bool | str]],
    list_license_stats: list[dict[str, bool]],
):
    """
    Print the SBOM generation statistics.
    """
    package_stats: dict[str, int] = {
        "name": 0,
        "SPDXID": 0,
        "versionInfo": 0,
        "packageFileName": 0,
        "downloadLocation": 0,
        "filesAnalyzed": 0,
        "homepage": 0,
        "supplier": 0,
        "originator": 0,
        "summary": 0,
        "description": 0,
        "checksums": 0,
        "externalRefs": 0,
        "copyrightText": 0,
        "licenseConcluded": 0,
        "licenseDeclared": 0,
        "licenseComments": 0,
        "comment": 0,
        "copyright_ok": 0,
        "copyright_cannot_open": 0,
        "copyright_unknown_format": 0,
        "license_count": 0,
        "license_expr_valid": 0,
    }
    for item in list_package_stats:
        for key in item:
            if key != "copyright_status":
                package_stats[key] += item[key]
            elif item[key] == "ok":
                package_stats["copyright_ok"] += 1
            elif item[key] == "cannot open":
                package_stats["copyright_cannot_open"] += 1
            elif item[key] == "unknown format":
                package_stats["copyright_unknown_format"] += 1

    license_stats: dict[str, int] = {
        "licenseId": 0,
        "name": 0,
        "extractedText": 0,
        "comment": 0,
    }
    for item in list_license_stats:
        for key in item:
            license_stats[key] += item[key]

    print("=== Results ===", file=sys.stderr)

    print(
        f"Processed packages: {stat_line(len(packages), len(list_package_stats))}",
        file=sys.stderr,
    )
    if len(list_package_stats) > 0:
        print("Package metadata", file=sys.stderr)
        for item in package_stats.items():
            if item[0] == "license_count":
                continue
            print(
                f"- {item[0]}: {stat_line(item[1], len(list_package_stats))}",
                file=sys.stderr,
            )

    print(
        f"Unknown licenses: {stat_line(len(list_license_stats), package_stats['license_count'])}",
        file=sys.stderr,
    )
    if len(list_license_stats) > 0:
        print("License metadata", file=sys.stderr)
        for item in license_stats.items():
            print(
                f"- {item[0]}: {stat_line(item[1], len(list_license_stats))}",
                file=sys.stderr,
            )


def make_spdx(
    packages: list[tuple[str, set[str]]],
    target_project: str,
    target_developer: str,
    target_version: str,
    target_license: str | None,
    target_copyright: str | None,
    target_creators: list[str],
    no_license_heuristic: bool,
    include_individual_licenses: bool = False,
    include_files_section: bool = False,
) -> str:
    """
    Generate a whole SPDX document for given packages in the JSON format.
    """
    document_id = "SPDXRef-DOCUMENT"
    root_package_id = "SPDXRef-RootPackage"

    spdx: dict = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": document_id,
        "name": target_project,
        "documentNamespace": f"https://spdx.org/spdxdocs/c2sbom-{target_project}-{uuid.uuid4()}",
        "creationInfo": {
            "created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "creators": target_creators
            + [
                "Organization: Software Engineering Laboratory, Osaka University",
                "Tool: C2SBOM Preview",
            ],
        },
        "documentDescribes": [root_package_id],
        "packages": [
            {
                "name": target_project,
                "SPDXID": root_package_id,
                "filesAnalyzed": False,
                "downloadLocation": "NOASSERTION",
                "licenseConcluded": "NOASSERTION" if target_license is None else target_license,
                "licenseDeclared": "NOASSERTION" if target_license is None else target_license,
                "copyrightText": "NOASSERTION" if target_copyright is None else target_copyright,
                "versionInfo": target_version,
                "supplier": target_developer,
            }
        ],
        "hasExtractedLicensingInfos": [],
        "relationships": [
            {
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": root_package_id,
                "spdxElementId": document_id,
            }
        ],
    }

    if include_files_section:
        spdx["files"] = []

    list_package_stats: list[dict[str, bool]] = []
    list_license_stats: list[dict[str, bool]] = []

    for package, files in packages:
        print(f"Processing '{package}'...", file=sys.stderr)

        package_basename, arch = divide_package_name(package)
        package_meta, package_stats = get_metadata.get_metadata(package_basename, arch)

        comment, copyright_text, license_manager, copyright_status = get_copyright.get_license(
            package_basename, arch, no_license_heuristic
        )
        licenseDeclared = license_manager.all_expr_str_cat
        package_stats["copyright_status"] = copyright_status
        package_stats["license_count"] = len(license_manager.stats_all_licenses)
        package_stats["license_expr_valid"] = license_manager.stats_syntax_errors == 0

        if len(copyright_text) > 0:
            package_meta["copyrightText"] = copyright_text
            package_stats["copyrightText"] = True
        elif copyright_status == "ok":
            package_meta["copyrightText"] = "NONE"
            package_stats["copyrightText"] = True

        if include_individual_licenses:
            licenseInfoFromFiles = license_manager.all_expr_str
            if len(licenseInfoFromFiles) > 0:
                package_meta["licenseInfoFromFiles"] = licenseInfoFromFiles

        if len(licenseDeclared) > 0:
            package_meta["licenseDeclared"] = licenseDeclared
            package_stats["licenseDeclared"] = True
            package_meta["licenseConcluded"] = licenseDeclared
            package_stats["licenseConcluded"] = True

        if len(comment) > 0:
            package_meta["licenseComments"] = comment
            package_stats["licenseComments"] = True

        if include_files_section:
            for file in sorted(files):
                base_index = file.rindex(os.path.sep)
                file_basename = re.sub(r"[^0-9a-zA-Z\.\-]+", "-", file[base_index + 1 :])
                file_path = re.sub(r"[^0-9a-zA-Z\.\-]+", "-", file[:base_index])

                try:
                    with open(file, "rb") as fd:
                        md5 = hashlib.md5(fd.read()).hexdigest()
                        sha1 = hashlib.sha1(fd.read()).hexdigest()
                        sha256 = hashlib.sha256(fd.read()).hexdigest()
                        sha512 = hashlib.sha512(fd.read()).hexdigest()
                except OSError as e:
                    print(
                        f"Error: Cannot open '{file}': {e.strerror}, skipping it.",
                        file=sys.stderr,
                    )
                    continue

                file_meta = {
                    "fileName": file,
                    "SPDXID": f"SPDXRef-File-{file_path}--{file_basename}-{sha1}",
                    "checksums": [
                        {"algorithm": "MD5", "checksumValue": md5},
                        {"algorithm": "SHA1", "checksumValue": sha1},
                        {"algorithm": "SHA256", "checksumValue": sha256},
                        {"algorithm": "SHA512", "checksumValue": sha512},
                    ],
                    "licenseConcluded": (licenseDeclared if len(licenseDeclared) > 0 else "NOASSERTION"),
                    "licenseComments": comment,
                }
                spdx["files"].append(file_meta)

                spdx["relationships"].append(
                    {
                        "relationshipType": "CONTAINS",
                        "relatedSpdxElement": file_meta["SPDXID"],
                        "spdxElementId": package_meta["SPDXID"],
                    }
                )

        spdx["packages"].append(package_meta)
        list_package_stats.append(package_stats)

        spdx["relationships"].append(
            {
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": package_meta["SPDXID"],
                "spdxElementId": root_package_id,
            }
        )

        for license_ref, value in license_manager.licenses.items():
            if value.name.lower() == "public-domain" and value.text is None:
                # As per https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
                value.text = (
                    "No license required for any purpose; the work is not subject to copyright in any jurisdiction."
                )
                if value.comment is None:
                    value.comment = (
                        "Using the text from https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/ "
                        "since no license text is extracted."
                    )
                else:
                    value.comment += (
                        "\nUsing the text from https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/ "
                        "since no license text is extracted."
                    )

            spdx["hasExtractedLicensingInfos"].append(
                {
                    "licenseId": license_ref,
                    "name": value.name,
                    "extractedText": "No text found for this license." if value.text is None else value.text,
                    "comment": "" if value.comment is None else value.comment,
                }
            )

            list_license_stats.append(
                {
                    "licenseId": True,
                    "name": value.name != "NOASSERTION",
                    "extractedText": value.text is not None and len(value.text) > 0,
                    "comment": value.comment is not None and len(value.comment) > 0,
                }
            )

    print(file=sys.stderr)
    print_stats(packages, list_package_stats, list_license_stats)
    return json.dumps(spdx, ensure_ascii=False, indent=2)
