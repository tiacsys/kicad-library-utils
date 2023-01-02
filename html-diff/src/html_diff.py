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

from pygments.lexer import RegexLexer
from pygments import token
import wsdiff

try:
    # Try importing kicad_mod to figure out whether the kicad-library-utils stuff is in path
    import kicad_mod  # NOQA: F401
except ImportError:
    if (common := Path(__file__).parent.parent.with_name('common').absolute()) not in sys.path:
        sys.path.insert(0, str(common))


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
            warnings.warn(f'Error formatting diff')  # NOQA: F541
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


def temporary_symbol_library(symbol_lines):
    if symbol_lines and not symbol_lines[0].strip().startswith('(symbol'):
        warnings.warn(f'Leading garbage in same line before symbol definition or broken symbol index')  # NOQA: E501, F541

    if symbol_lines and not symbol_lines[-1].strip().endswith(')'):
        warnings.warn(f'Trailing garbage in same line after symbol definition or broken symbol index')  # NOQA: E501, F541

    content = '\n'.join(symbol_lines)
    return f'(kicad_symbol_lib (version 20220914) (generator kicad_html_diff)\n{content}\n)'


def build_symlib_index(libfile):
    if not libfile.is_file():
        return

    text = Path(libfile).read_text()
    lineno = 0
    last_start, last_name = 1, None
    for match in re.finditer(r'\(\W*symbol\W*\s"(\S+)"\s|(\r?\n)', text, re.MULTILINE):
        symbol_name, newline = match.groups()

        if symbol_name and not re.fullmatch(r'.*_[0-9]_[0-9]', symbol_name):
            if last_name:
                yield last_name, (last_start, lineno)
            last_name, last_start = symbol_name, lineno

        # newlines might be embedded in between the symbol def, e.g. (symbol\n"FOO"
        lineno += match.group(0).count('\n')

    if last_name:
        yield last_name, (last_start, lineno)


