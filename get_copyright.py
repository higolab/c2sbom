# Standard modules
import dataclasses, json, os, re, sys


@dataclasses.dataclass
class License:
    """Stores data of an unknown license (not in the SPDX License List)."""

    name: str
    text: str | None = None
    comment: str | None = None


class LicenseManager:
    """Manages all licenses appears for a package."""

    def __init__(self, package: str):
        # Package name.
        self.package = package

        # All expressions for this package (tokenized).
        self.exprs: list[list[str]] = []

        # All unknown licenses (keys are `LicenseRef`).
        self.licenses: dict[str, License] = {}

        # Maps license names in a `copyright` file to `LicenseRef`s.
        self.mapping: dict[str, str] = {}  # keys are in lower case

        # SPDX License List
        self.spdx_license_list: dict | None = None

        try:
            with open(
                os.path.dirname(__file__) + os.path.sep + "licenses.json",
                encoding="utf-8",
            ) as fd:
                self.spdx_license_list = json.load(fd)
        except OSError as e:
            print("SPDX License List not available:", e, file=sys.stderr)

    def add_expr(self, expr: str) -> list[str]:
        """
        Parse a license expression string found in a Debian `copyright` file and
        add the result.

        Returns newly found individual license identifiers as a list of strings,
        not including any operators.

        This tokenizer splits `expr` into tokens where `and`, `or`, and `,` are
        separate tokens if they appear at word boundaries.
        Otherwise, it captures everything including spaces as a single token
        (license nane) until the next boundary.

        This tokenizer makes `and`/`or` operators upper case. Also, it resolves
        `,` (comma) operators into `()`s (parentheses) and `AND`/`OR` operators.
        """
        tokens: list[str] = []
        i: int = 0
        length: int = len(expr)
        prepare_paren: bool = False
        new_licenses: list[str] = []

        while i < length:
            # Skip leading whitespace
            if expr[i].isspace():
                i += 1
                continue

            # Check for ','
            #
            # A comma can mean two things;
            # a) changing the priority of `or`s and `and`s like `A or B, and C`
            # b) usual English manner like `A, B, and C`
            if expr[i] == ",":
                prepare_paren = True
                i += 1
                continue

            # Check for 'and/or' at a boundary
            if expr.startswith("and/or", i):
                end_idx = i + 6
                # Verify boundary before/after 'and'
                if (i == 0 or expr[i - 1].isspace() or expr[i - 1] == ",") and (
                    end_idx == length or expr[end_idx].isspace() or expr[end_idx] == ","
                ):
                    if prepare_paren:
                        prepare_paren = False
                        tokens.insert(0, "(")
                        tokens.append(")")
                    tokens.append("OR")
                    i = end_idx
                    continue

            # Check for 'and' at a boundary
            if expr.startswith("and", i):
                end_idx = i + 3
                # Verify boundary before/after 'and'
                if (i == 0 or expr[i - 1].isspace() or expr[i - 1] == ",") and (
                    end_idx == length or expr[end_idx].isspace() or expr[end_idx] == ","
                ):
                    if prepare_paren:
                        prepare_paren = False
                        tokens.insert(0, "(")
                        tokens.append(")")
                    tokens.append("AND")
                    i = end_idx
                    continue

            # Check for 'or' at a boundary
            if expr.startswith("or", i):
                end_idx = i + 2
                # Verify boundary before/after 'or'
                if (i == 0 or expr[i - 1].isspace() or expr[i - 1] == ",") and (
                    end_idx == length or expr[end_idx].isspace() or expr[end_idx] == ","
                ):
                    if prepare_paren:
                        prepare_paren = False
                        tokens.insert(0, "(")
                        tokens.append(")")
                    tokens.append("OR")
                    i = end_idx
                    continue

            # Otherwise, capture everything up to the next boundary (license name)
            if prepare_paren:
                prepare_paren = False
                tokens.append(",")  # Temporal
            start: int = i
            while i < length:
                if expr[i] == ",":
                    break
                if (
                    expr.startswith("and", i)
                    and (i == 0 or expr[i - 1].isspace() or expr[i - 1] == ",")
                    and (i + 3 == length or expr[i + 3].isspace() or expr[i + 3] == ",")
                ):
                    break
                if (
                    expr.startswith("or", i)
                    and (i == 0 or expr[i - 1].isspace() or expr[i - 1] == ",")
                    and (i + 2 == length or expr[i + 2].isspace() or expr[i + 2] == ",")
                ):
                    break
                i += 1
            token = expr[start:i].rstrip()
            if token.lower() == "perl":
                # As per https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
                tokens.append("(")
                tokens.append("GPL-1.0-or-later")
                tokens.append("OR")
                tokens.append("Artistic-1.0")
                tokens.append(")")
            else:
                tokens.append(token)

        # Resolve "natural" commas
        i = 0
        while i < len(tokens):
            if tokens[i] == ",":
                j: int = i + 1
                while j < len(tokens):
                    if tokens[j] == "AND" or tokens[j] == "OR":
                        tokens[i] = tokens[j]
                        break
                    j += 1
                else:  # It was just a license name with commas
                    j: int = i + 1
                    new_token: str = tokens[i - 1] + tokens[i]
                    while (
                        j < len(tokens)
                        and tokens[j] != "AND"
                        and tokens[j] != "OR"
                        and tokens[j] != "("
                        and tokens[j] != ")"
                    ):
                        new_token += (
                            tokens[j] if tokens[j] == "," else (" " + tokens[j])
                        )
                        j += 1
                    tokens[i - 1 : j] = [new_token]
            i += 1

        # Fix license names and register licenses
        i: int = 0
        while i < len(tokens):
            if (
                tokens[i] != "AND"
                and tokens[i] != "OR"
                and tokens[i] != "("
                and tokens[i] != ")"
            ):
                tokens[i] = self._convert_name(tokens[i])
                new_licenses.append(tokens[i])
            i += 1

        # Add the newly constructed expression avoiding a repetition
        if tokens not in self.exprs:
            self.exprs.append(tokens)

        return new_licenses

    def add_license_direct(
        self, text: str, comment: str | None = None, tokens: list[str] | None = None
    ) -> str:
        """
        Add a license text directly and return a `LicenseRef` assigned for it.

        Intended for unnamed licenses and Debian `copyright` files that are not
        in the standard format.
        """
        license_ref = self._gen_license_ref(tokens)

        self.exprs.append(license_ref)
        self.licenses[license_ref] = License(
            "NOASSERTION", text.strip(), None if comment is None else comment.strip()
        )

        return license_ref

    def _gen_license_ref(self, tokens: list[str] | None = None) -> str:
        """
        Generates a new LicenseRef that does not conflicts with existing ones.
        """
        license_ref_base = (
            f"LicenseRef-{self.package.lower()}"
            if tokens is None
            else f"LicenseRef-{self.package.lower()}--{'-'.join(tokens).lower()}"
        )
        license_ref_base = re.sub(r"[^0-9a-zA-Z\.\-]+", "-", license_ref_base)
        license_ref = license_ref_base

        i: int = 1
        while license_ref in self.licenses:
            license_ref = f"{license_ref_base}-{i}"
            i += 1

        return license_ref

    def _normalize_name(self, name: str) -> str:
        """
        Return a normalized license name by making it lower case and
        removing trailing `.0`s.
        """
        prev = ""
        result = name.lower()

        while prev != result:
            prev = result
            i = len(result) - 2

            while i >= 0:
                if result[i : i + 2] == ".0" and (
                    i + 2 >= len(result) or result[i + 2] != "."
                ):
                    result = result[:i] + result[i + 2 :]
                i -= 1

        return result

    def _convert_name(self, name: str, no_add: bool = False) -> str:
        """
        Match a license name appears in Debian `copyright` file into an SPDX license
        identifier with a simple heuristic, and assign a `LicenseRef` if no license
        matches. It skips the matching step if SPDX License List is not available.

        If `no_add` is `True`, then this function doesn't assign a new `LicenseRef`.
        """
        tokens = name.split()
        normalized = self._normalize_name(tokens[0])
        is_known: bool | None = None

        # Debian calls the MIT License as "Expat".
        if normalized == "expat":
            tokens[0] = "MIT"
            is_known = True

        # Deprecated licenses
        elif normalized == "bsd-2-clause-netbsd":
            tokens[0] = "BSD-2-Clause"
            is_known = True
        elif normalized == "bsd-2-clause-freebsd":
            tokens[0] = "BSD-2-Clause-Views"
            is_known = True
        elif normalized == "bzip2-1.0.5":
            tokens[0] = "bzip2-1.0.6"
            is_known = True
        elif len(tokens) == 1 and normalized == "ecos-2.0":
            tokens[0] = "GPL-2.0-or-later WITH eCos-exception-2.0"
            is_known = True
        elif normalized == "ecos-2.0":
            is_known = False
        elif normalized == "nunit":
            tokens[0] = "MIT-advertising"
            is_known = True
        elif normalized == "standardml-nj":
            tokens[0] = "SMLNJ"
            is_known = True
        elif len(tokens) == 1 and normalized == "wxwindows":
            tokens[0] = "LGPL-2.0-or-later WITH WxWindows-exception-3.1"
            is_known = True
        elif normalized == "wxwindows":
            is_known = False
        elif normalized == "net-snmp":
            is_known = False  # Can't reliably modernize

        # Version number omissions
        elif normalized == "apache":
            tokens[0] = "Apache-1.0"
            is_known = True
        elif normalized == "artistic":
            tokens[0] = "Artistic-1.0"
            is_known = True
        elif normalized == "cc-by":
            tokens[0] = "CC-BY-1.0"
            is_known = True
        elif normalized == "cc-by-sa":
            tokens[0] = "CC-BY-SA-1.0"
            is_known = True
        elif normalized == "cc-by-nd":
            tokens[0] = "CC-BY-ND-1.0"
            is_known = True
        elif normalized == "cc-by-nc":
            tokens[0] = "CC-BY-NC-1.0"
            is_known = True
        elif normalized == "cc-by-nc-sa":
            tokens[0] = "CC-BY-NC-SA-1.0"
            is_known = True
        elif normalized == "cc-by-nc-nd":
            tokens[0] = "CC-BY-NC-ND-1.0"
            is_known = True
        elif normalized == "cc0":
            tokens[0] = "CC0-1.0"
            is_known = True
        elif normalized == "cddl":
            tokens[0] = "CDDL-1.0"
            is_known = True
        elif normalized == "cpl":
            tokens[0] = "CPL-1.0"
            is_known = True
        elif normalized == "efl":
            tokens[0] = "EFL-1.0"
            is_known = True
        elif normalized == "lppl":
            tokens[0] = "LPPL-1.0"
            is_known = True
        elif normalized == "mpl":
            # As per https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
            tokens[0] = "MPL-1.1"
            is_known = True
        elif normalized == "python":
            # As per https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
            tokens[0] = "Python-2.0"
            is_known = True
        elif normalized == "qpl":
            tokens[0] = "QPL-1.0"
            is_known = True
        elif normalized == "zope":
            tokens[0] = "Zope-1.1"
            is_known = True

        # Naming mismatches for GPL
        elif normalized.startswith("gpl"):
            if normalized == "gpl" or normalized == "gpl-1":
                tokens[0] = "GPL-1.0-only"
                is_known = True
            elif normalized == "gpl+" or normalized == "gpl-1+":
                tokens[0] = "GPL-1.0-or-later"
                is_known = True
            elif normalized == "gpl-2":
                tokens[0] = "GPL-2.0-only"
                is_known = True
            elif normalized == "gpl-2+":
                tokens[0] = "GPL-2.0-or-later"
                is_known = True
            elif normalized == "gpl-3":
                tokens[0] = "GPL-3.0-only"
                is_known = True
            elif normalized == "gpl-3+":
                tokens[0] = "GPL-3.0-or-later"
                is_known = True

        # Naming mismatches for AGPL
        elif normalized.startswith("agpl"):
            if normalized == "agpl" or normalized == "agpl-1":
                tokens[0] = "AGPL-1.0-only"
                is_known = True
            elif normalized == "agpl+" or normalized == "agpl-1+":
                tokens[0] = "AGPL-1.0-or-later"
                is_known = True
            elif normalized == "agpl-3":
                tokens[0] = "AGPL-3.0-only"
                is_known = True
            elif normalized == "agpl-3+":
                tokens[0] = "AGPL-3.0-or-later"
                is_known = True

        # Naming mismatches for LGPL
        elif normalized.startswith("lgpl"):
            if normalized == "lgpl" or normalized == "lgpl-2":
                tokens[0] = "LGPL-2.0-only"
                is_known = True
            elif normalized == "lgpl+" or normalized == "lgpl-2+":
                tokens[0] = "LGPL-2.0-or-later"
                is_known = True
            elif normalized == "lgpl-2.1":
                tokens[0] = "LGPL-2.1-only"
                is_known = True
            elif normalized == "lgpl-2.1+":
                tokens[0] = "LGPL-2.1-or-later"
                is_known = True
            elif normalized == "lgpl-3":
                tokens[0] = "LGPL-3.0-only"
                is_known = True
            elif normalized == "lgpl-3+":
                tokens[0] = "LGPL-3.0-or-later"
                is_known = True

        # Naming mismatches for GFDL no invariants
        elif normalized.startswith("gfdl-niv"):
            if normalized == "gfdl-niv" or normalized == "gfdl-niv-1.1":
                tokens[0] = "GFDL-1.1-no-invariants-only"
                is_known = True
            elif normalized == "gfdl-niv+" or normalized == "gfdl-niv-1.1+":
                tokens[0] = "GFDL-1.1-no-invariants-or-later"
                is_known = True
            elif normalized == "gfdl-niv-1.2":
                tokens[0] = "GFDL-1.2-no-invariants-only"
                is_known = True
            elif normalized == "gfdl-niv-1.2+":
                tokens[0] = "GFDL-1.2-no-invariants-or-later"
                is_known = True
            elif normalized == "gfdl-niv-1.3":
                tokens[0] = "GFDL-1.3-no-invariants-only"
                is_known = True
            elif normalized == "gfdl-niv-1.3+":
                tokens[0] = "GFDL-1.3-no-invariants-or-later"
                is_known = True

        # Naming mismatches for GFDL invariants
        elif normalized.startswith("gfdl"):
            if normalized == "gfdl" or normalized == "gfdl-1.1":
                tokens[0] = "GFDL-1.1-invariants-only"
                is_known = True
            elif normalized == "gfdl+" or normalized == "gfdl-1.1+":
                tokens[0] = "GFDL-1.1-invariants-or-later"
                is_known = True
            elif normalized == "gfdl-1.2":
                tokens[0] = "GFDL-1.2-invariants-only"
                is_known = True
            elif normalized == "gfdl-1.2+":
                tokens[0] = "GFDL-1.2-invariants-or-later"
                is_known = True
            elif normalized == "gfdl-1.3":
                tokens[0] = "GFDL-1.3-invariants-only"
                is_known = True
            elif normalized == "gfdl-1.3+":
                tokens[0] = "GFDL-1.3-invariants-or-later"
                is_known = True

        # Check if the license is in the SPDX License List
        if is_known is None and self.spdx_license_list is not None:
            is_known = False
            for item in self.spdx_license_list["licenses"]:
                if self._normalize_name(tokens[0]) == self._normalize_name(
                    item["licenseId"]
                ):
                    tokens[0] = item["licenseId"]
                    is_known = True
                    break

        # License with exception or format violating license name
        if len(tokens) > 1:
            full_name = " ".join(tokens)
            if full_name.lower() not in self.mapping:
                if no_add:
                    return None
                else:
                    license_ref = self._gen_license_ref(tokens)
                    self.mapping[full_name.lower()] = license_ref
                    self.licenses[license_ref] = License(full_name)
            return self.mapping[full_name.lower()]

        # Well-known licese
        if is_known:
            return tokens[0]

        # Unknown License
        if tokens[0].lower() in self.mapping:
            return self.mapping[tokens[0].lower()]
        elif no_add:
            return None
        else:
            license_ref = self._gen_license_ref(tokens)
            self.mapping[tokens[0].lower()] = license_ref
            self.licenses[license_ref] = License(tokens[0])
            return self.mapping[tokens[0].lower()]

    def _expr_to_str(self, expr: list[str]) -> tuple[str, bool]:
        """
        Return all license expressions as a list of strings.
        Also, check if the given expression requires parenthesis
        for concatenating with `AND` clause.

        It does so by searching for a "naked" `OR` clause.
        """
        expr_str: str = ""
        req_paren: bool = False
        level: int = 0

        for token in expr:
            if token == "AND" or token == "OR":
                expr_str += " " + token + " "
            else:
                expr_str += token

            if token == "(":
                level += 1
            elif token == ")":
                level -= 1
            elif token == "OR" and level == 0:
                req_paren = True

        return expr_str, req_paren

    @property
    def all_expr_str(self) -> list[str]:
        """Return all license expressions as a list of strings."""
        result: list[str] = []

        for tokens in self.exprs:
            expr, _ = self._expr_to_str(tokens)
            result.append(expr)

        return result

    @property
    def all_expr_str_cat(self) -> str:
        """Return all license expressions as a concatenated string."""
        result: str = None

        if len(self.exprs) == 0:
            return ""
        elif len(self.exprs) == 1:
            return self._expr_to_str(self.exprs[0])[0]

        expr_str, req_paren = self._expr_to_str(self.exprs[0])
        if req_paren:
            result = "(" + expr_str + ")"
        else:
            result = expr_str

        i: int = 1
        while i < len(self.exprs):
            expr_str, req_paren = self._expr_to_str(self.exprs[i])
            if req_paren:
                result += " AND (" + expr_str + ")"
            else:
                result += " AND " + expr_str
            i += 1

        return result

    def add_license_text(self, name: str, text: str):
        """Add a license text to the specified license."""
        license_ref = name if name in self.licenses else self._convert_name(name, True)

        if license_ref is None or license_ref not in self.licenses:
            return  # The specified license doesn't need license text
        elif self.licenses[license_ref].text is None:
            self.licenses[license_ref].text = text.strip()
        else:
            self.licenses[license_ref].text += "\n" + text.strip()

    def add_license_comment(self, name: str, comment: str):
        """Add a license comment to the specified license."""
        license_ref = name if name in self.licenses else self._convert_name(name, True)

        if license_ref is None or license_ref not in self.licenses:
            return  # The specified license doesn't need license comment
        elif self.licenses[license_ref].comment is None:
            self.licenses[license_ref].comment = comment.strip()
        else:
            self.licenses[license_ref].comment += "\n" + comment.strip()


