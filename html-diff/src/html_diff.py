#!/usr/bin/env python3

import tempfile
import string
import functools
import traceback
import warnings
import sys
import os
import re
import argparse
import subprocess
from pathlib import Path
import fnmatch
from typing import Optional
import multiprocessing
import logging
from dataclasses import dataclass


from pygments.lexer import RegexLexer
from pygments import token
import wsdiff

try:
    # Try importing kicad_mod to figure out whether the kicad-library-utils stuff is in path
    import kicad_mod  # NOQA: F401
except ImportError:
    if (common := Path(__file__).parent.parent.with_name('common').absolute()) not in sys.path:
        sys.path.insert(0, str(common))
import kicad_sym

import print_fp_properties
import print_sym_properties
import render_fp
import render_sym
import jinja2


ERROR_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
<title>Diff error</title>
</head>
<body>
<h4>Python exception in diff formatter</h4>
<pre>${error}</pre>
</body>
'''

if __name__ == '__main__':
    loader = jinja2.FileSystemLoader(Path(__file__).parent.with_name('templates'))
else:
    loader = jinja2.PackageLoader('html_diff')
j2env = jinja2.Environment(loader=loader, autoescape=jinja2.select_autoescape())


class SexprLexer(RegexLexer):
    name = 'KiCad S-Expression'
    aliases = ['sexp']
    filenames = ['*.kicad_mod', '*.kicad_sym']

    tokens = {
        'root': [
            (r'\s+', token.Whitespace),
            (r'[()]', token.Punctuation),
            (r'([+-]?\d+\.\d+)(?=[)\s])', token.Number),
            (r'(-?\d+)(?=[)\s])', token.Number),
            (r'"((?:[^"]|\\")*)"(?=[)\s])', token.String),
            (r'([^()"\s]+)(?=[)\s])', token.Name),
        ]
    }


def html_stacktrace(fun):
    @functools.wraps(fun)
    def wrapper(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except Exception as e:
            warnings.warn(f'Error formatting diff: {traceback.format_exception(e)}')
            return string.Template(ERROR_TEMPLATE).substitute(
                error=''.join(traceback.format_exception(e)))
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
        return ''


def js_str_list(l):  # NOQA: E741
    js_template_strs = ["`" + elem.replace('$', r'\$') + "`" for elem in l if elem]
    return '[' + ', '.join(js_template_strs) + ']'


def temporary_symbol_library(symbol_lines: list[str]) -> str:
    if symbol_lines and not symbol_lines[0].strip().startswith('(symbol'):
        warnings.warn(f'Leading garbage in same line before symbol definition or broken symbol index')  # NOQA: E501, F541

    if symbol_lines and not symbol_lines[-1].strip().endswith(')'):
        warnings.warn(f'Trailing garbage in same line after symbol definition or broken symbol index')  # NOQA: E501, F541

    content = '\n'.join(symbol_lines)
    return f'(kicad_symbol_lib (version 20231120) (generator kicad_html_diff)\n{content}\n)'


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

    kicad_cli = os.environ.get('KICAD_CLI', 'kicad-cli')
    try:
        cmd = [kicad_cli, 'sym', 'export', 'svg']

        if symname:
            cmd.extend(['-s', symname])

        cmd.extend(['-o', str(outdir), str(libfile)])

        subprocess.run(cmd, check=True, stdout=sys.stdout, stderr=sys.stderr)
    except FileNotFoundError:
        warnings.warn('Cannot find kicad-cli, no reference screenshots will be exported.')


def render_footprint_kicad_cli(libdir: Path, fpname: str | None, outfile: Path):
    """
    Render a library (or a single footprint) using kicad-cli.
    """
    outfile.parent.mkdir(parents=True, exist_ok=True)

    kicad_cli = os.environ.get('KICAD_CLI', 'kicad-cli')
    try:
        cmd = [kicad_cli, 'fp', 'export', 'svg']

        if fpname:
            cmd.extend(['--fp', fpname])

        cmd.extend(['-o', str(outfile), str(libdir)])

        subprocess.run(cmd, check=True, stdout=sys.stdout, stderr=sys.stderr)
    except FileNotFoundError:
        warnings.warn('Cannot find kicad-cli, no reference screenshots will be exported.')


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
            if f.suffix == '.svg':
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
            fn = self.outdir / f'{stem}.svg'
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
        # Why lower(), IDK but it's a kicad-cli thing
        stem = stem.lower()

        if not self.outdir.is_dir():
            return []

        if os.path.isfile(self.outdir / f'{stem}.svg'):
            return [self.outdir / f'{stem}.svg']

        # A little sus in pathological cases, in 8.0 but it applies to
        # only a small number of symbols (e.g. HDSP-4830)
        # https://gitlab.com/kicad/code/kicad/-/issues/18929
        regex = re.compile(f'{re.escape(stem)}(?:_unit|_)?([0-9]+).svg')

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

        if 'CI_MERGE_REQUEST_ID' in os.environ:
            old_sha, _old_shortid = meta["old_git"]

            self.old_url = f'{os.environ["CI_PROJECT_URL"]}/-/blob/{old_sha}/{meta["old_path"]}'
            if 'old_line_range' in meta:
                start, end = meta['old_line_range']
                self.old_url += f'#L{start}-{end}'

            self.new_url = f'{os.environ["CI_MERGE_REQUEST_SOURCE_PROJECT_URL"]}/-/blob/{os.environ["CI_MERGE_REQUEST_SOURCE_BRANCH_NAME"]}/{meta["new_path"]}'  # NOQA: E501
            if 'new_line_range' in meta:
                start, end = meta['new_line_range']
                self.new_url += f'#L{start}-{end}'

            self.mr_url = f'{os.environ["CI_MERGE_REQUEST_PROJECT_URL"]}/-/merge_requests/{os.environ["CI_MERGE_REQUEST_IID"]}'  # NOQA: E501
        else:
            self.old_url = self.new_url = self.mr_url = None

        if meta.get("old_git") is not None:
            revname, commit_id = meta["old_git"]
            if meta['old_path'] == meta['new_path']:
                self.source_revisions = f'Comparing {meta["new_path"]} against rev {commit_id}'
            else:
                self.source_revisions = f'Comparing {meta["new_path"]} against {meta["old_path"]} at {commit_id}'  # NOQA: E501

            if revname:
                self.source_revisions += f' alias {revname}'
        else:
            self.source_revisions = f'Comparing {meta["new_path"]} against {meta["old_path"]}'

    def diff(self, old, new):
        old, new = Path(old), Path(new)

        if new.suffix.startswith('.kicad_sym'):
            if ':' in old.suffix or ':' in new.suffix:
                _suffix, _, old_part_name = old.suffix.partition(':')
                _suffix, _, new_part_name = new.suffix.partition(':')
                old = old.with_suffix('.kicad_sym')
                new = new.with_suffix('.kicad_sym')

                if '*' in old_part_name or '*' in new_part_name:
                    raise ValueError("part name can't be a glob")

                if self.name_glob:
                    raise ValueError('Only either a part name filter or an individual symbol can be given, not both.')  # NOQA: E501

                if not new_part_name:
                    if not old_part_name:
                        raise ValueError('No part name given')

                    self.name_glob = old_part_name

                elif not old_part_name:
                    self.name_glob = new_part_name

                else:
                    self.name_glob = new_part_name
                    self.name_map = {new_part_name: old_part_name}

            # Check entire (updated) library for inconsistencies:
            # Check if all parent symbols appear before the child symbols
            new_library_data = new.read_text()
            lib = kicad_sym.KicadLibrary.from_file(new, new_library_data)
            lib.check_extends_order()

            self.symlib_diff(old, new)

        elif new.suffix == '.kicad_mod':
            if self.name_glob:
                raise ValueError('Name globs are not supported when processing a single footprint only.')  # NOQA: E501

            if self.output is None:
                self.output = new.with_suffix('.diff')
            self.output.mkdir(exist_ok=True, parents=True)

            old_text, new_text = old.read_text(), new.read_text()

            part_name = new.stem

            if new.parent.suffix.lower() == '.pretty':
                lib_name = new.parent.stem
            else:
                lib_name = '<unknown library>'

            ref_fn = self.screenshot_dir / f'{lib_name}.pretty' / f'{part_name}.kicad_mod.svg'
            ref_svg = ''
            if ref_fn.is_file():
                ref_svg = ref_fn.read_text()
            else:
                try:
                    render_footprint_kicad_cli(new.parent, new.stem, ref_fn.parent)
                    ref_fn = ref_fn.with_name(f'{part_name}.svg')
                    ref_svg = ref_fn.read_text()
                except Exception as e:
                    warnings.warn(f'Error exporting reference render using kicad-cli: {e}')

            html_file_path = self.output / new.with_suffix('.html').name
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

        elif new.suffix == '.pretty':
            if ':' in old.suffix or ':' in new.suffix:
                raise ValueError('Giving library item names via [library]:[item_name] is only supported for symbol libraries. To compare individual footprints, simply list their .kicad_mod files inside the .pretty directory.')  # NOQA: E501

            if self.output is None:
                self.output = new.with_suffix('.diff')
            self.output.mkdir(exist_ok=True, parents=True)

            self.pretty_diff(old, new)

        else:
            raise ValueError('Unhandled input type {new.suffix}. Supported formats are .kicad_sym, .kicad_mod and .pretty.')  # NOQA: E501

    @staticmethod
    def format_index(diff_index, part_name: str):

        index = ""
        prefetch = None
        prefetch_next = False

        for filename, created, changed, deleted in diff_index:
            classes = []
            if created:
                classes.append('created')
            elif deleted:
                classes.append('deleted')
            elif changed:
                classes.append('changed')
            else:
                classes.append('unchanged')

            if prefetch_next:
                prefetch = filename.name
                prefetch_next = False

            if filename.stem == part_name:
                classes.append('index-self')
                prefetch_next = True

            link = f'<a href="{filename.name}">{filename.stem}</a>'
            index += f'  <div class="{" ".join(classes)}">{link}</div>\n'

        return index, prefetch

    def _format_html_diff(self, part_name: str, lib_name: str,
                          next_diff: str, prev_diff: str,
                          enable_layers, hide_text_in_diff, **kwargs):

        index, prefetch = self.format_index(self.diff_index, part_name)

        return j2env.get_template('diff.html').render(
            page_title = f'diff: {part_name} in {lib_name}',
            part_name = part_name,
            source_revisions = self.source_revisions,
            enable_layers = 'true' if enable_layers else 'false',
            hide_text_in_diff = 'true' if hide_text_in_diff else 'false',

            code_diff_css=wsdiff.MAIN_CSS,
            diff_syntax_css=wsdiff.PYGMENTS_CSS,

            prev_button = button('<', prev_diff, _id='nav-bt-prev'),
            next_button = button('>', next_diff, _id='nav-bt-next'),
            diff_index = index,
            prefetch_url = prefetch,

            pipeline_button = button_if('Pipeline', os.environ.get('CI_PIPELINE_URL')),
            old_file_button = button_if('Old File', self.old_url),
            new_file_button = button_if('New File', self.new_url),
            merge_request_button = button_if('Merge Request', self.mr_url),
            **kwargs
        )

    @html_stacktrace
    def mod_diff(self, part_name: str, lib_name: str,
                 old_text: list[str], new_text: list[str],
                 prev_diff: str, next_diff: str,
                 ref_svg):

        old_svg_text = render_fp.render_mod(old_text)
        new_svg_text = render_fp.render_mod(new_text)

        # Write the SVGs to disk for debugging or use in other tools
        if self.diff_svg_output_dir is not None:
            old_svg_path = self.diff_svg_output_dir / f'{part_name}.old.svg'
            new_svg_path = self.diff_svg_output_dir / f'{part_name}.new.svg'
            old_svg_path.write_text(old_svg_text)
            new_svg_path.write_text(new_svg_text)

        return self._format_html_diff(
            part_name=part_name,
            lib_name=lib_name,
            next_diff=next_diff,
            prev_diff=prev_diff,
            enable_layers=True,
            canvas_background='#001023',
            hide_text_in_diff=True,
            properties_table=print_fp_properties.format_properties(new_text),
            code_diff=wsdiff.html_diff_block(old_text, new_text,
                                             filename='', lexer=SexprLexer()),
            old_svg=js_str_list([old_svg_text]),
            new_svg=js_str_list([new_svg_text]),
            reference_svg=js_str_list([ref_svg]))

    def _get_ref_fn(self, new_file):
        return self.screenshot_dir / new_file.parent.name / f'{new_file.stem}.kicad_mod.svg'

    def pretty_diff(self, old: Path, new: Path):
        self.diff_index = []
        files = []

        def diff_name(new_file) -> Path:
            return self.output / new_file.with_suffix('.html').name

        mod_files = list(new.glob('*.kicad_mod'))
        mod_files.sort(key=lambda x: x.stem)

        for new_file in mod_files:
            if not fnmatch.fnmatch(new_file.stem, self.name_glob):
                continue

            old_file = old / new_file.name
            old_text = old_file.read_text() if old_file.is_file() else ''
            new_text = new_file.read_text()
            changed = old_text != new_text
            created = not old_file.is_file()

            if self.changes_only and not changed:
                continue

            self.diff_index.append((diff_name(new_file), created, changed, False))
            files.append(new_file)

        # Render reference SVGs all at once
        # This is a lot faster than rendering them one by one, even if we end up over-rendering
        renderer = BatchRenderFootprints(new, self.screenshot_dir / new.name)

        for new_file in files:
            renderer.add_stem(new_file.stem)

        try:
            renderer.render()
        except Exception as e:
            warnings.warn(f'Error exporting reference render using kicad-cli: {e}')

        with multiprocessing.Pool(processes=self.max_workers) as pool:

            args = []

            for i, new_file in enumerate(files):
                prev_file = diff_name(files[(i - 1) % len(files)]).name
                next_file = diff_name(files[(i + 1) % len(files)]).name
                out_file = diff_name(new_file)
                args.append((old, new_file, next_file, prev_file, out_file))
            try:
                pool.starmap(self._process_one_mod, args)
            except KeyboardInterrupt:
                pool.terminate()
                pool.join()
            except Exception as e:
                warnings.warn(f'Error processing footprints: {e}')

    def _process_one_mod(self, old: Path, new_file: Path,
                         next_file: Path, prev_file: Path,
                         out_file: Path):  # fmt: skip
        old_file = old / new_file.name
        old_text = old_file.read_text() if old_file.is_file() else ''
        new_text = new_file.read_text()

        ref_fn = self._get_ref_fn(new_file)
        ref_svg = ''
        if ref_fn.is_file():
            ref_svg = ref_fn.read_text()
        else:
            ref_fn = ref_fn.with_name(f'{new_file.stem}.svg')
            ref_svg = ref_fn.read_text()

        diff_text = self.mod_diff(
            part_name=new_file.stem,
            lib_name=new_file.parent.stem,
            new_text=new_text,
            old_text=old_text,
            prev_diff=prev_file,
            next_diff=next_file,
            ref_svg=ref_svg
        )
        out_file.write_text(diff_text)

    @dataclass
    class SymLibDiffInfo():
        """
        Metadata describing a symbol library diff.
        """
        # Line content of the old and new symbol library files
        old_lines: list[str]
        new_lines: list[str]

        new_lib_stem: str

        # Name of the new/current symbol library
        old_lib: kicad_sym.KicadLibrary
        new_lib: kicad_sym.KicadLibrary

    @dataclass
    class SymbolDiffInfo():
        """
        Information about the files related to a symbol diff
        for a single symbol.
        """
        # Output HTML file
        out_file: Path

        # Name of the symbol in the new kicad_sym file
        new_name: str
        # Lines range in the new kicad_sym file
        new_start_line: int
        new_end_line: int

        # Name of the symbol in the old kicad_sym file
        old_name: str
        # Lines range in the old kicad_sym file
        old_start_line: int
        old_end_line: int

    def symlib_diff(self, old_symlib_path: Path, new_symlib_path: Path):
        if self.output is None:
            self.output = new_symlib_path.with_suffix('.diff')
        self.output.mkdir(exist_ok=True)

        old_lib = kicad_sym.KicadLibrary.from_file(filename=old_symlib_path)
        new_lib = kicad_sym.KicadLibrary.from_file(filename=new_symlib_path)

        # Get the raw s-expr lines of the symbol libraries for code-level diffs
        index_old = dict(build_symlib_index(old_symlib_path))
        index_new = dict(build_symlib_index(new_symlib_path))
        old_lines = old_symlib_path.read_text().splitlines() if old_symlib_path.is_file() else []
        new_lines = new_symlib_path.read_text().splitlines()

        symlib_diff_info = self.SymLibDiffInfo(
            old_lib=old_lib,
            new_lib=new_lib,
            old_lines=old_lines,
            new_lines=new_lines,
            new_lib_stem=new_symlib_path.stem,
        )

        self.diff_index = []
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

            created = (old_start, old_end) == (0, 0)
            changed = old_lines[old_start:old_end] != new_lines[start:end]

            deleted = (start, end) == (0, 0)

            if self.changes_only and not changed:
                continue

            out_file = self.output / f'{name}.html'
            self.diff_index.append((out_file, created, changed, deleted))

            files.append(
                self.SymbolDiffInfo(
                    out_file=out_file,
                    new_name=name,
                    new_start_line=start,
                    new_end_line=end,
                    old_name=old_name,
                    old_start_line=old_start,
                    old_end_line=old_end,
                )
            )

        # Render reference SVGs all at once
        batch_renderer = BatchRenderSymbols(
            new_symlib_path, self.screenshot_dir / new_symlib_path.name
        )
        for sym_diff_info in files:
            batch_renderer.add_stem(sym_diff_info.new_name)

        try:
            batch_renderer.render()
        except Exception as e:
            warnings.warn(f'Error exporting reference render using kicad-cli: {e}')

        with multiprocessing.Pool(processes=self.max_workers) as pool:

            args = []
            for i, sym_diff_info in enumerate(files):
                unit_files = batch_renderer.get_files_for_stem(sym_diff_info.new_name)

                prev_file = files[(i - 1) % len(files)].out_file.name
                next_file = files[(i + 1) % len(files)].out_file.name

                args.append((symlib_diff_info, sym_diff_info, unit_files,
                             next_file, prev_file))
            try:
                pool.starmap(self._process_one_sym, args)
            except KeyboardInterrupt:
                pool.terminate()
                pool.join()

    def _process_one_sym(self,
                         symlib_diff_info: SymLibDiffInfo,
                         sym_diff_info: SymbolDiffInfo,
                         unit_files, next_file, prev_file):  # fmt: skip

        # The actual line content of the symbol
        symbol_old_lines = symlib_diff_info.old_lines[
            sym_diff_info.old_start_line : sym_diff_info.old_end_line
        ]
        symbol_new_lines = symlib_diff_info.new_lines[
            sym_diff_info.new_start_line : sym_diff_info.new_end_line
        ]

        # Construct a temporary symbol library that contains only the new/old symbol
        old_sym = symlib_diff_info.old_lib.get_symbol(sym_diff_info.old_name)
        new_sym = symlib_diff_info.new_lib.get_symbol(sym_diff_info.new_name)

        screenshots_content = [f.read_text() for f in unit_files]

        svgs_old = []
        svgs_new = []

        if symbol_old_lines:
            svgs_old = [
                str(x)
                for x in render_sym.render_sym(
                    old_sym, symlib_diff_info.old_lib, default_style=False
                )
            ]

        if symbol_new_lines:
            svgs_new = [
                str(x)
                for x in render_sym.render_sym(
                    new_sym, symlib_diff_info.new_lib, default_style=False
                )
            ]

        sexpr_diff = wsdiff.html_diff_block(
            "\n".join(symbol_old_lines),
            "\n".join(symbol_new_lines),
            filename="",
            lexer=SexprLexer(),
        )

        prop_table = print_sym_properties.format_properties(old_sym, new_sym)

        sym_diff_info.out_file.write_text(
            self._format_html_diff(
                lib_name=symlib_diff_info.new_lib_stem,
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
            )
        )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='''html-diff.py generates a visual, HTML-formatted diff between two libraries. It outputs one file per library item into a folder named after the library with suffix ".diff". Included in the diff are:

                                     * An S-Expression diff
                                     * A visual diff
                                     * A render using kicad-cli
                                     * For footprints: A layer-by-layer preview

                                     If kicad-cli is not in PATH, you can give its location by setting the KICAD_CLI environment variable.
                                     ''')  # NOQA: E501
    parser.add_argument('base', nargs='?', default='HEAD', help='Old version to compare against. Format: [git_revision]:[library_or_mod_file]:[library_item]. All three are optional, defaults to taking the input file from git\'s HEAD. If the given parameter does not name an existing file or no git revision is given, the file is taken from git\'s HEAD.')  # NOQA: E501
    parser.add_argument('path', help='New version to compare. Format: [library_or_mod_file]:[library_item], with the item name optional.')  # NOQA: E501
    parser.add_argument('-n', '--only-names', default='*', help='Only output symbols or footprints whose name matches the given glob')  # NOQA: E501
    parser.add_argument('-u', '--unchanged', action='store_true', help='Also output unchanged symbols or footprints')  # NOQA: E501
    parser.add_argument('-s', '--screenshot-dir', type=Path, help='Read (footprints) or write (symbols) screenshots generated with kicad-cli to given directory instead of re-generating them on the fly.')  # NOQA: E501
    parser.add_argument('-S', '--diff-svg-output-dir', type=Path,
                        help='Write the diff A/B files to the given directory instead of a temporary directory.')  # NOQA: E501
    parser.add_argument('-j', '--jobs', type=int, default=1,
                        help="Number of parallel jobs to run when rendering symbols or footprints. Default is 1, "
                        "0 is use all available cores.")
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help='Increase verbosity. Can be given multiple times.')
    parser.add_argument('-o', '--output', type=Path, help='Where to output the diff. Must be a directory for symbol/footprint library comparisons, and must be a file for individual symbol or footprint comparisons.')  # NOQA: E501
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
    logging.info(f'Running with {workers} parallel jobs')

    try:
        if base.exists():
            if not path.exists():
                logging.error(f'File "{path}" does not exist.')
                sys.exit(2)

            meta['old_git'] = None
            meta['old_path'] = str(base)
            meta['new_path'] = str(path)

            html_diff = HTMLDiff(args.output, meta, args.only_names,
                                 changes_only=(not args.unchanged),
                                 screenshot_dir=args.screenshot_dir,
                                 diff_svg_output_dir=args.diff_svg_output_dir)
            html_diff.max_workers = workers
            html_diff.diff(base, path)

        else:
            if base.suffix.lower() in ('.kicad_mod', '.kicad_sym') and ':' not in args.base:
                # This does not look like either "[git_revision]" or "[git_revision]:[path]"
                logging.error(f'File "{base}" does not exist.')
                sys.exit(2)

            base_rev, _, rest = args.base.partition(':')
            base_file, _, base_name = rest.rpartition(':')
            base_file = Path(base_file if base_file else args.path)
            base_rev = base_rev or 'HEAD'

            try:
                proc = subprocess.run(['git', 'rev-parse', '--short', base_rev],
                                      check=True,
                                      capture_output=True,
                                      text=True,
                                      cwd=path.parent)
                meta['old_git'] = (base_rev, proc.stdout.strip())

                proc = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                                      check=True,
                                      capture_output=True,
                                      text=True,
                                      cwd=path.parent)
                tl = meta['git_toplevel'] = Path(proc.stdout.strip())
                meta['old_path'] = str(base_file.absolute().relative_to(tl))
                meta['new_path'] = str(path.absolute().relative_to(tl))

            except subprocess.CalledProcessError as e:
                logging.error(
                    f"Error parsing git revision '{base_rev}': "
                    f"rc={e.returncode}\n{e.stderr.strip()}"
                )
                sys.exit(1)

            with tempfile.TemporaryDirectory(suffix=path.suffix) as tmpd:
                tmpd = Path(tmpd)
                try:
                    ls_path = str(base_file.absolute().relative_to(path.parent.absolute()))
                    if path.is_dir():
                        ls_path += '/'
                    proc = subprocess.run(['git', 'ls-tree', '--name-only', base_rev, ls_path],
                                          check=True,
                                          capture_output=True,
                                          text=True,
                                          cwd=path.parent)
                    for fn in proc.stdout.splitlines():
                        with (tmpd/Path(fn).name).open('w') as outf:
                            subprocess.run(['git', 'show', f'{base_rev}:{fn}'],
                                           check=True,
                                           stderr=subprocess.PIPE,
                                           stdout=outf,
                                           text=True,
                                           cwd=path.parent)
                except subprocess.CalledProcessError as e:
                    logging.error(
                        f"Error checking out file '{base_file}' from git revision '{base_rev}': "
                        f"rc={e.returncode}\n{e.stderr.strip()}"
                    )
                    sys.exit(1)

                base = tmpd if path.is_dir() else tmpd / base_file.name

                html_diff = HTMLDiff(args.output, meta, args.only_names,
                                     changes_only=(not args.unchanged),
                                     screenshot_dir=args.screenshot_dir,
                                     diff_svg_output_dir=args.diff_svg_output_dir)
                html_diff.max_workers = workers
                html_diff.diff(base, path)

    except ValueError as e:
        raise e
        print(e.args[0], file=sys.stderr)
        sys.exit(2)
