Visual Library Diff
===================

This directory contains a script that produces HTML-formatted diffs between two symbol or footprint libraries. For every
footprint or for every symbol it generates a single HTML file that contains:

* A textual diff of the library item's S-Expression source code.
* A render generated using `kicad-cli`.
* A visual diff between old and new version.
* For footprints, a slightly inaccurate preview with selectable layer visibility.

All renders are draggable and zoomable.

Command-line usage
------------------

```
usage: html_diff.py [-h] [-n ONLY_NAMES] [-u] [-s SCREENSHOT_DIR] [-o OUTPUT]
                    [base] path

html-diff.py generates a visual, HTML-formatted diff between two libraries. It
outputs one file per library item into a folder named after the library with
suffix ".diff". Included in the diff are: * An S-Expression diff * A visual
diff * A render using kicad-cli * For footprints: A layer-by-layer preview If
kicad-cli is not in PATH, you can give its location by setting the KICAD_CLI
environment variable.

positional arguments:
  base                  Old version to compare against. Format:
                        [git_revision]:[library_or_mod_file]:[library_item].
                        All three are optional, defaults to taking the input
                        file from git's HEAD. If the given parameter does not
                        name an existing file or no git revision is given, the
                        file is taken from git's HEAD.
  path                  New version to compare. Format:
                        [library_or_mod_file]:[library_item], with the item
                        name optional.

options:
  -h, --help            show this help message and exit
  -n ONLY_NAMES, --only-names ONLY_NAMES
                        Only output symbols or footprints whose name matches
                        the given glob
  -u, --unchanged       Also output unchanged symbols or footprints
  -s SCREENSHOT_DIR, --screenshot-dir SCREENSHOT_DIR
                        Read (footprints) or write (symbols) screenshots
                        generated with kicad-cli to given directory instead of
                        re-generating them on the fly.
  -o OUTPUT, --output OUTPUT
                        Where to output the diff. Must be a directory for
                        symbol/footprint library comparisons, and must be a
                        file for individual symbol or footprint comparisons.
```