def read_formatted_text(lines: list[str], start: int = 0) -> tuple[str, int]:
    """
    Read a formatted text from the second line as in the Debian `copyright` file and
    return the resulting string and the next line index in this order.
    """
    index: int = start
    result: str = ""

    while index < len(lines):
        line_stripped = lines[index].strip()
        length = len(line_stripped)

        if lines[index].startswith(" .") and length > 0:  # Blank line
            result += "\n"
        elif lines[index].startswith(" ") and length > 0:  # Continuation
            result += line_stripped + "\n"
        else:  # End of field
            break

        index += 1

    return result, index


def copyright_header_stanza(
    lines: list[str],
    comment: str,
    copyright_text: str,
    license_manager: LicenseManager,
    start: int,
) -> tuple[str, str, LicenseManager, int]:
    """
    Parse a Header stanza in a copyright file and return the comment,
    copyright text, `LicenseManager`, and the next line index in this order.

    Raise `RuntimeError` if the file is not in the standard format.
    """
    index: int = start

    is_format_validated = False
    while index < len(lines):
        if lines[index].startswith("Format:"):
            line_splitted = lines[index].split()
            if (
                len(line_splitted) != 2
                or line_splitted[1]
                != "https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
                and line_splitted[1]
                != "http://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
            ):
                raise RuntimeError("Unknown copyright format:" + lines[index])
            is_format_validated = True
            index += 1

        elif lines[index].startswith("Comment:"):
            value = lines[index][8:].strip()
            if len(value) > 0:
                comment += value + "\n"
            result, index = read_formatted_text(lines, index + 1)
            if len(result) > 0:
                comment += result

        elif lines[index].startswith("License:"):
            license_name = lines[index][8:].strip()
            result, index = read_formatted_text(lines, index + 1)
            if len(license_name) > 0:
                new_licences = license_manager.add_expr(license_name)
                if len(result) > 0:
                    for item in new_licences:
                        license_manager.add_license_text(item, result)
            elif len(result) > 0:
                license_manager.add_license_direct(result)

        elif lines[index].startswith("Copyright:"):
            value = lines[index][10:].strip()
            if len(value) > 0:
                copyright_text += value + "\n"
            result, index = read_formatted_text(lines, index + 1)
            if len(result) > 0:
                copyright_text += result

        elif len(lines[index].strip()) == 0:  # End of stanza
            index += 1
            break

        else:  # No interest in this field, just skip
            index += 1

    if not is_format_validated:
        raise RuntimeError("Unknown copyright format")

    return comment, copyright_text, license_manager, index


