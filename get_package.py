# Standard Modules
import datetime, glob, json, pathlib, subprocess, sys, urllib.parse, uuid  # hashlib, os, re

# Internal Modules
import get_copyright


def normalize_resolve_path(files: set[str]) -> set[str]:
    """
    For the given set of file pathes,

    - normalize `/./`, `//`, and `/../` notations,
    - resolve symlinks, and
    - find actual versioned files
      (ex. `libpsl.so` -> `libpsl.so.5` -> `libpsl.so.5.3.4`).
    """
    normalized_files: set[str] = set()
    ok_count: int = 0

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
        f"{ok_count} out of {len(files)} ({ok_count / len(files) * 100:.2f}%) files are resolved, resulting in {len(normalized_files)} files excluding repetition.",
        file=sys.stderr,
    )
    return normalized_files


def map_files_to_packages(files: set[str]) -> list[tuple[str, set[str]]]:
    """
    Map files to their packages using the `dpkg -S` tool.

    Return a list of tuples that contain a package name
    as the first tuple item and a set of file names
    which belong to the package as the second tuple item.
    """
    packages: dict[str, set[str]] = {}
    ok_count: int = 0

    for file in files:
        dpkg = subprocess.run(
            f"dpkg -S '{file}'", shell=True, capture_output=True, text=True
        )
        if dpkg.returncode != 0:
            print("'dpkg -S' failed for", file, file=sys.stderr)
            continue
        pkg_name = dpkg.stdout.split()[0][:-1]

        packages.setdefault(pkg_name, set())
        packages[pkg_name].add(file)
        ok_count += 1

    print(
        f"{ok_count} out of {len(files)} ({ok_count / len(files) * 100:.2f}%) files are mapped to {len(packages)} packages.",
        file=sys.stderr,
    )
    return sorted(packages.items())


def divide_package_name(package: str) -> tuple[str, str | None]:
    """
    Divide the given package name into a basename and an ISA.
    Ex. `"libpsl5t64:amd64"` -> `("libpsl5t64", "amd64")`

    The ISA part can be `None` if the package is ISA independent.
    """
    colonIndex = package.rfind(":")

    if colonIndex >= 0:
        return package[:colonIndex], package[colonIndex + 1 :]
    else:
        return package, None


def get_installed_version(package: str) -> str:
    """Return a installed version for the given package."""
    dpkg_query = subprocess.run(
        f"dpkg-query -W '{package}'",
        shell=True,
        capture_output=True,
        text=True,
    )
    if dpkg_query.returncode != 0:
        raise RuntimeError("'dpkg-query -W' failed")

    dq_split = dpkg_query.stdout.split()
    if len(dq_split) < 2:
        raise RuntimeError("Unexpected 'dpkg-query -W' output: " + dpkg_query.stdout)

    return dq_split[1]


def get_download_url(package: str, version: str) -> tuple[str, str]:
    """
    Return a download URL and a package file name for the given package,
    as a tuple in this order.
    """
    dl = subprocess.run(
        f"apt-get download --print-uris '{package}={version}'",
        shell=True,
        capture_output=True,
        text=True,
    )
    if dl.returncode != 0:
        raise RuntimeError("'apt-get download --print-uris' failed")

    dl_split = dl.stdout.split()
    if len(dl_split) < 2:
        raise RuntimeError(
            "Unexpected 'apt-get download --print-uris' output: " + dl.stdout
        )

    return dl_split[1], dl_split[0][1:-1]  # Trim quotes


