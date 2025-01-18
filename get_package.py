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

    return normalized_files


def map_files_to_packages(files: set[str]) -> list[tuple[str, set[str]]]:
    """
    Map files to their packages using the `dpkg -S` tool.

    Return a list of tuples that contain a package name
    as the first tuple item and a set of file names
    which belong to the package as the second tuple item.
    """
    packages: dict[str, set[str]] = {}

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


def get_metadata(package: str, arch: str) -> dict:
    """
    Return an SPDX package information item for the given package
    in a `dict`.
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

    comment: str = ""

    try:
        version = get_installed_version(package + ":" + arch)
        package_meta["versionInfo"] = version
    except RuntimeError as e:
        package_meta["comment"] = f"Error: {e}, not generating metadata."
        return package_meta

    try:
        filename, url = get_download_url(package + ":" + arch, version)
        package_meta["packageFileName"] = filename
        package_meta["downloadLocation"] = url
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
    except RuntimeError as e:
        comment += f"Warning: {e}, not including purl.\n"

    # Get many metadata
    apt_show = subprocess.run(
        f"apt-cache show '{package}:{arch}={version}'",
        shell=True,
        capture_output=True,
        text=True,
    )
    if apt_show.returncode != 0:
        package_meta["comment"] = (
            "Error: 'apt-cache show' failed, not generating metadata."
        )
        return package_meta

    package_meta["comment"] = comment.rstrip()

    index = 0
    lines = apt_show.stdout.splitlines()
    for line in lines:
        if line.startswith("Maintainer:"):
            package_meta["supplier"] = "Organization: " + line[11:].strip().replace(
                "<", "("
            ).replace(">", ")")
        elif line.startswith("Original-Maintainer:"):
            package_meta["originator"] = "Organization: " + line[20:].strip().replace(
                "<", "("
            ).replace(">", ")")
        elif line.startswith("Homepage:"):
            package_meta["homepage"] = line[9:].strip()
        elif line.startswith("Description-en:"):
            package_meta["summary"] = line[15:].strip()
            package_meta["description"] = read_description(lines, index + 1)
        elif line.startswith("MD5sum:"):
            package_meta.setdefault("checksums", [])
            package_meta["checksums"].append(
                {"algorithm": "MD5", "checksumValue": line[7:].strip()}
            )
        elif line.startswith("SHA1:"):
            sha1 = line[5:].strip()
            package_meta.setdefault("checksums", [])
            package_meta["checksums"].append(
                {"algorithm": "SHA1", "checksumValue": sha1}
            )
            package_meta["SPDXID"] = f"SPDXRef-Package--{sha1}"
        elif line.startswith("SHA256:"):
            package_meta.setdefault("checksums", [])
            package_meta["checksums"].append(
                {"algorithm": "SHA256", "checksumValue": line[7:].strip()}
            )
        elif line.startswith("SHA512:"):
            package_meta.setdefault("checksums", [])
            package_meta["checksums"].append(
                {"algorithm": "SHA512", "checksumValue": line[7:].strip()}
            )

        index += 1

    return package_meta


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

    for package, files in packages:
        package_basename, arch = divide_package_name(package)
        package_meta = get_metadata(package_basename, arch)

        comment, copyright_text, license_manager = get_copyright.get_license(
            package_basename, arch
        )
        # licenseInfoFromFiles = license_manager.all_expr_str
        licenseDeclared = license_manager.all_expr_str_cat

        if len(copyright_text) > 0:
            package_meta["copyrightText"] = copyright_text
        # if len(licenseInfoFromFiles) > 0:
        #    package_meta["licenseInfoFromFiles"] = licenseInfoFromFiles
        if len(licenseDeclared) > 0:
            package_meta["licenseDeclared"] = licenseDeclared
            package_meta["licenseConcluded"] = licenseDeclared
        if len(comment) > 0:
            package_meta["licenseComments"] = comment

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
                    "extractedText": "" if value.text is None else value.text,
                    "comment": "" if value.comment is None else value.comment,
                }
            )

    return json.dumps(spdx, ensure_ascii=False, indent=2)