def copyright_files_stanza(
    lines: list[str],
    comment: str,
    copyright_text: str,
    license_manager: LicenseManager,
    start: int,
) -> tuple[str, str, LicenseManager, int]:
    """
    Parse a Files stanza in a copyright file and return the comment,
    copyright text, `LicenseManager`, and the next line index in this order.
    """
    index: int = start

    while index < len(lines):
        if lines[index].startswith("Comment:"):
            value = lines[index][8:].strip()
            if len(value) > 0:
                comment += value + "\n"
            result, index = read_formatted_text(lines, index + 1)
            if len(result) > 0:
                comment += result

        elif lines[index].startswith("License:"):
            license_name = lines[index][8:].strip()
            result, index = read_formatted_text(lines, index + 1)
            if len(license_name) > 0:
                new_licences = license_manager.add_expr(license_name)
                if len(result) > 0:
                    for item in new_licences:
                        license_manager.add_license_text(item, result)
            elif len(result) > 0:
                license_manager.add_license_direct(result)

        elif lines[index].startswith("Copyright:"):
            value = lines[index][10:].strip()
            if len(value) > 0:
                copyright_text += value + "\n"
            result, index = read_formatted_text(lines, index + 1)
            if len(result) > 0:
                copyright_text += result

        elif len(lines[index].strip()) == 0:  # End of stanza
            index += 1
            break

        else:  # No interest in this field, just skip
            index += 1

    return comment, copyright_text, license_manager, index