def make_purl(package_basename: str, version: str, arch: str | None) -> str:
    """
    Construct a Package URL (purl) for the given package.
    Uses `/etc/os-release` file to extract the vendor and distro.
    """
    vendor: str | None = None
    distro: str | None = None

    try:
        with open("/etc/os-release", encoding="utf-8") as f_rel:
            for line in f_rel:
                if line.startswith("ID="):
                    vendor = (
                        line[4:-1].lower().strip()
                        if line[4] == "'" or line[4] == '"'
                        else line[3:].lower().strip()
                    )
                elif line.startswith("VERSION_CODENAME="):
                    distro = (
                        line[18:-1].lower().strip()
                        if line[18] == "'" or line[18] == '"'
                        else line[17:].lower().strip()
                    )
    except:
        raise RuntimeError("Cannot open '/etc/os-release'")

    if vendor is None:
        raise RuntimeError("Cannot find 'ID' from '/etc/os-release'")
    else:
        qualifiers = ""
        if arch is not None:
            qualifiers += f"?arch={urllib.parse.quote(arch)}"
        if distro is not None:
            qualifiers += f"?distro={urllib.parse.quote(distro)}"

        return f"pkg:deb/{urllib.parse.quote(vendor)}/{urllib.parse.quote(package_basename)}@{urllib.parse.quote(version)}{qualifiers}"


def read_description(lines: list[str], start: int = 0) -> str:
    """Read an extended description as in the Debian `control` file."""
    index: int = start
    result: str = ""

    while index < len(lines):
        line_stripped = lines[index].strip()
        length = len(line_stripped)

        if lines[index].startswith("  ") and length > 0:  # Verbatim
            result += lines[index][1:].rstrip() + "\n"
        elif lines[index].startswith(" .") and length > 0:  # Blank line
            result += "\n"
        elif lines[index].startswith(" ") and length > 0:  # Continuation
            result += line_stripped + "\n"
        else:  # End of field
            break

        index += 1

    return result.rstrip()


