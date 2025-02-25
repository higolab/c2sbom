# Standard modules
import dataclasses, json, os, re, sys


@dataclasses.dataclass
class License:
    """
    Store data of an unknown license (not in the SPDX License List).
    """

    name: str
    text: str | None = None
    comment: str | None = None


class LicenseManager:
    """
    Manage all licenses appears for a package.
    """

    def __init__(self, package: str, no_license_heuristic: bool = False):
        # Package name.
        self.package = package

        # Whether `_normalize_name` should use a simple heuristic.
        self.no_license_heuristic = no_license_heuristic

        # All expressions for this package (tokenized).
        self.exprs: list[list[str]] = []

        # All unknown licenses (keys are `LicenseRef`).
        self.licenses: dict[str, License] = {}

        # Individual license names extracted in the previous invocation.
        self.last_licenses: list[str] = []

        # Maps license names in a `copyright` file to `LicenseRef`s.
        self.mapping: dict[str, str] = {}  # keys are in lower case

        # All license names appeared (for statistics).
        self.stats_all_licenses: set[str] = set()

        # Syntax error count (for statistics).
        self.stats_syntax_errors = 0

        # SPDX License List
        self.spdx_license_list: dict | None = None

        try:
            with open(
                os.path.dirname(__file__) + os.path.sep + "licenses.json",
                encoding="utf-8",
                errors="ignore",
            ) as fd:
                self.spdx_license_list = json.load(fd)
        except OSError as e:
            print("SPDX License List not available:", e, file=sys.stderr)

    def add_expr(self, expr: str) -> bool:
        """
        Parse a license expression string found in a Debian `copyright` file, add the result,
        and return the syntax validity.

        If the syntax validity is `False`, then this function treats the whole license expression as a single license.
        Blame package maintainers for not complying with the `copyright` file format specification.
        """
        tokens = self._tokenize(expr)
        tokens = self._validate(tokens)
        is_valid = tokens is not None
        if not is_valid:
            tokens = [expr]
            self.stats_syntax_errors += 1

        # Fix license names and register licenses
        i = 0
        self.last_licenses = []
        while i < len(tokens):
            if tokens[i] != "AND" and tokens[i] != "OR" and tokens[i] != "(" and tokens[i] != ")":
                tokens[i] = self._convert_name(tokens[i])
                self.last_licenses.append(tokens[i])
                self.stats_all_licenses.add(tokens[i])
            i += 1

        # Add the newly constructed expression avoiding a repetition
        if tokens not in self.exprs:
            self.exprs.append(tokens)

        return is_valid

    def _tokenize(self, expr: str) -> list[str]:
        """
        Tokenize the `expr` into tokens where `and`, `or`, and `,` are separate tokens if they appear
        at word boundaries. Otherwise, it captures everything as a single token until the next boundary.

        This tokenizer makes `and`/`or` operators upper case.
        """
        tokens: list[str] = []
        length = len(expr)

        i = 0
        while i < length:
            # Skip leading whitespace
            if expr[i].isspace():
                i += 1
                continue

            # Check for ','
            if expr[i] == ",":
                tokens.append(",")
                i += 1
                continue

            # Check for 'and/or' at a boundary
            if expr.startswith("and/or", i):
                end_idx = i + 6
                # Verify boundary before/after 'and'
                if (i == 0 or expr[i - 1].isspace() or expr[i - 1] == ",") and (
                    end_idx == length or expr[end_idx].isspace() or expr[end_idx] == ","
                ):
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
                    tokens.append("OR")
                    i = end_idx
                    continue

            # Otherwise, capture everything up to the next boundary (license name)
            token = ""
            while i < length and expr[i] != "," and not expr[i].isspace():
                token += expr[i]
                i += 1
            tokens.append(token)

        return tokens

    def _validate(self, tokens: list[str]) -> list[str] | None:
        """
        Parse license expression tokens and returns the resulting modified tokens.
        Return `None` if there are syntax errors.

        This function resolves `,` (comma) operators into `()`s (parentheses) and `AND`/`OR` operators.
        """
        result: list[str] = []
        i = 0
        state = "after_op"

        while i < len(tokens):
            if state == "after_op":
                if tokens[i] == "AND" or tokens[i] == "OR" or tokens[i] == ",":
                    return None

                elif tokens[i].lower() == "perl" and (i + 1 >= len(tokens) or tokens[i + 1] != "with"):
                    # As per https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
                    result.append("(")
                    result.append("GPL-1.0-or-later")
                    result.append("OR")
                    result.append("Artistic-1.0")
                    result.append(")")

                elif i + 1 < len(tokens) and tokens[i + 1] == "with":
                    # As we have no way to identify the exact license exception,
                    # just concatenate the with statement to form a single license name.
                    start = i
                    i += 2
                    while i < len(tokens):
                        if tokens[i] == "exception":
                            break
                        i += 1
                    else:
                        return None
                    result.append(" ".join(tokens[start : i + 1]))

                else:
                    result.append(tokens[i])

                state = "after_name"

            elif state == "after_name":
                if tokens[i] == "AND" or tokens[i] == "OR":
                    result.append(tokens[i])
                    state = "after_op"

                elif tokens[i] == ",":
                    state = "after_comma"

                else:
                    return None

            elif state == "after_comma":
                if tokens[i] == "AND":
                    # Search for the nearest "naked-AND" (or the start of the expession) backward.
                    j = len(result) - 1
                    nest = 0
                    while j > 0:
                        if result[j] == ")":
                            nest += 1
                        elif result[j] == "(":
                            nest -= 1
                        elif nest == 0 and result[j] == "AND":
                            j += 1
                            break
                        j -= 1

                    # Parenthesize from there.
                    result.insert(j, "(")
                    result.append(")")
                    result.append(tokens[i])
                    state = "after_op"

                elif tokens[i] == "OR":  # Meaningless, ignore
                    result.append(tokens[i])
                    state = "after_op"

                else:
                    result.append(",")  # Natural comma, resolved later
                    state = "after_op"
                    continue

            i += 1

        if state == "after_op":
            return None

        # Resolve natural commas
        i = 0
        while i < len(result):
            if result[i] == ",":
                j = i + 1
                while j < len(result):
                    if result[j] == "AND" or result[j] == "OR":
                        result[i] = result[j]
                        break
                    j += 1
                else:
                    return None
            i += 1

        return result

    def add_license_direct(self, text: str, comment: str | None = None, name: str | None = None) -> str:
        """
        Add a license text directly and return a `LicenseRef` assigned for it.

        Intended for unnamed licenses and Debian `copyright` files that are not
        in the standard format.
        """
        license_ref = self._gen_license_ref(name)

        self.exprs.append(license_ref)
        self.licenses[license_ref] = License("NOASSERTION", text.strip(), None if comment is None else comment.strip())
        self.stats_all_licenses.add(license_ref)

        return license_ref

    def _gen_license_ref(self, name: str | None = None) -> str:
        """
        Generate a new LicenseRef that does not conflicts with existing ones.
        """
        license_ref_base = (
            f"LicenseRef-{self.package.lower()}"
            if name is None
            else f"LicenseRef-{self.package.lower()}--{name.lower()}"
        )
        license_ref_base = re.sub(r"[^0-9a-zA-Z\.\-]+", "-", license_ref_base)
        license_ref = license_ref_base

        i = 1
        while license_ref in self.licenses:
            license_ref = f"{license_ref_base}-{i}"
            i += 1

        return license_ref

    def _normalize_name(self, name: str) -> str:
        """
        Return a normalized license name by making it lower case and removing trailing `.0`s.
        """
        prev = ""
        result = name.lower().replace(" ", "-")

        while prev != result:
            prev = result
            i = len(result) - 2

            while i >= 0:
                if result[i : i + 2] == ".0" and (i + 2 >= len(result) or result[i + 2] != "."):
                    result = result[:i] + result[i + 2 :]
                i -= 1

        return result

    def _convert_name(self, name: str, no_add: bool = False) -> str:
        """
        Match a license name appears in Debian `copyright` file into an SPDX license identifier
        with a simple heuristic, and assign a `LicenseRef` if no license matches.
        It skips the matching step if SPDX License List is not available.

        If `no_add` is `True`, then this function doesn't assign a new `LicenseRef`.
        """
        is_checked = False
        normalized = name

        if not self.no_license_heuristic:
            normalized = self._normalize_name(name)
            # Debian calls the MIT License as "Expat".
            if normalized == "expat":
                return "MIT"

            # Deprecated licenses
            if normalized == "bsd-2-clause-netbsd":
                return "BSD-2-Clause"
            if normalized == "bsd-2-clause-freebsd":
                return "BSD-2-Clause-Views"
            if normalized == "bzip2-1.0.5":
                return "bzip2-1.0.6"
            if normalized == "ecos-2":
                return "GPL-2.0-or-later WITH eCos-exception-2.0"
            if normalized == "nunit":
                return "MIT-advertising"
            if normalized == "standardml-nj":
                return "SMLNJ"
            if normalized == "wxwindows":
                return "LGPL-2.0-or-later WITH WxWindows-exception-3.1"
            if normalized == "net-snmp":
                is_checked = True  # Can't reliably modernize

            # Version number omissions
            if normalized == "apache":
                return "Apache-1.0"
            if normalized == "artistic":
                return "Artistic-1.0"
            if normalized == "cc-by":
                return "CC-BY-1.0"
            if normalized == "cc-by-sa":
                return "CC-BY-SA-1.0"
            if normalized == "cc-by-nd":
                return "CC-BY-ND-1.0"
            if normalized == "cc-by-nc":
                return "CC-BY-NC-1.0"
            if normalized == "cc-by-nc-sa":
                return "CC-BY-NC-SA-1.0"
            if normalized == "cc-by-nc-nd":
                return "CC-BY-NC-ND-1.0"
            if normalized == "cc0":
                return "CC0-1.0"
            if normalized == "cddl":
                return "CDDL-1.0"
            if normalized == "cpl":
                return "CPL-1.0"
            if normalized == "efl":
                return "EFL-1.0"
            if normalized == "lppl":
                return "LPPL-1.0"
            if normalized == "mpl":
                # As per https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
                return "MPL-1.1"
            if normalized == "python":
                # As per https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
                return "Python-2.0"
            if normalized == "qpl":
                return "QPL-1.0"
            if normalized == "zope":
                return "Zope-1.1"

            # Naming mismatches for GPL
            if normalized.startswith("gpl"):
                if normalized == "gpl" or normalized == "gpl-1":
                    return "GPL-1.0-only"
                if normalized == "gpl+" or normalized == "gpl-1+":
                    return "GPL-1.0-or-later"
                if normalized == "gpl-2":
                    return "GPL-2.0-only"
                if normalized == "gpl-2+":
                    return "GPL-2.0-or-later"
                if normalized == "gpl-3":
                    return "GPL-3.0-only"
                if normalized == "gpl-3+":
                    return "GPL-3.0-or-later"

            # Naming mismatches for AGPL
            elif normalized.startswith("agpl"):
                if normalized == "agpl" or normalized == "agpl-1":
                    return "AGPL-1.0-only"
                if normalized == "agpl+" or normalized == "agpl-1+":
                    return "AGPL-1.0-or-later"
                if normalized == "agpl-3":
                    return "AGPL-3.0-only"
                if normalized == "agpl-3+":
                    return "AGPL-3.0-or-later"

            # Naming mismatches for LGPL
            elif normalized.startswith("lgpl"):
                if normalized == "lgpl" or normalized == "lgpl-2":
                    return "LGPL-2.0-only"
                if normalized == "lgpl+" or normalized == "lgpl-2+":
                    return "LGPL-2.0-or-later"
                if normalized == "lgpl-2.1":
                    return "LGPL-2.1-only"
                if normalized == "lgpl-2.1+":
                    return "LGPL-2.1-or-later"
                if normalized == "lgpl-3":
                    return "LGPL-3.0-only"
                if normalized == "lgpl-3+":
                    return "LGPL-3.0-or-later"

            # Naming mismatches for GFDL no invariants
            elif normalized.startswith("gfdl-niv"):
                if normalized == "gfdl-niv" or normalized == "gfdl-niv-1.1":
                    return "GFDL-1.1-no-invariants-only"
                if normalized == "gfdl-niv+" or normalized == "gfdl-niv-1.1+":
                    return "GFDL-1.1-no-invariants-or-later"
                if normalized == "gfdl-niv-1.2":
                    return "GFDL-1.2-no-invariants-only"
                if normalized == "gfdl-niv-1.2+":
                    return "GFDL-1.2-no-invariants-or-later"
                if normalized == "gfdl-niv-1.3":
                    return "GFDL-1.3-no-invariants-only"
                if normalized == "gfdl-niv-1.3+":
                    return "GFDL-1.3-no-invariants-or-later"

            # Naming mismatches for GFDL invariants
            elif normalized.startswith("gfdl"):
                if normalized == "gfdl" or normalized == "gfdl-1.1":
                    return "GFDL-1.1-invariants-only"
                if normalized == "gfdl+" or normalized == "gfdl-1.1+":
                    return "GFDL-1.1-invariants-or-later"
                if normalized == "gfdl-1.2":
                    return "GFDL-1.2-invariants-only"
                if normalized == "gfdl-1.2+":
                    return "GFDL-1.2-invariants-or-later"
                if normalized == "gfdl-1.3":
                    return "GFDL-1.3-invariants-only"
                if normalized == "gfdl-1.3+":
                    return "GFDL-1.3-invariants-or-later"

        # Check if the license is in the SPDX License List
        if not is_checked and self.spdx_license_list is not None:
            for item in self.spdx_license_list["licenses"]:
                if self.no_license_heuristic:
                    current_name = name
                    spdx_name = item["licenseId"]
                else:
                    current_name = self._normalize_name(name)
                    spdx_name = self._normalize_name(item["licenseId"])

                if current_name == spdx_name:
                    return item["licenseId"]

        # Unknown License
        if normalized in self.mapping:
            return self.mapping[normalized]

        if no_add:
            return None

        license_ref = self._gen_license_ref(normalized)
        self.mapping[normalized] = license_ref
        self.licenses[license_ref] = License(name)
        return license_ref

    def _expr_to_str(self, expr: list[str]) -> tuple[str, bool]:
        """
        Return all license expressions as a list of strings.
        Also, check if the given expression requires parenthesis for concatenating with `AND` clause
        by searching for a "naked" `OR` clause.
        """
        expr_str = ""
        req_paren = False
        level = 0

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
        """
        Return all license expressions as a list of strings.
        """
        result: list[str] = []

        for tokens in self.exprs:
            expr, _ = self._expr_to_str(tokens)
            result.append(expr)

        return result

    @property
    def all_expr_str_cat(self) -> str:
        """
        Return all license expressions as a concatenated string.
        """
        result: str | None = None

        if len(self.exprs) == 0:
            return ""
        elif len(self.exprs) == 1:
            return self._expr_to_str(self.exprs[0])[0]

        expr_str, req_paren = self._expr_to_str(self.exprs[0])
        if req_paren:
            result = "(" + expr_str + ")"
        else:
            result = expr_str

        i = 1
        while i < len(self.exprs):
            expr_str, req_paren = self._expr_to_str(self.exprs[i])
            if req_paren:
                result += " AND (" + expr_str + ")"
            else:
                result += " AND " + expr_str
            i += 1

        return result

    def add_license_text(self, text: str, name: str | None = None):
        """
        Add a license text to the licenses in the last invocation of `add_expr`.
        Add to the license `name` instead if it is specified.
        """
        names = self.last_licenses if name is None else [name]

        for item in names:
            license_ref = item if item in self.licenses else self._convert_name(item, True)

            if license_ref is None or license_ref not in self.licenses:
                continue  # The specified license doesn't need license text

            if self.licenses[license_ref].text is None:
                self.licenses[license_ref].text = text.strip()
            else:
                self.licenses[license_ref].text += "\n" + text.strip()

    def add_license_comment(self, comment: str, name: str | None = None):
        """
        Add a license comment to the licenses in the last invocation of `add_expr`.
        Add to the license `name` instead if it is specified.
        """
        names = self.last_licenses if name is None else [name]

        for item in names:
            license_ref = item if item in self.licenses else self._convert_name(item, True)

            if license_ref is None or license_ref not in self.licenses:
                continue  # The specified license doesn't need license comment

            if self.licenses[license_ref].comment is None:
                self.licenses[license_ref].comment = comment.strip()
            else:
                self.licenses[license_ref].comment += "\n" + comment.strip()


