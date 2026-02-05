#!/usr/bin/env python3

import argparse
import fnmatch
import functools
import logging
import multiprocessing
import os
import re
import string
import subprocess
import sys
import tempfile
import textwrap
import traceback
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import wsdiff
from pygments import token
from pygments.formatters import HtmlFormatter
from pygments.lexer import RegexLexer
from witchhazel import WitchHazelStyle

try:
    # Try importing kicad_mod to figure out whether the kicad-library-utils stuff is in path
    import kicad_mod  # NOQA: F401
except ImportError:
    if (
        common := Path(__file__).parent.parent.with_name("common").absolute()
    ) not in sys.path:
        sys.path.insert(0, str(common))
import jinja2
import kicad_mod  # NOQA: F811
import kicad_sym
import print_fp_properties
import print_sym_properties
import render_fp
import render_sym

ERROR_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<title>Diff error</title>
</head>
<body>
<h4>Python exception in diff formatter</h4>
<pre>${error}</pre>
</body>
"""

if __name__ == "__main__":
    loader = jinja2.FileSystemLoader(Path(__file__).parent.with_name("templates"))
else:
    loader = jinja2.PackageLoader("html_diff")
j2env = jinja2.Environment(loader=loader, autoescape=jinja2.select_autoescape())


class SexprLexer(RegexLexer):
    name = "KiCad S-Expression"
    aliases = ["sexp"]
    filenames = ["*.kicad_mod", "*.kicad_sym"]

    tokens = {
        "root": [
            (r"\s+", token.Whitespace),
            (r"[()]", token.Punctuation),
            (r"([+-]?\d+\.\d+)(?=[)\s])", token.Number),
            (r"(-?\d+)(?=[)\s])", token.Number),
            (r'"((?:[^"]|\\")*)"(?=[)\s])', token.String),
            (r'([^()"\s]+)(?=[)\s])', token.Name),
        ]
    }


def _construct_syntax_css() -> str:
    """
    Constructs some suitable light/dark mode CSS for the diff syntax highlighting.
    """
    light_css = HtmlFormatter(classprefix="wsd-", style="xcode").get_style_defs()
    dark_css = HtmlFormatter(classprefix="wsd-", style=WitchHazelStyle).get_style_defs()

    syntax_css = textwrap.dedent(f"""@media print, (prefers-color-scheme: light) {{
            {light_css}
        }}

        @media (prefers-color-scheme: dark) {{
            {dark_css}
        }}""")
    return syntax_css


def html_stacktrace(fun):
    @functools.wraps(fun)
    def wrapper(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except Exception as e:
            formatted_exc = "".join(traceback.format_exception(e))
            warnings.warn(f"Error formatting diff: {formatted_exc}")
            return string.Template(ERROR_TEMPLATE).substitute(error=formatted_exc)

    return wrapper


def button(title, url, _id=None):
    if _id:
        return f'<a id="{_id}" href="{url}" class="button link">{title}</a>'
    else:
        return f'<a href="{url}" class="button link">{title}</a>'


def button_if(title, url, _id=None):
    if url and _id:
        return f'<a id="{_id}" href="{url}" class="button link">{title}</a>'
    elif url:
        return f'<a href="{url}" class="button link">{title}</a>'
    else:
        return ""


def js_str_list(l):  # NOQA: E741
    js_template_strs = ["`" + elem.replace("$", r"\$") + "`" for elem in l if elem]
    return "[" + ", ".join(js_template_strs) + "]"


def get_unit_suffix(unit_num: int) -> str:
    """
    Get the suffix: A, B, ..., Z, AA, AB, ...

    Unit num is 1-based like unit indexes in KiCad
    """
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    unit_num -= 1  # convert to 0-based

    if unit_num < 0:
        raise ValueError("Unit number must be non-negative")

    suffix = ""
    while unit_num >= 0:
        suffix = alphabet[unit_num % 26] + suffix
        unit_num = unit_num // 26 - 1

    return suffix


def temporary_symbol_library(symbol_lines: list[str]) -> str:
    if symbol_lines and not symbol_lines[0].strip().startswith("(symbol"):
        warnings.warn(
            f"Leading garbage in same line before symbol definition or broken symbol index"  # NOQA: E501, F541
        )

    if symbol_lines and not symbol_lines[-1].strip().endswith(")"):
        warnings.warn(
            f"Trailing garbage in same line after symbol definition or broken symbol index"  # NOQA: E501, F541
        )

    content = "\n".join(symbol_lines)
    return f"(kicad_symbol_lib (version 20231120) (generator kicad_html_diff)\n{content}\n)"


def build_symlib_index(libfile: Path):
    """
    Yields the names and line ranges (start, end) of all symbols in a library.

    Note, end is the line after the last line of the symbol.
    """
    if not libfile.is_file():
        return

    lineno = 0
    last_start = 0
    last_name: str | None = None

    # Note that this exploits the KiCad v8+ formatting:
    # symbols always indent with exactly one tab, and end with "\t)".
    #
    # If it gets more complex, either we need to autodetect indentation
    # or do more complex parsing (or delegate to kicad API one day?)

    symbol_start_patt = re.compile(r'^\t\(symbol\s+"(\S+)"')

    for line in libfile.read_text().splitlines():

        # Start of a symbol?
        if match := re.match(symbol_start_patt, line):
            last_name = match.group(1)
            last_start = lineno

        # End of a symbol?
        elif line == "\t)":
            if last_name:
                yield last_name, (last_start, lineno + 1)
                last_name = None

        lineno += 1


def render_symbol_kicad_cli(libfile, symname, outdir):
    outdir.mkdir(parents=True, exist_ok=True)

    kicad_cli = os.environ.get("KICAD_CLI", "kicad-cli")
    try:
        cmd = [kicad_cli, "sym", "export", "svg"]

        if symname:
            cmd.extend(["-s", symname])

        cmd.extend(["-o", str(outdir), str(libfile)])

        subprocess.run(cmd, check=True, stdout=sys.stdout, stderr=sys.stderr)
    except FileNotFoundError:
        warnings.warn(
            "Cannot find kicad-cli, no reference screenshots will be exported."
        )


def render_footprint_kicad_cli(libdir: Path, fpname: str | None, outfile: Path):
    """
    Render a library (or a single footprint) using kicad-cli.
    """
    outfile.parent.mkdir(parents=True, exist_ok=True)

    kicad_cli = os.environ.get("KICAD_CLI", "kicad-cli")
    try:
        cmd = [kicad_cli, "fp", "export", "svg"]

        if fpname:
            cmd.extend(["--fp", fpname])

        cmd.extend(["-o", str(outfile), str(libdir)])

        subprocess.run(cmd, check=True, stdout=sys.stdout, stderr=sys.stderr)
    except FileNotFoundError:
        warnings.warn(
            "Cannot find kicad-cli, no reference screenshots will be exported."
        )


class BatchRenderLibrary:
    """
    Render a library of parts (symbols or footprints) using kicad-cli.

    This class is used to render a batch of parts from a library at once.
    This is radically faster than rendering each part individually in a
    separate kicad-cli invocation.
    """

    def __init__(self, libdir, outdir: Path):
        self.stems: set[str] = set()
        self.libdir = libdir
        self.outdir = outdir

    def add_stem(self, stem: str):
        self.stems.add(stem)

    def get_files_for_stem(self, stem) -> list[Path]:
        """
        Get all existing files for a given stem, in order as suitable
        (e.g. by unit for symbols).
        """
        raise NotImplementedError()

    def _clear_unwanted(self):

        # Can't be anything to delete if the output directory doesn't exist
        if not self.outdir.is_dir():
            return

        # find all SVG files in the output directory
        # that we didn't ask for and delete them
        wanted_files = set()

        for stem in self.stems:
            for file in self.get_files_for_stem(stem):
                wanted_files.add(file)

        for f in self.outdir.iterdir():
            if f.suffix == ".svg":
                if f not in wanted_files:
                    f.unlink()


class BatchRenderFootprints(BatchRenderLibrary):

    def render(self):

        fp: str | None = None

        # if there's only one footprint, we can render it directly
        if len(self.stems) == 1:
            fp = min(self.stems)

        render_footprint_kicad_cli(self.libdir, fp, self.outdir)

        self._clear_unwanted()

    def get_files_for_stem(self, stem):
        # Very simple: name and extension
        # no useful unit for FPs

        if self.outdir.is_dir():
            fn = self.outdir / f"{stem}.svg"
            if fn.is_file():
                return [fn]

        return []


class BatchRenderSymbols(BatchRenderLibrary):

    def render(self):

        # First, clear the output directory of any matching files
        # in case we deleted a unit

        for symname in self.stems:
            for file in self.get_files_for_stem(symname):
                file.unlink()

        sym: str | None = None

        # if there's only one symbol, we can render it directly
        if len(self.stems) == 1:
            sym = min(self.stems)

        render_symbol_kicad_cli(self.libdir, sym, self.outdir)

        self._clear_unwanted()

    def get_files_for_stem(self, stem):
        if not self.outdir.is_dir():
            return []

        if os.path.isfile(self.outdir / f"{stem}.svg"):
            return [self.outdir / f"{stem}.svg"]

        # Since V9, there's always a uniform unitN suffix
        regex = re.compile(f"{re.escape(stem)}_unit([0-9]+).svg")

        files = []
        for file in self.outdir.iterdir():
            if match := regex.match(file.name):
                files.append((int(match.group(1)), file))

        # Sort by the number in the filename
        files.sort(key=lambda x: x[0])
        # Return just the files
        return [file for _, file in files]


class HTMLDiff:

    output: Path
    name_glob: str
    changes_only: bool
    screenshot_dir: Path
    # If present, the directory where the diff old/new files are written to
    diff_svg_output_dir: Optional[Path]
    max_workers: int

    def __init__(
        self,
        output,
        meta,
        name_glob="*",
        changes_only=True,
        screenshot_dir=None,
        diff_svg_output_dir=None,
    ):
        self.output = output
        self.name_glob = name_glob
        self.changes_only = changes_only
        self.name_map = {}
        self.diff_index = []
        self.max_workers = 1

        if screenshot_dir is None:
            tmp = self.screenshot_tmpdir = tempfile.TemporaryDirectory()
            self.screenshot_dir = Path(tmp.name)
        else:
            self.screenshot_dir = screenshot_dir

        self.diff_svg_output_dir = diff_svg_output_dir

        if self.diff_svg_output_dir is not None:
            self.diff_svg_output_dir.mkdir(parents=True, exist_ok=True)

        if "CI_MERGE_REQUEST_ID" in os.environ:
            old_sha, _old_shortid = meta["old_git"]

            self.old_url = (
                f'{os.environ["CI_PROJECT_URL"]}/-/blob/{old_sha}/{meta["old_path"]}'
            )
            if "old_line_range" in meta:
                start, end = meta["old_line_range"]
                self.old_url += f"#L{start}-{end}"

            self.new_url = f'{os.environ["CI_MERGE_REQUEST_SOURCE_PROJECT_URL"]}/-/blob/{os.environ["CI_MERGE_REQUEST_SOURCE_BRANCH_NAME"]}/{meta["new_path"]}'  # NOQA: E501
            if "new_line_range" in meta:
                start, end = meta["new_line_range"]
                self.new_url += f"#L{start}-{end}"

            self.mr_url = f'{os.environ["CI_MERGE_REQUEST_PROJECT_URL"]}/-/merge_requests/{os.environ["CI_MERGE_REQUEST_IID"]}'  # NOQA: E501
        else:
            self.old_url = self.new_url = self.mr_url = None

        if meta.get("old_git") is not None:
            revname, commit_id = meta["old_git"]
            if meta["old_path"] == meta["new_path"]:
                self.source_revisions = (
                    f'Comparing {meta["new_path"]} against rev {commit_id}'
                )
            else:
                self.source_revisions = f'Comparing {meta["new_path"]} against {meta["old_path"]} at {commit_id}'  # NOQA: E501

            if revname:
                self.source_revisions += f" alias {revname}"
        else:
            self.source_revisions = (
                f'Comparing {meta["new_path"]} against {meta["old_path"]}'
            )

    def diff(self, old, new):
        old, new = Path(old), Path(new)

        if new.suffix == ".kicad_sym":

            print(f"Diffing symbol libraries {old} and {new}")

            if ":" in old.suffix or ":" in new.suffix:
                _suffix, _, old_part_name = old.suffix.partition(":")
                _suffix, _, new_part_name = new.suffix.partition(":")
                old = old.with_suffix(".kicad_sym")
                new = new.with_suffix(".kicad_sym")

            self.symlib_diff(old, new)

        elif new.suffix == ".kicad_mod":
            if self.name_glob:
                raise ValueError(
                    "Name globs are not supported when processing a single footprint only."
                )  # NOQA: E501

            if self.output is None:
                self.output = new.with_suffix(".diff")
            self.output.mkdir(exist_ok=True, parents=True)

            old_text, new_text = old.read_text(), new.read_text()

            part_name = new.stem

            if new.parent.suffix.lower() == ".pretty":
                lib_name = new.parent.stem
            else:
                lib_name = "<unknown library>"

            ref_fn = (
                self.screenshot_dir
                / f"{lib_name}.pretty"
                / f"{part_name}.kicad_mod.svg"
            )
            ref_svg = ""
            if ref_fn.is_file():
                ref_svg = ref_fn.read_text()
            else:
                try:
                    render_footprint_kicad_cli(new.parent, new.stem, ref_fn.parent)
                    ref_fn = ref_fn.with_name(f"{part_name}.svg")
                    ref_svg = ref_fn.read_text()
                except Exception as e:
                    warnings.warn(
                        f"Error exporting reference render using kicad-cli: {e}"
                    )

            html_file_path = self.output / new.with_suffix(".html").name
            html_file_path.write_text(
                self.mod_diff(
                    part_name=part_name,
                    lib_name=lib_name,
                    old_text=old_text,
                    new_text=new_text,
                    prev_diff="",
                    next_diff="",
                    ref_svg=ref_svg,
                )
            )

        elif new.suffix.startswith(".kicad_symdir"):
            if ":" in old.suffix or ":" in new.suffix:
                raise ValueError(
                    "Giving library item names via [library]:[item_name] is not supported. "
                    "To compare individual symbols, simply list their .kicad_sym files inside the .kicad_symdir directory."  # NOQA: E501
                )

            if self.output is None:
                self.output = new.with_suffix(".diff")
            self.output.mkdir(exist_ok=True, parents=True)

            self.symlib_diff(old, new)

        elif new.suffix == ".pretty":
            if ":" in old.suffix or ":" in new.suffix:
                raise ValueError(
                    "Giving library item names via [library]:[item_name] is only supported for symbol libraries."
                    "To compare individual footprints, simply list their .kicad_mod files inside the .pretty directory."  # NOQA: E501
                )

            if self.output is None:
                self.output = new.with_suffix(".diff")
            self.output.mkdir(exist_ok=True, parents=True)

            self.pretty_diff(old, new)

        else:
            raise ValueError(
                "Unhandled input type {new.suffix}. Supported formats are .kicad_sym, .kicad_mod and .pretty."
            )  # NOQA: E501

    @staticmethod
    def format_index(diff_index, part_name: str):

        index = ""
        prefetch = None
        prefetch_next = False

        for filename, created, changed, deleted in diff_index:
            classes = []
            if created:
                classes.append("created")
            elif deleted:
                classes.append("deleted")
            elif changed:
                classes.append("changed")
            else:
                classes.append("unchanged")

            if prefetch_next:
                prefetch = filename.name
                prefetch_next = False

            if filename.stem == part_name:
                classes.append("index-self")
                prefetch_next = True

            link = f'<a href="{filename.name}">{filename.stem}</a>'
            index += f'  <div class="{" ".join(classes)}">{link}</div>\n'

        return index, prefetch

    def _format_html_diff(
        self,
        part_name: str,
        lib_name: str,
        next_diff: str,
        prev_diff: str,
        enable_layers,
        hide_text_in_diff,
        unit_names=[],
        **kwargs,
    ):

        index, prefetch = self.format_index(self.diff_index, part_name)

        return j2env.get_template("diff.html").render(
            page_title=f"diff: {part_name} in {lib_name}",
            part_name=part_name,
            unit_names=unit_names,
            source_revisions=self.source_revisions,
            enable_layers="true" if enable_layers else "false",
            hide_text_in_diff="true" if hide_text_in_diff else "false",
            code_diff_css=wsdiff.MAIN_CSS,
            diff_syntax_css=_construct_syntax_css(),
            prev_button=button("<", prev_diff, _id="nav-bt-prev"),
            next_button=button(">", next_diff, _id="nav-bt-next"),
            diff_index=index,
            prefetch_url=prefetch,
            pipeline_button=button_if("Pipeline", os.environ.get("CI_PIPELINE_URL")),
            old_file_button=button_if("Old File", self.old_url),
            new_file_button=button_if("New File", self.new_url),
            merge_request_button=button_if("Merge Request", self.mr_url),
            **kwargs,
        )

    @html_stacktrace
    def mod_diff(
        self,
        part_name: str,
        lib_name: str,
        old_text: list[str],
        new_text: list[str],
        prev_diff: str,
        next_diff: str,
        ref_svg,
    ):

        old_mod = None
        new_mod = None
        old_svg_text = ""
        new_svg_text = ""

        if old_text:
            old_mod = kicad_mod.KicadMod(data=old_text)
            old_svg_text = render_fp.render_mod(old_mod)

        if new_text:
            new_mod = kicad_mod.KicadMod(data=new_text)
            new_svg_text = render_fp.render_mod(new_mod)

        # Write the SVGs to disk for debugging or use in other tools
        if self.diff_svg_output_dir is not None:
            old_svg_path = self.diff_svg_output_dir / f"{part_name}.old.svg"
            new_svg_path = self.diff_svg_output_dir / f"{part_name}.new.svg"

            if old_svg_text:
                old_svg_path.write_text(old_svg_text)

            if new_svg_text:
                new_svg_path.write_text(new_svg_text)

        properties_table = print_fp_properties.format_properties(old_mod, new_mod)

        return self._format_html_diff(
            part_name=part_name,
            lib_name=lib_name,
            next_diff=next_diff,
            prev_diff=prev_diff,
            enable_layers=True,
            canvas_background="#001023",
            hide_text_in_diff=True,
            properties_table=properties_table,
            code_diff=wsdiff.html_diff_block(
                old_text, new_text, filename="", lexer=SexprLexer()
            ),
            old_svg=js_str_list([old_svg_text]),
            new_svg=js_str_list([new_svg_text]),
            reference_svg=js_str_list([ref_svg]),
        )

    def _get_ref_fn(self, new_file):
        return (
            self.screenshot_dir
            / new_file.parent.name
            / f"{new_file.stem}.kicad_mod.svg"
        )

    def pretty_diff(self, old: Path, new: Path):
        self.diff_index, files = self._get_changed_stems(old, new, ".kicad_mod")

        os.makedirs(self.screenshot_dir / new.name, exist_ok=True)

        # Render reference SVGs all at once
        # This is a lot faster than rendering them one by one, even if we end up over-rendering
        renderer = BatchRenderFootprints(new, self.screenshot_dir / new.name)

        for new_file in files:
            renderer.add_stem(new_file.stem)

        try:
            renderer.render()
        except Exception as e:
            warnings.warn(f"Error exporting reference render using kicad-cli: {e}")

        with multiprocessing.Pool(processes=self.max_workers) as pool:

            args = []

            for i, new_file in enumerate(files):
                prev_file = self._diff_name(files[(i - 1) % len(files)]).name
                next_file = self._diff_name(files[(i + 1) % len(files)]).name
                out_file = self._diff_name(new_file)
                args.append((old, new_file, next_file, prev_file, out_file))
            try:
                pool.starmap(self._process_one_mod, args)
            except KeyboardInterrupt:
                pool.terminate()
                pool.join()
            except Exception as e:
                warnings.warn(f"Error processing footprints: {e}")

    def _process_one_mod(
        self,
        old: Path,
        new_file: Path,
        next_file: Path,
        prev_file: Path,
        out_file: Path,
    ):
        old_file = old / new_file.name
        old_text = old_file.read_text() if old_file.is_file() else ""
        new_text = new_file.read_text() if new_file.is_file() else ""

        ref_svg = ""

        if new_file.is_file():
            ref_fn = self._get_ref_fn(new_file)
            if ref_fn.is_file():
                ref_svg = ref_fn.read_text()
            else:
                ref_fn = ref_fn.with_name(f"{new_file.stem}.svg")
                ref_svg = ref_fn.read_text()

        diff_text = self.mod_diff(
            part_name=new_file.stem,
            lib_name=new_file.parent.stem,
            new_text=new_text,
            old_text=old_text,
            prev_diff=prev_file,
            next_diff=next_file,
            ref_svg=ref_svg,
        )
        out_file.write_text(diff_text)

    @dataclass
    class SymLibDiffInfo:
        """
        Metadata describing a symbol library diff.

        This might be for a packed or unpacked library.
        """

        new_lib_path: Path

        # Name of the new/current symbol library
        old_lib: kicad_sym.KicadLibrary
        new_lib: kicad_sym.KicadLibrary

    @dataclass
    class SymbolDiffInfo:
        """
        Information about the files related to a symbol diff
        for a single symbol.
        """

        # Output HTML file
        out_file: Path

        # Old and new kicad_sym file
        old_kicad_sym: Path | None
        new_kicad_sym: Path | None

        # Line ranges of the symbol in the old and new kicad_sym files, for code-level diffs
        old_lines: tuple[int, int]
        new_lines: tuple[int, int]

        # Name of the symbol in the new kicad_sym file
        new_name: str

        # Name of the symbol in the old kicad_sym file
        old_name: str

    def _diff_name(self, new_file: Path) -> Path:
        return self.output / new_file.with_suffix(".html").name

    def _get_changed_stems(
        self, old_dir: Path, new_dir: Path, extension: str
    ) -> tuple[list, list]:
        """
        Look for files with the given extension in the old and new directories, and return a list of their
        stems along with their change status (created, changed, deleted).
        """

        diff_index = []
        files = []

        new_files = set(new_dir.glob(f"*{extension}"))
        old_files = set(old_dir.glob(f"*{extension}"))

        all_stems = {f.stem for f in new_files.union(old_files)}

        for stem in sorted(list(all_stems)):

            # Skip if the name doesn't match the glob
            if not fnmatch.fnmatch(stem, self.name_glob):
                continue

            new_file = new_dir / f"{stem}{extension}"
            old_file = old_dir / f"{stem}{extension}"

            old_text = old_file.read_text() if old_file.is_file() else ""
            new_text = new_file.read_text() if new_file.is_file() else ""
            changed = old_text != new_text
            created = not old_file.is_file()
            deleted = not new_file.is_file()

            if self.changes_only and not changed:
                continue

            diff_index.append((self._diff_name(new_file), created, changed, deleted))
            files.append(new_file)

        return diff_index, files

    def _process_sym_diffs(
        self, symdir_info: SymLibDiffInfo, syms: list[SymbolDiffInfo]
    ):
        """
        Process a list of symbol diffs for a symbol library.
        """

        screenshot_subdir = self.screenshot_dir / symdir_info.new_lib_path.stem
        os.makedirs(screenshot_subdir, exist_ok=True)

        # Render reference SVGs all at once
        # This is a lot faster than rendering them one by one, even if we end up over-rendering
        renderer = BatchRenderSymbols(symdir_info.new_lib_path, screenshot_subdir)

        for diffed_sym in syms:
            # Don't try to render deleted symbols, since they won't be in the new library
            # and kicad-cli will error out
            if diffed_sym.new_lines != (0, 0):
                renderer.add_stem(diffed_sym.new_name)

        try:
            renderer.render()
        except Exception as e:
            warnings.warn(f"Error exporting reference render using kicad-cli: {e}")

        # Sort the symbols by their new name
        sorted_syms = sorted(syms, key=lambda s: s.new_name)

        with multiprocessing.Pool(processes=self.max_workers) as pool:

            args = []

            for i, sym_diff_info in enumerate(sorted_syms):

                prev_sym = sorted_syms[(i - 1) % len(sorted_syms)]
                next_sym = sorted_syms[(i + 1) % len(sorted_syms)]

                prev_file = self._diff_name(
                    prev_sym.old_kicad_sym / prev_sym.new_name
                ).name
                next_file = self._diff_name(
                    next_sym.new_kicad_sym / next_sym.new_name
                ).name

                unit_files = renderer.get_files_for_stem(sym_diff_info.new_name)
                args.append(
                    (symdir_info, sym_diff_info, unit_files, next_file, prev_file)
                )

            try:
                pool.starmap(self._process_one_sym, args)
            except KeyboardInterrupt:
                pool.terminate()
                pool.join()
            except Exception as e:
                warnings.warn(f"Error processing footprints: {e}")
                raise e

    def _get_symbol_diffs(
        self, old_kicad_sym_path: Path, new_kicad_sym_path: Path
    ) -> list[SymbolDiffInfo]:
        """
        Get all the symbol diff infos for the symbols in the given kicad_sym files.
        """
        if self.output is None:
            self.output = new_kicad_sym_path.with_suffix(".diff")
        self.output.mkdir(exist_ok=True, parents=True)

        # Get the raw s-expr lines of the symbol libraries for code-level diffs
        index_old = dict(build_symlib_index(old_kicad_sym_path))
        index_new = dict(build_symlib_index(new_kicad_sym_path))
        old_lines = (
            old_kicad_sym_path.read_text().splitlines()
            if old_kicad_sym_path.is_file()
            else []
        )
        new_lines = (
            new_kicad_sym_path.read_text().splitlines()
            if new_kicad_sym_path.is_file()
            else []
        )

        files: list[HTMLDiff.SymbolDiffInfo] = []

        to_diff = []

        # Add all the new items
        for name, (start, end) in index_new.items():
            if not fnmatch.fnmatch(name, self.name_glob):
                continue
            to_diff.append((name, (start, end)))

        # Add any deleted items
        for name, (start, end) in index_old.items():
            if not fnmatch.fnmatch(name, self.name_glob):
                continue
            if name not in index_new:
                to_diff.append((name, (0, 0)))

        # Sort in name order
        to_diff.sort(key=lambda x: x[0])

        for name, (start, end) in to_diff:

            old_name = self.name_map.get(name, name)
            old_start, old_end = index_old.get(old_name, (0, 0))

            changed = old_lines[old_start:old_end] != new_lines[start:end]

            if self.changes_only and not changed:
                continue

            out_file = self.output / f"{name}.html"

            files.append(
                self.SymbolDiffInfo(
                    out_file=out_file,
                    new_name=name,
                    new_lines=(start, end),
                    old_name=old_name,
                    old_lines=(old_start, old_end),
                    old_kicad_sym=old_kicad_sym_path,
                    new_kicad_sym=new_kicad_sym_path,
                )
            )

        return files

    def symlib_diff(self, old_symlib_path: Path, new_symlib_path: Path) -> None:
        """
        Diff two libraries containing symbols.

        These could be packed or unpacked.
        """

        old_lib = None
        new_lib = None

        if old_symlib_path.exists():
            old_lib = kicad_sym.KicadLibrary.from_path(filename=old_symlib_path)
        if new_symlib_path.exists():
            new_lib = kicad_sym.KicadLibrary.from_path(filename=new_symlib_path)

        # This is the common info about the library diff that applies to all
        # symbol diffs in this library.
        symdir_info = self.SymLibDiffInfo(
            old_lib=old_lib,
            new_lib=new_lib,
            new_lib_path=new_symlib_path,
        )

        # So now we know about a change library, but we need to extract
        # the actual symbols - do this for both old and new libraries in case they
        # have different contents or multiple symbols each. This means we can
        # track symbols across packing/unpacking, for example.

        sym_diff_infos: list[HTMLDiff.SymbolDiffInfo] = []

        # Look for files being added, removed or changed

        # If a .kicad_sym file is given, we treat it as its own packed library.
        if old_symlib_path.is_file():
            old_stem_search_dir = old_symlib_path.parent
        else:
            old_stem_search_dir = old_symlib_path

        if new_symlib_path.is_file():
            new_stem_search_dir = new_symlib_path.parent
        else:
            new_stem_search_dir = new_symlib_path

        # Looks for appearing, changing or disappearing .kicad_sym files
        self.diff_index, files = self._get_changed_stems(
            old_dir=old_stem_search_dir,
            new_dir=new_stem_search_dir,
            extension=".kicad_sym",
        )

        # Gather symbols from each separate .kicad_sym file and do a diff of each one
        for kicad_sym_file in files:
            old_kicad_sym_path = old_stem_search_dir / kicad_sym_file.name
            new_kicad_sym_path = new_stem_search_dir / kicad_sym_file.name

            sym_diff_infos += self._get_symbol_diffs(
                old_kicad_sym_path, new_kicad_sym_path
            )

        # Finally, process all the symbol diffs
        self._process_sym_diffs(symdir_info, sym_diff_infos)

    def _process_one_sym(
        self,
        symdir_diff_info: SymLibDiffInfo,
        sym_diff_info: SymbolDiffInfo,
        unit_files,
        next_file,
        prev_file,
    ):

        screenshots_content = [f.read_text() for f in unit_files]

        svgs_old = []
        svgs_new = []

        old_content = ""
        new_content = ""

        new_sym = None
        old_sym = None

        def _get_sym_data(kicad_sym_path: Path, sym_name: str):
            """
            Extract symbol data - the raw s-expr lines, the parsed symbol and the rendered SVGs,
            for a given symbol in a given kicad_sym file.
            """
            lib = kicad_sym.KicadLibrary.from_file(kicad_sym_path)
            content = kicad_sym_path.read_text()
            sym = lib.get_symbol(sym_name)

            svgs = [
                str(x) for x in render_sym.render_sym(sym, lib, default_style=False)
            ]

            return content, sym, svgs

        if sym_diff_info.old_lines != (0, 0):
            old_content, old_sym, svgs_old = _get_sym_data(
                sym_diff_info.old_kicad_sym, sym_diff_info.old_name
            )

        if sym_diff_info.new_lines != (0, 0):
            new_content, new_sym, svgs_new = _get_sym_data(
                sym_diff_info.new_kicad_sym, sym_diff_info.new_name
            )

        sexpr_diff = wsdiff.html_diff_block(
            old_content,
            new_content,
            filename="",
            lexer=SexprLexer(),
        )

        prop_table = print_sym_properties.format_properties(old_sym, new_sym)

        unit_names: list[str] = []

        # Currently, matching units between old and new is not done.
        # That's quite tricky as units can be added, removed or reordered.
        # For now, just show the unit names of the new symbol.
        if new_sym is not None:
            for unit in range(new_sym.unit_count):
                unit_name = new_sym.unit_names.get(unit + 1)
                unit_suffix = get_unit_suffix(unit + 1)

                if unit_name is not None:
                    # Still show the suffix as this may be useful when looking at ref-des
                    unit_name = f"{unit_suffix}: {unit_name}"
                else:
                    unit_name = f"Unit {unit_suffix}"

                unit_names.append(unit_name)

        sym_diff_info.out_file.write_text(
            self._format_html_diff(
                lib_name=symdir_diff_info.new_lib_path.stem,
                part_name=sym_diff_info.new_name,
                next_diff=next_file,
                prev_diff=prev_file,
                enable_layers=False,
                canvas_background="#e0e0e0",
                hide_text_in_diff=False,
                properties_table=prop_table,
                code_diff=sexpr_diff,
                old_svg=js_str_list(svgs_old),
                new_svg=js_str_list(svgs_new),
                reference_svg=js_str_list(screenshots_content),
                unit_names=unit_names,
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="""html-diff.py generates a visual, HTML-formatted diff between two libraries. It outputs one file per library item into a folder named after the library with suffix ".diff". Included in the diff are:

                                     * An S-Expression diff
                                     * A visual diff
                                     * A render using kicad-cli
                                     * For footprints: A layer-by-layer preview

                                     If kicad-cli is not in PATH, you can give its location by setting the KICAD_CLI environment variable.
                                     """  # NOQA: E501
    )  # NOQA: E501
    parser.add_argument(
        "base",
        nargs="?",
        default="HEAD",
        help="Old version to compare against."
        + " Format: [git_revision]:[library_or_mod_file]:[library_item]."
        + " All three are optional, defaults to taking the input file from git's HEAD."
        + " If the given parameter does not name an existing file or no git revision is given,"
        + " the file is taken from git's HEAD.",
    )
    parser.add_argument(
        "path",
        help="New version to compare. Format: [library_or_mod_file]:[library_item], with the item name optional.",
    )
    parser.add_argument(
        "-n",
        "--only-names",
        default="*",
        help="Only output symbols or footprints whose name matches the given glob",
    )
    parser.add_argument(
        "-u",
        "--unchanged",
        action="store_true",
        help="Also output unchanged symbols or footprints",
    )
    parser.add_argument(
        "-s",
        "--screenshot-dir",
        type=Path,
        help="Read (footprints) or write (symbols) screenshots generated with kicad-cli"
        + " to given directory instead of re-generating them on the fly.",
    )
    parser.add_argument(
        "-S",
        "--diff-svg-output-dir",
        type=Path,
        help="Write the diff A/B files to the given directory instead of a temporary directory.",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=1,
        help="Number of parallel jobs to run when rendering symbols or footprints. Default is 1, "
        "0 is use all available cores.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity. Can be given multiple times.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Where to output the diff. Must be a directory for symbol/footprint library comparisons,"
        + " and must be a file for individual symbol or footprint comparisons.",
    )
    args = parser.parse_args()

    path, path_name = Path(args.path), None
    base, base_name = Path(args.base), None

    meta = {}

    if args.verbose == 1:
        logging.basicConfig(level=logging.INFO)
    elif args.verbose > 1:
        logging.basicConfig(level=logging.DEBUG)

    if not (path.is_file() or path.is_dir()):
        logging.error(f'Path "{path}" does not exist or is not a file.')
        sys.exit(2)

    workers = args.jobs if args.jobs > 0 else multiprocessing.cpu_count()
    logging.info(f"Running with {workers} parallel jobs")

    try:
        if base.exists():
            if not path.exists():
                logging.error(f'File "{path}" does not exist.')
                sys.exit(2)

            meta["old_git"] = None
            meta["old_path"] = str(base)
            meta["new_path"] = str(path)

            html_diff = HTMLDiff(
                args.output,
                meta,
                args.only_names,
                changes_only=(not args.unchanged),
                screenshot_dir=args.screenshot_dir,
                diff_svg_output_dir=args.diff_svg_output_dir,
            )
            html_diff.max_workers = workers
            html_diff.diff(base, path)

        else:
            if (
                base.suffix.lower() in (".kicad_mod", ".kicad_symdir")
                and ":" not in args.base
            ):
                # This does not look like either "[git_revision]" or "[git_revision]:[path]"
                logging.error(f'File "{base}" does not exist.')
                sys.exit(2)

            base_rev, _, rest = args.base.partition(":")
            base_file, _, base_name = rest.rpartition(":")
            base_file = Path(base_file if base_file else args.path)
            base_rev = base_rev or "HEAD"

            try:
                proc = subprocess.run(
                    ["git", "rev-parse", "--short", base_rev],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=path.parent,
                )
                meta["old_git"] = (base_rev, proc.stdout.strip())

                proc = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=path.parent,
                )
                tl = meta["git_toplevel"] = Path(proc.stdout.strip())
                meta["old_path"] = str(base_file.absolute().relative_to(tl))
                meta["new_path"] = str(path.absolute().relative_to(tl))

            except subprocess.CalledProcessError as e:
                logging.error(
                    f"Error parsing git revision '{base_rev}': "
                    f"rc={e.returncode}\n{e.stderr.strip()}"
                )
                sys.exit(1)

            with tempfile.TemporaryDirectory(suffix=path.name) as tmpd:
                print(tmpd)
                tmpd = Path(tmpd)
                try:
                    ls_path = str(
                        base_file.absolute().relative_to(path.parent.absolute())
                    )
                    if path.is_dir():
                        ls_path += "/"

                    proc = subprocess.run(
                        ["git", "ls-tree", "--name-only", base_rev, ls_path],
                        check=True,
                        capture_output=True,
                        text=True,
                        cwd=path.parent,
                    )
                    for fn in proc.stdout.splitlines():
                        out_fn = tmpd / Path(fn).name
                        with out_fn.open("w") as outf:
                            subprocess.run(
                                ["git", "show", f"{base_rev}:{fn}"],
                                check=True,
                                stderr=subprocess.PIPE,
                                stdout=outf,
                                text=True,
                                cwd=path.parent,
                            )
                except subprocess.CalledProcessError as e:
                    logging.error(
                        f"Error checking out file '{base_file}' from git revision '{base_rev}': "
                        f"rc={e.returncode}\n{e.stderr.strip()}"
                    )
                    sys.exit(1)

                base = tmpd if path.is_dir() else tmpd / base_file.name

                html_diff = HTMLDiff(
                    args.output,
                    meta,
                    args.only_names,
                    changes_only=(not args.unchanged),
                    screenshot_dir=args.screenshot_dir,
                    diff_svg_output_dir=args.diff_svg_output_dir,
                )
                html_diff.max_workers = workers
                html_diff.diff(base, path)

    except ValueError as e:
        raise e
        print(e.args[0], file=sys.stderr)
        sys.exit(2)
