# Standard Modules
import re, subprocess, urllib.parse, uuid


def get_installed_version(package: str) -> str:
    """
    Return the installed version for the given package.
    """
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
        raise RuntimeError("Unexpected 'apt-get download --print-uris' output: " + dl.stdout)

    return dl_split[1], dl_split[0][1:-1]  # Trim quotes


def make_purl(package_basename: str, version: str, arch: str | None) -> str:
    """
    Construct a Package URL (purl) for the given package.
    Uses `/etc/os-release` file to extract the vendor and distro.
    """
    vendor: str | None = None
    distro: str | None = None

    try:
        with open("/etc/os-release", encoding="utf-8", errors="ignore") as f_rel:
            for line in f_rel:
                if line.startswith("ID="):
                    if line[4] == "'" or line[4] == '"':
                        vendor = line[4:-1].lower().strip()
                    else:
                        vendor = line[3:].lower().strip()
                elif line.startswith("VERSION_CODENAME="):
                    if line[18] == "'" or line[18] == '"':
                        distro = line[18:-1].lower().strip()
                    else:
                        distro = line[17:].lower().strip()
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

        return (
            "pkg:deb/"
            + urllib.parse.quote(vendor)
            + "/"
            + urllib.parse.quote(package_basename)
            + "@"
            + urllib.parse.quote(version)
            + qualifiers
        )


def read_description(lines: list[str], start: int = 0) -> str:
    """
    Read an extended description as in the Debian `control` file.
    """
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
        "licenseComments": "",
        "comment": "",
    }

    statistics: dict[str, bool | str | int] = {
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
        "licenseComments": False,
        "comment": False,
        "copyright_status": None,
        "license_count": 0,
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
        if (
            re.fullmatch(
                r"^(NONE"
                r"|NOASSERTION"
                r"|(((git|hg|svn|bzr)\+)?([^:/?#]+://)?"
                r"[a-z0-9]+([\-\.]{1}[a-z0-9]+){0,100}\.[a-z]{2,5}(:[0-9]{1,5})?(\/.*)?)"
                r"|(git\+git@[a-zA-Z0-9\.\-]+:[a-zA-Z0-9/\\.@\-]+)|(bzr\+lp:[a-zA-Z0-9\.\-]+))$",
                url,
            )
            is None
        ):
            comment += (
                f"Warning: Extracted download location '{url}' is invalid in SPDX, not including downloadLocation.\n"
            )
        else:
            package_meta["downloadLocation"] = url
            statistics["downloadLocation"] = True
    except RuntimeError as e:
        comment += f"Warning: {e}, not including packageFileName and downloadLocation.\n"

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
        package_meta["comment"] = "Error: 'apt-cache show' failed, not generating metadata."
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
                package_meta["supplier"] = "Organization: " + value.replace("<", "(").replace(">", ")")
                statistics["supplier"] = True
        elif line.startswith("Original-Maintainer:"):
            value = line[20:].strip()
            if len(value) > 0:
                package_meta["originator"] = "Organization: " + value.replace("<", "(").replace(">", ")")
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
                package_meta["checksums"].append({"algorithm": "MD5", "checksumValue": value})
                statistics["md5"] = True
        elif line.startswith("SHA1:"):
            value = line[5:].strip()
            if len(value) > 0:
                package_meta.setdefault("checksums", [])
                package_meta["checksums"].append({"algorithm": "SHA1", "checksumValue": value})
                statistics["sha1"] = True
                package_meta["SPDXID"] = f"SPDXRef-Package--{value}"
        elif line.startswith("SHA256:"):
            value = line[7:].strip()
            if len(value) > 0:
                package_meta.setdefault("checksums", [])
                package_meta["checksums"].append({"algorithm": "SHA256", "checksumValue": value})
                statistics["sha256"] = True
        elif line.startswith("SHA512:"):
            value = line[7:].strip()
            if len(value) > 0:
                package_meta.setdefault("checksums", [])
                package_meta["checksums"].append({"algorithm": "SHA512", "checksumValue": value})
                statistics["sha512"] = True

        index += 1

    return package_meta, statistics