def read_formatted_text(lines: list[str], start: int = 0) -> tuple[str, int]:
    """
    Read a formatted text from the second line as in the Debian `copyright` file and
    return the resulting string and the next line index in this order.
    """
    index = start
    result = ""

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
    Parse a Header stanza in a copyright file and return the comment, copyright text, `LicenseManager`,
    and the next line index in this order.

    Raise `RuntimeError` if the file is not in the standard format.
    """
    index = start

    is_format_validated = False
    while index < len(lines):
        if lines[index].startswith("Format:"):
            line_splitted = lines[index].split()
            if (
                len(line_splitted) != 2
                or line_splitted[1] != "https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
                and line_splitted[1] != "http://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
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
                is_valid = license_manager.add_expr(license_name)
                if not is_valid:
                    comment += "Syntax error(s) in the copyright file.\n"
                if len(result) > 0:
                    license_manager.add_license_text(result)
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
    Parse a Files stanza in a copyright file and return the comment, copyright text, `LicenseManager`,
    and the next line index in this order.
    """
    index = start

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
                is_valid = license_manager.add_expr(license_name)
                if not is_valid:
                    comment += "Syntax error(s) in the copyright file.\n"
                if len(result) > 0:
                    license_manager.add_license_text(result)
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
    index = start
    license_name: str | None = None
    comment: str | None = None

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
                    license_manager.add_license_text(result, license_name)

        elif len(lines[index].strip()) == 0:  # End of stanza
            index += 1
            break

        else:  # No interest in this field, just skip
            index += 1

    if license_name is None:
        raise RuntimeError("No name given for stand-alone license stanza")

    if comment is not None:
        license_manager.add_license_comment(comment, license_name)

    return license_manager, index