def get_metadata(package: str, arch: str | None) -> tuple[dict, dict[str, bool]]:
    """
    Return an SPDX package information item and metadata collection statistics
    for the given package in this order.
    """
    package_meta: dict = {
        "name": package,
        "SPDXID": f"SPDXRef-Package--{uuid.uuid4()}",
        "versionInfo": "NOASSERTION",
        "packageFileName": "NOASSERTION",
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "homepage": "NOASSERTION",
        "supplier": "NOASSERTION",
        "originator": "NOASSERTION",
        "checksums": [],
        "externalRefs": [],
        "copyrightText": "NOASSERTION",
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": "NOASSERTION",
        # "licenseInfoFromFiles": [],
        "licenseComments": "",
        "comment": "",
    }

    statistics: dict[str, bool | str] = {
        "name": True,
        "SPDXID": True,
        "versionInfo": False,
        "packageFileName": False,
        "downloadLocation": False,
        "filesAnalyzed": True,
        "homepage": False,
        "supplier": False,
        "originator": False,
        "summary": False,
        "description": False,
        "md5": False,
        "sha1": False,
        "sha256": False,
        "sha512": False,
        "externalRefs": False,
        "copyrightText": False,
        "licenseConcluded": False,
        "licenseDeclared": False,
        # "licenseInfoFromFiles": False,
        "licenseComments": False,
        "comment": False,
        "copyright_status": None,
    }

    comment: str = ""
    whole_package_name: str = package if arch is None else package + ":" + arch

    try:
        version = get_installed_version(whole_package_name)
        package_meta["versionInfo"] = version
        statistics["versionInfo"] = True
    except RuntimeError as e:
        package_meta["comment"] = f"Error: {e}, not generating metadata."
        statistics["comment"] = True
        return package_meta

    try:
        filename, url = get_download_url(whole_package_name, version)
        package_meta["packageFileName"] = filename
        statistics["packageFileName"] = True
        package_meta["downloadLocation"] = url
        statistics["downloadLocation"] = True
        # meta_dic["packageVerificationCode"] = {
        #    "packageVerificationCodeValue": hashlib.sha1(
        #        hashlib.sha1(filename.encode("utf-8")).hexdigest().encode("utf-8")
        #    ).hexdigest()
        # }
    except RuntimeError as e:
        comment += (
            f"Warning: {e}, not including packageFileName and downloadLocation.\n"
        )

    try:
        purl = make_purl(package, version, arch)
        package_meta["externalRefs"] = [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": purl,
            }
        ]
        statistics["externalRefs"] = True
    except RuntimeError as e:
        comment += f"Warning: {e}, not including purl.\n"

    # Get many metadata
    apt_show = subprocess.run(
        f"apt-cache show '{whole_package_name}={version}'",
        shell=True,
        capture_output=True,
        text=True,
    )
    if apt_show.returncode != 0:
        package_meta["comment"] = (
            "Error: 'apt-cache show' failed, not generating metadata."
        )
        statistics["comment"] = True
        return package_meta

    package_meta["comment"] = comment.rstrip()
    statistics["comment"] = len(package_meta["comment"]) > 0

    index = 0
    lines = apt_show.stdout.splitlines()
    for line in lines:
        if line.startswith("Maintainer:"):
            value = line[11:].strip()
            if len(value) > 0:
                package_meta["supplier"] = "Organization: " + value.replace(
                    "<", "("
                ).replace(">", ")")
                statistics["supplier"] = True
        elif line.startswith("Original-Maintainer:"):
            value = line[20:].strip()
            if len(value) > 0:
                package_meta["originator"] = "Organization: " + value.replace(
                    "<", "("
                ).replace(">", ")")
                statistics["originator"] = True
        elif line.startswith("Homepage:"):
            value = line[9:].strip()
            if len(value) > 0:
                package_meta["homepage"] = value
                statistics["homepage"] = True
        elif line.startswith("Description-en:"):
            summary = line[15:].strip()
            if len(summary) > 0:
                package_meta["summary"] = summary
                statistics["summary"] = True
            description = read_description(lines, index + 1)
            if len(description) > 0:
                package_meta["description"] = description
                statistics["description"] = True
        elif line.startswith("MD5sum:"):
            value = line[7:].strip()
            if len(value) > 0:
                package_meta.setdefault("checksums", [])
                package_meta["checksums"].append(
                    {"algorithm": "MD5", "checksumValue": value}
                )
                statistics["md5"] = True
        elif line.startswith("SHA1:"):
            value = line[5:].strip()
            if len(value) > 0:
                package_meta.setdefault("checksums", [])
                package_meta["checksums"].append(
                    {"algorithm": "SHA1", "checksumValue": value}
                )
                statistics["sha1"] = True
                package_meta["SPDXID"] = f"SPDXRef-Package--{value}"
        elif line.startswith("SHA256:"):
            value = line[7:].strip()
            if len(value) > 0:
                package_meta.setdefault("checksums", [])
                package_meta["checksums"].append(
                    {"algorithm": "SHA256", "checksumValue": value}
                )
                statistics["sha256"] = True
        elif line.startswith("SHA512:"):
            value = line[7:].strip()
            if len(value) > 0:
                package_meta.setdefault("checksums", [])
                package_meta["checksums"].append(
                    {"algorithm": "SHA512", "checksumValue": value}
                )
                statistics["sha512"] = True

        index += 1

    return package_meta, statistics