def render_symbol_kicad_cli(libfile, symname, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    svg_glob = lambda: list(outdir.glob(f'{symname.lower()}*.svg'))  # NOQA: E731

    # Remove conflicting old files in case a unit was deleted
    for old_file in svg_glob():
        old_file.unlink()

    kicad_cli = os.environ.get('KICAD_CLI', 'kicad-cli')
    try:
        subprocess.run([kicad_cli, 'sym', 'export', 'svg',
                        '-s', symname,
                        '-o', str(outdir), str(libfile)],
                       check=True, stdout=sys.stdout, stderr=sys.stderr)
    except FileNotFoundError:
        warnings.warn('Cannot find kicad-cli, no reference screenshots will be exported.')
        return {}

    new_files = svg_glob()
    if len(new_files) == 1:  # only one unit
        return {1: new_files[0]}
    else:
        return {int(fn.stem.rpartition('_')[2]): fn for fn in new_files}


def render_footprint_kicad_cli(libdir, fpname, outfile):
    outfile.parent.mkdir(parents=True, exist_ok=True)

    kicad_cli = os.environ.get('KICAD_CLI', 'kicad-cli')
    try:
        subprocess.run([kicad_cli, 'fp', 'export', 'svg',
                        '--footprint', fpname,
                        '-o', str(outfile), str(libdir)],
                       check=True, stdout=sys.stdout, stderr=sys.stderr)
    except FileNotFoundError:
        warnings.warn('Cannot find kicad-cli, no reference screenshots will be exported.')


class HTMLDiff:
    @html_stacktrace
    def mod_diff(self, old_text, new_text, ref_svg):
        return self._format_html_diff(
            enable_layers=True,
            canvas_background='#001023',
            hide_text_in_diff=True,
            properties_table=print_fp_properties.format_properties(new_text),
            code_diff=wsdiff.html_diff_block(old_text, new_text,
                                             filename='', lexer=SexprLexer()),
            old_svg=js_str_list([render_fp.render_mod(old_text)]),
            new_svg=js_str_list([render_fp.render_mod(new_text)]),
            reference_svg=js_str_list([ref_svg]))

    def _format_html_diff(self, enable_layers, hide_text_in_diff, **kwargs):
        return j2env.get_template('diff.html').render(
            page_title = f'diff: {self.meta["part_name"]} in {self.meta["lib_name"]}',
            part_name = self.meta["part_name"],
            source_revisions = self.source_revisions,
            enable_layers = 'true' if enable_layers else 'false',
            hide_text_in_diff = 'true' if hide_text_in_diff else 'false',

            code_diff_css=wsdiff.MAIN_CSS,
            diff_syntax_css=wsdiff.PYGMENTS_CSS,

            prev_button = button('<', meta.get('prev_diff'), _id='nav-bt-prev'),
            next_button = button('>', meta.get('next_diff'), _id='nav-bt-next'),
            diff_index = '\n'.join(self.format_index()),

            pipeline_button = button_if('Pipeline', os.environ.get('CI_PIPELINE_URL')),
            old_file_button = button_if('Old File', self.old_url),
            new_file_button = button_if('New File', self.new_url),
            merge_request_button = button_if('Merge Request', self.mr_url),

            **kwargs)

    def __init__(self, output, meta, name_glob='*', changes_only=True, screenshot_dir=None):
        self.output = output
        self.meta = meta
        self.name_glob = name_glob
        self.changes_only = changes_only
        self.name_map = {}
        self.diff_index = []

        if screenshot_dir is None:
            tmp = self.screenshot_tmpdir = tempfile.TemporaryDirectory()
            self.screenshot_dir = Path(tmp.name)
        else:
            self.screenshot_dir = screenshot_dir

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

        if 'old_git' in self.meta:
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

            self.symlib_diff(old, new)

        elif new.suffix == '.kicad_mod':
            if self.name_glob:
                raise ValueError('Name globs are not supported when processing a single footprint only.')  # NOQA: E501

            if self.output is None:
                self.output = new.with_suffix('.diff')
            self.output.mkdir(exist_ok=True)

            old_text, new_text = old.read_text(), new.read_text()
            meta['part_name'] = new.stem
            if new.parent.suffix.lower() == '.pretty':
                meta['lib_name'] = new.parent.stem
            else:
                meta['lib_name'] = '<unknown library>'

            ref_fn = self.screenshot_dir / f'{meta["lib_name"]}.pretty' / f'{meta["part_name"]}.kicad_mod.svg'  # NOQA: E501
            ref_svg = ''
            if ref_fn.is_file():
                ref_svg = ref_fn.read_text()
            else:
                try:
                    render_footprint_kicad_cli(new.parent, new.stem, ref_fn.parent)
                    ref_fn = ref_fn.with_name(f'{meta["part_name"]}.svg')
                    ref_svg = ref_fn.read_text()
                except Exception as e:
                    warnings.warn(f'Error exporting reference render using kicad-cli: {e}')

            (self.output / new.with_suffix('.html').name).write_text(
                self.mod_diff(old_text, new_text, ref_svg))

        elif new.suffix == '.pretty':
            if ':' in old.suffix or ':' in new.suffix:
                raise ValueError('Giving library item names via [library]:[item_name] is only supported for symbol libraries. To compare individual footprints, simply list their .kicad_mod files inside the .pretty directory.')  # NOQA: E501

            if self.output is None:
                self.output = new.with_suffix('.diff')
            self.output.mkdir(exist_ok=True)

            self.pretty_diff(old, new)

        else:
            raise ValueError('Unhandled input type {new.suffix}. Supported formats are .kicad_sym, .kicad_mod and .pretty.')  # NOQA: E501

    def format_index(self):
        for filename, created, changed in self.diff_index:
            if created:
                css_class = 'created'
            elif changed:
                css_class = 'changed'
            else:
                css_class = 'unchanged'
            self_class = ' index-self' if filename.stem == self.meta['part_name'] else ''
            yield f'<div class="{css_class}{self_class}"><a href="{filename.name}">{filename.stem}</a></div>'  # NOQA: E501

    def pretty_diff(self, old, new):
        self.diff_index = []
        files = []
        meta['lib_name'] = new.stem
        diff_name = lambda new_file: self.output / new_file.with_suffix('.html').name  # NOQA: E731

        for new_file in new.glob('*.kicad_mod'):
            if not fnmatch.fnmatch(new_file.stem, self.name_glob):
                continue

            old_file = old / new_file.name
            old_text = old_file.read_text() if old_file.is_file() else ''
            new_text = new_file.read_text()
            changed = old_text != new_text
            created = not old_file.is_file()

            if self.changes_only and not changed:
                continue

            self.diff_index.append((diff_name(new_file), created, changed))
            files.append(new_file)

        for i, new_file in enumerate(files):
            meta['prev_diff'] = str(diff_name(files[(i-1) % len(files)]).name)
            meta['next_diff'] = str(diff_name(files[(i+1) % len(files)]).name)
            meta['diff_index'] = 'index.html'
            meta['part_name'] = new_file.stem
            meta['old_path'] = new_file
            meta['new_path'] = new_file
            old_file = old / new_file.name
            old_text = old_file.read_text() if old_file.is_file() else ''
            new_text = new_file.read_text()

            ref_fn = self.screenshot_dir / new_file.parent.name / f'{new_file.stem}.kicad_mod.svg'
            ref_svg = ''
            if ref_fn.is_file():
                ref_svg = ref_fn.read_text()
            else:
                try:
                    render_footprint_kicad_cli(new_file.parent, new_file.stem, ref_fn.parent)
                    ref_fn = ref_fn.with_name(f'{new_file.stem}.svg')
                    ref_svg = ref_fn.read_text()
                except Exception as e:
                    warnings.warn(f'Error exporting reference render using kicad-cli: {e}')

            diff_name(new_file).write_text(self.mod_diff(old_text, new_text, ref_svg))

    def symlib_diff(self, old, new):
        if self.output is None:
            self.output = new.with_suffix('.diff')
        self.output.mkdir(exist_ok=True)

        index_old = dict(build_symlib_index(old))
        index_new = dict(build_symlib_index(new))
        old_lines = old.read_text().splitlines() if old.is_file() else []
        new_lines = new.read_text().splitlines()
        meta['lib_name'] = new.stem

        self.diff_index, files = [], []
        for name, (start, end) in index_new.items():
            if not fnmatch.fnmatch(name, self.name_glob):
                continue

            old_name = self.name_map.get(name, name)
            old_start, old_end = index_old.get(old_name, (0, 0))

            created = (old_start, old_end) == (0, 0)
            changed = old_lines[old_start:old_end] != new_lines[start:end]

            if self.changes_only and not changed:
                continue

            out_file = self.output / f'{name}.html'
            self.diff_index.append((out_file, created, changed))
            files.append((name, out_file, start, end, old_name, old_start, old_end))

        for i, (name, out_file, start, end, old_name, old_start, old_end) in enumerate(files):
            meta['prev_diff'] = files[(i-1) % len(files)][0] + '.html'
            meta['next_diff'] = files[(i+1) % len(files)][0] + '.html'
            meta['diff_index'] = 'index.html'
            meta['part_name'] = name
            meta['old_path'] = old
            meta['new_path'] = new
            meta['old_line_range'] = (old_start, old_end)
            meta['new_line_range'] = (start, end)

            old_sym = temporary_symbol_library(old_lines[old_start:old_end])
            new_sym = temporary_symbol_library(new_lines[start:end])

            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir = Path(tmpdir)
                out = self.screenshot_dir / new.name if self.screenshot_dir else tmpdir

                screenshots_new = render_symbol_kicad_cli(new, name, out)
                screenshots_new_sorted = [v.read_text()
                                          for k, v in sorted(
                                              screenshots_new.items(),
                                              key=lambda x: x[0])]

            if old_lines[old_start:old_end]:
                svgs_old = [str(x) for x in render_sym.render_sym(old_sym, old_name,
                                                                  default_style=False)]
            else:
                svgs_old = []
            svgs_new = [str(x) for x in render_sym.render_sym(new_sym, name, default_style=False)]

            sexpr_diff = wsdiff.html_diff_block(old_sym, new_sym, filename='', lexer=SexprLexer())

            out_file.write_text(self._format_html_diff(
                enable_layers=False,
                canvas_background='#e0e0e0',
                hide_text_in_diff=False,
                properties_table=print_sym_properties.format_properties(new_sym, name),
                code_diff=sexpr_diff,
                old_svg=js_str_list(svgs_old),
                new_svg=js_str_list(svgs_new),
                reference_svg=js_str_list(screenshots_new_sorted)))


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
    parser.add_argument('-o', '--output', type=Path, help='Where to output the diff. Must be a directory for symbol/footprint library comparisons, and must be a file for individual symbol or footprint comparisons.')  # NOQA: E501
    args = parser.parse_args()

    path, path_name = Path(args.path), None
    base, base_name = Path(args.base), None

    meta = {}

    if not (path.is_file() or path.is_dir()):
        path, _, path_name = path.rpartition(':')
        print(f'Path "{path}" does not exist or is not a file.', file=sys.stderr)
        sys.exit(2)

    try:
        if base.exists():
            if not path.exists():
                print(f'File "{path}" does not exist.', file=sys.stderr)
                sys.exit(2)

            meta['old_git'] = None
            meta['old_path'] = str(base)
            meta['new_path'] = str(path)

            html_diff = HTMLDiff(args.output, meta, args.only_names,
                                 changes_only=(not args.unchanged),
                                 screenshot_dir=args.screenshot_dir)
            html_diff.diff(base, path)

        else:
            if base.suffix.lower() in ('.kicad_mod', '.kicad_sym') and ':' not in args.base:
                # This does not look like either "[git_revision]" or "[git_revision]:[path]"
                print(f'File "{base}" does not exist.', file=sys.stderr)
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
                print(f'Error parsing git revision "{base_rev}": rc={e.returncode}\n{e.stderr.strip()}', file=sys.stderr)  # NOQA: E501
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
                    print(f'Error checking out file "{base_file}" from git revision "{base_rev}": rc={e.returncode}\n{e.stderr.strip()}', file=sys.stderr)  # NOQA: E501
                    sys.exit(1)

                base = tmpd if path.is_dir() else tmpd / base_file.name

                html_diff = HTMLDiff(args.output, meta, args.only_names,
                                     changes_only=(not args.unchanged),
                                     screenshot_dir=args.screenshot_dir)
                html_diff.diff(base, path)

    except ValueError as e:
        raise e
        print(e.args[0], file=sys.stderr)
        sys.exit(2)