def copyright_license_stanza(
    lines: list[str], license_manager: LicenseManager, start: int
) -> tuple[LicenseManager, int]:
    """
    Parse a Stand-alone License stanza in a copyright file and
    return the `LicenseManager` and the next line index in this order.

    Raise `RuntimeError` if no `License:` field is found.
    """
    index: int = start
    license_name: str = None
    comment: str = None

    while index < len(lines):
        if lines[index].startswith("Comment:"):
            value = lines[index][8:].strip()
            if len(value) > 0:
                comment = value + "\n"
            result, index = read_formatted_text(lines, index + 1)
            if len(result) > 0:
                if comment is None:
                    comment = result
                else:
                    comment += result

        elif lines[index].startswith("License:"):
            value = lines[index][8:].strip()
            result, index = read_formatted_text(lines, index + 1)
            if len(value) > 0:
                license_name = value
                if len(result) > 0:
                    license_manager.add_license_text(license_name, result)

        elif len(lines[index].strip()) == 0:  # End of stanza
            index += 1
            break

        else:  # No interest in this field, just skip
            index += 1

    if license_name is None:
        raise RuntimeError("No name given for stand-alone license stanza")

    if comment is not None:
        license_manager.add_license_comment(license_name, comment)

    return license_manager, index


def get_license(
    package_basename: str, arch: str | None
) -> tuple[str, str, LicenseManager, str]:
    """
    Get license information from `/usr/share/doc/<package_basename>/copyright` and
    return the comment, copyright text, and `LicenseManager` in this order.

    If `copyright` file is not in the standard format,
    then this function assigns a `LicenseRef` to the whole text of the file.

    If the file is not available,
    then this function records a comment indicating it.
    """
    package_comment: str = ""
    copyright_text: str = ""
    license_manager = LicenseManager(
        package_basename if arch is None else package_basename + "-" + arch
    )
    index: int = 0

    try:
        with open(
            f"/usr/share/doc/{package_basename}/copyright", encoding="utf-8"
        ) as f_rel:
            lines = f_rel.readlines()
    except IOError as e:
        package_comment += f"Cannot open '/usr/share/doc/{package_basename}/copyright': {e.strerror}, not including license information."
        return package_comment, copyright_text, license_manager, "cannot open"

    while index < len(lines):  # Skip blank lines
        if len(lines[index].strip()) != 0:
            break
        index += 1

    try:
        package_comment, copyright_text, license_manager, index = (
            copyright_header_stanza(
                lines, package_comment, copyright_text, license_manager, index
            )
        )
    except RuntimeError as e:
        license_manager.add_license_direct(
            "".join(lines),
            f"Including the content of '/usr/share/doc/{package_basename}/copyright' as-is, because: {e}.",
            ["copyright"],
        )
        return package_comment, copyright_text, license_manager, "unknown format"

    while index < len(lines):
        while index < len(lines):  # Skip blank lines
            if len(lines[index].strip()) != 0:
                break
            index += 1
        else:
            break

        if lines[index].startswith("Files:"):
            package_comment, copyright_text, license_manager, index = (
                copyright_files_stanza(
                    lines, package_comment, copyright_text, license_manager, index
                )
            )

        elif lines[index].startswith("License:"):
            try:
                license_manager, index = copyright_license_stanza(
                    lines, license_manager, index
                )
            except RuntimeError as e:
                package_comment += f"{e}\n"
                index += 1

        else:  # Unknown stanza
            while index < len(lines):  # Skip a stanza
                if len(lines[index].strip()) == 0:
                    break
                index += 1
            else:
                break

    return package_comment.strip(), copyright_text.strip(), license_manager, "ok"