def print_stats(
    packages: list,
    list_package_stats: list[dict[str, bool | str]],
    list_license_stats: list[dict[str, bool]],
):
    """Print the generation statistics."""
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
        "md5": 0,
        "sha1": 0,
        "sha256": 0,
        "sha512": 0,
        "externalRefs": 0,
        "copyrightText": 0,
        "licenseConcluded": 0,
        "licenseDeclared": 0,
        # "licenseInfoFromFiles": 0,
        "licenseComments": 0,
        "comment": 0,
        "copyright_ok": 0,
        "copyright_cannot_open": 0,
        "copyright_unknown_format": 0,
    }
    for item in list_package_stats:
        package_stats["name"] += item["name"]
        package_stats["SPDXID"] += item["SPDXID"]
        package_stats["versionInfo"] += item["versionInfo"]
        package_stats["packageFileName"] += item["packageFileName"]
        package_stats["downloadLocation"] += item["downloadLocation"]
        package_stats["filesAnalyzed"] += item["filesAnalyzed"]
        package_stats["homepage"] += item["homepage"]
        package_stats["supplier"] += item["supplier"]
        package_stats["originator"] += item["originator"]
        package_stats["summary"] += item["summary"]
        package_stats["description"] += item["description"]
        package_stats["md5"] += item["md5"]
        package_stats["sha1"] += item["sha1"]
        package_stats["sha256"] += item["sha256"]
        package_stats["sha512"] += item["sha512"]
        package_stats["externalRefs"] += item["externalRefs"]
        package_stats["copyrightText"] += item["copyrightText"]
        package_stats["licenseConcluded"] += item["licenseConcluded"]
        package_stats["licenseDeclared"] += item["licenseDeclared"]
        # package_stats["licenseInfoFromFiles"] += item["licenseInfoFromFiles"]
        package_stats["licenseComments"] += item["licenseComments"]
        package_stats["comment"] += item["comment"]
        if item["copyright_status"] == "ok":
            package_stats["copyright_ok"] += 1
        elif item["copyright_status"] == "cannot open":
            package_stats["copyright_cannot_open"] += 1
        elif item["copyright_status"] == "unknown format":
            package_stats["copyright_unknown_format"] += 1

    license_stats: dict[str, int] = {
        "licenseId": 0,
        "name": 0,
        "extractedText": 0,
        "comment": 0,
    }
    for item in list_license_stats:
        license_stats["licenseId"] += item["licenseId"]
        license_stats["name"] += item["name"]
        license_stats["extractedText"] += item["extractedText"]
        license_stats["comment"] += item["comment"]

    package_stat_str: str = (
        ""
        if len(list_package_stats) == 0
        else f"""- Package metadata
  - name: {package_stats["name"]} out of {len(list_package_stats)} ({package_stats["name"] / len(list_package_stats) * 100:.2f}%)
  - SPDXID: {package_stats["SPDXID"]} out of {len(list_package_stats)} ({package_stats["SPDXID"] / len(list_package_stats) * 100:.2f}%)
  - versionInfo: {package_stats["versionInfo"]} out of {len(list_package_stats)} ({package_stats["versionInfo"] / len(list_package_stats) * 100:.2f}%)
  - packageFileName: {package_stats["packageFileName"]} out of {len(list_package_stats)} ({package_stats["packageFileName"] / len(list_package_stats) * 100:.2f}%)
  - downloadLocation: {package_stats["downloadLocation"]} out of {len(list_package_stats)} ({package_stats["downloadLocation"] / len(list_package_stats) * 100:.2f}%)
  - filesAnalyzed: {package_stats["filesAnalyzed"]} out of {len(list_package_stats)} ({package_stats["filesAnalyzed"] / len(list_package_stats) * 100:.2f}%)
  - homepage: {package_stats["homepage"]} out of {len(list_package_stats)} ({package_stats["homepage"] / len(list_package_stats) * 100:.2f}%)
  - supplier: {package_stats["supplier"]} out of {len(list_package_stats)} ({package_stats["supplier"] / len(list_package_stats) * 100:.2f}%)
  - originator: {package_stats["originator"]} out of {len(list_package_stats)} ({package_stats["originator"] / len(list_package_stats) * 100:.2f}%)
  - summary: {package_stats["summary"]} out of {len(list_package_stats)} ({package_stats["summary"] / len(list_package_stats) * 100:.2f}%)
  - description: {package_stats["description"]} out of {len(list_package_stats)} ({package_stats["description"] / len(list_package_stats) * 100:.2f}%)
  - md5: {package_stats["md5"]} out of {len(list_package_stats)} ({package_stats["md5"] / len(list_package_stats) * 100:.2f}%)
  - sha1: {package_stats["sha1"]} out of {len(list_package_stats)} ({package_stats["sha1"] / len(list_package_stats) * 100:.2f}%)
  - sha256: {package_stats["sha256"]} out of {len(list_package_stats)} ({package_stats["sha256"] / len(list_package_stats) * 100:.2f}%)
  - sha512: {package_stats["sha512"]} out of {len(list_package_stats)} ({package_stats["sha512"] / len(list_package_stats) * 100:.2f}%)
  - externalRefs: {package_stats["externalRefs"]} out of {len(list_package_stats)} ({package_stats["externalRefs"] / len(list_package_stats) * 100:.2f}%)
  - copyrightText: {package_stats["copyrightText"]} out of {len(list_package_stats)} ({package_stats["copyrightText"] / len(list_package_stats) * 100:.2f}%)
  - licenseConcluded: {package_stats["licenseConcluded"]} out of {len(list_package_stats)} ({package_stats["licenseConcluded"] / len(list_package_stats) * 100:.2f}%)
  - licenseDeclared: {package_stats["licenseDeclared"]} out of {len(list_package_stats)} ({package_stats["licenseDeclared"] / len(list_package_stats) * 100:.2f}%)
  - licenseComments: {package_stats["licenseComments"]} out of {len(list_package_stats)} ({package_stats["licenseComments"] / len(list_package_stats) * 100:.2f}%)
  - comment: {package_stats["comment"]} out of {len(list_package_stats)} ({package_stats["comment"] / len(list_package_stats) * 100:.2f}%)
  - copyright_stats: cannot_open:unknown_format:ok = {package_stats["copyright_cannot_open"]}:{package_stats["copyright_unknown_format"]}:{package_stats["copyright_ok"]} ({package_stats["copyright_cannot_open"] / len(list_package_stats) * 100:.2f}%:{package_stats["copyright_unknown_format"] / len(list_package_stats) * 100:.2f}%:{package_stats["copyright_ok"] / len(list_package_stats) * 100:.2f}%)"""
    )

    license_stat_str: str = (
        ""
        if len(list_license_stats) == 0
        else f"""- License metadata
  - licenseId: {license_stats["licenseId"]} out of {len(list_license_stats)} ({license_stats["licenseId"] / len(list_license_stats) * 100:.2f}%)
  - name: {license_stats["name"]} out of {len(list_license_stats)} ({license_stats["name"] / len(list_license_stats) * 100:.2f}%)
  - extractedText: {license_stats["extractedText"]} out of {len(list_license_stats)} ({license_stats["extractedText"] / len(list_license_stats) * 100:.2f}%)
  - comment: {license_stats["comment"]} out of {len(list_license_stats)} ({license_stats["comment"] / len(list_license_stats) * 100:.2f}%)"""
    )

    print(
        f"""=== Results ===
- Processed packages: {len(packages)} out of {len(list_package_stats)}
{package_stat_str}
- Unknown licenses: {len(list_license_stats)}
{license_stat_str}""",
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
) -> str:
    """Construct a whole SPDX document for the given package in the JSON format."""
    document_id = "SPDXRef-DOCUMENT"
    root_package_id = "SPDXRef-RootPackage"

    spdx: dict = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": document_id,
        "name": target_project,
        "documentNamespace": f"https://spdx.org/spdxdocs/c2sbom-{target_project}-{uuid.uuid4()}",
        "creationInfo": {
            "created": datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "creators": target_creators
            + [
                "Organization: Software Engineering Laboratory, Osaka University",
                "Tool: C2SBOM Preview",
            ],
        },
        "documentDescribes": [root_package_id],
        # "files": [],
        "packages": [
            {
                "name": target_project,
                "SPDXID": root_package_id,
                "filesAnalyzed": False,
                "downloadLocation": "NOASSERTION",
                "licenseConcluded": (
                    "NOASSERTION" if target_license is None else target_license
                ),
                "licenseDeclared": (
                    "NOASSERTION" if target_license is None else target_license
                ),
                "copyrightText": (
                    "NOASSERTION" if target_copyright is None else target_copyright
                ),
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

    list_package_stats: list[dict[str, bool]] = []
    list_license_stats: list[dict[str, bool]] = []

    for package, files in packages:
        print("Processing", package, file=sys.stderr)

        package_basename, arch = divide_package_name(package)
        package_meta, package_stats = get_metadata(package_basename, arch)

        comment, copyright_text, license_manager, tmp_stat = get_copyright.get_license(
            package_basename, arch
        )
        # licenseInfoFromFiles = license_manager.all_expr_str
        licenseDeclared = license_manager.all_expr_str_cat
        package_stats["copyright_status"] = tmp_stat

        if len(copyright_text) > 0:
            package_meta["copyrightText"] = copyright_text
            package_stats["copyrightText"] = True
        # if len(licenseInfoFromFiles) > 0:
        #    package_meta["licenseInfoFromFiles"] = licenseInfoFromFiles
        #    package_stats["licenseInfoFromFiles"] = True
        if len(licenseDeclared) > 0:
            package_meta["licenseDeclared"] = licenseDeclared
            package_stats["licenseDeclared"] = True
            package_meta["licenseConcluded"] = licenseDeclared
            package_stats["licenseConcluded"] = True
        if len(comment) > 0:
            package_meta["licenseComments"] = comment
            package_stats["licenseComments"] = True

        # for file in sorted(files):
        #    base_index = file.rindex(os.path.sep)
        #    file_basename = re.sub(r"[^0-9a-zA-Z\.\-]+", "-", file[base_index + 1 :])
        #    file_path = re.sub(r"[^0-9a-zA-Z\.\-]+", "-", file[:base_index])
        #
        #    try:
        #        with open(file, "rb") as fd:
        #            md5 = hashlib.md5(fd.read()).hexdigest()
        #            sha1 = hashlib.sha1(fd.read()).hexdigest()
        #            sha256 = hashlib.sha256(fd.read()).hexdigest()
        #            sha512 = hashlib.sha512(fd.read()).hexdigest()
        #    except OSError as e:
        #        print(
        #            f"Error: Cannot open '{file}': {e.strerror}, skipping it.",
        #            file=sys.stderr,
        #        )
        #        continue
        #
        #    file_meta = {
        #        "fileName": file,
        #        "SPDXID": f"SPDXRef-File-{file_path}--{file_basename}-{sha1}",
        #        "fileTypes": ["BINARY"],
        #        "checksums": [
        #            {"algorithm": "MD5", "checksumValue": md5},
        #            {"algorithm": "SHA1", "checksumValue": sha1},
        #            {"algorithm": "SHA256", "checksumValue": sha256},
        #            {"algorithm": "SHA512", "checksumValue": sha512},
        #        ],
        #        "licenseConcluded": (
        #            licenseDeclared if len(licenseDeclared) > 0 else "NOASSERTION"
        #        ),
        #        "licenseComments": comment,
        #    }
        #    spdx["files"].append(file_meta)
        #
        #    spdx["relationships"].append(
        #        {
        #            "relationshipType": "CONTAINS",
        #            "relatedSpdxElement": file_meta["SPDXID"],
        #            "spdxElementId": package_meta["SPDXID"],
        #        }
        #    )

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
                value.text = "No license required for any purpose; the work is not subject to copyright in any jurisdiction."
                if value.comment is None:
                    value.comment = "Using the text from https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/ since no license text is extracted."
                else:
                    value.comment += "\nUsing the text from https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/ since no license text is extracted."

            spdx["hasExtractedLicensingInfos"].append(
                {
                    "licenseId": license_ref,
                    "name": value.name,
                    "extractedText": (
                        "No text found for this license."
                        if value.text is None
                        else value.text
                    ),
                    "comment": "" if value.comment is None else value.comment,
                }
            )

            list_license_stats.append(
                {
                    "licenseId": True,
                    "name": True,
                    "extractedText": value.text is not None and len(value.text) > 0,
                    "comment": value.comment is not None and len(value.comment) > 0,
                }
            )

    print(file=sys.stderr)
    print_stats(packages, list_package_stats, list_license_stats)
    return json.dumps(spdx, ensure_ascii=False, indent=2)