def get_license(
    package_basename: str, arch: str | None, no_license_heuristic: bool
) -> tuple[str, str, LicenseManager, str]:
    """
    Get license information from `/usr/share/doc/<package_basename>/copyright` and
    return the comment, copyright text, `LicenseManager`, and result in this order.

    If `copyright` file is not in the standard format,
    then this function assigns a `LicenseRef` to the whole text of the file.

    If the file is not available, then this function records a comment indicating it.
    """
    package_comment = ""
    copyright_text = ""
    license_manager = LicenseManager(
        package_basename if arch is None else package_basename + "-" + arch,
        no_license_heuristic,
    )
    index = 0

    try:
        with open(
            f"/usr/share/doc/{package_basename}/copyright",
            encoding="utf-8",
            errors="ignore",
        ) as f_rel:
            lines = f_rel.readlines()
    except OSError as e:
        print(f"Cannot open '/usr/share/doc/{package_basename}/copyright': {e.strerror}", file=sys.stderr)
        package_comment += (
            f"Cannot open '/usr/share/doc/{package_basename}/copyright': {e.strerror}, "
            f"not including license information."
        )
        return package_comment, copyright_text, license_manager, "cannot open"

    while index < len(lines):  # Skip blank lines
        if len(lines[index].strip()) != 0:
            break
        index += 1

    try:
        package_comment, copyright_text, license_manager, index = copyright_header_stanza(
            lines, package_comment, copyright_text, license_manager, index
        )
    except RuntimeError as e:
        license_manager.add_license_direct(
            "".join(lines),
            f"Including the content of '/usr/share/doc/{package_basename}/copyright' as-is, because: {e}.",
            "copyright",
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
            package_comment, copyright_text, license_manager, index = copyright_files_stanza(
                lines, package_comment, copyright_text, license_manager, index
            )

        elif lines[index].startswith("License:"):
            try:
                license_manager, index = copyright_license_stanza(lines, license_manager, index)
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
