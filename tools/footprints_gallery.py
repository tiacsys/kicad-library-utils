#!/usr/bin/env python3

# KiCad Footprints Gallery Generator
#
# Copyright (C) 2025 Martin Sotirov <martin@libtec.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


import argparse
import json
import math
import os
import pathlib
import re
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor

from PIL import Image, ImageDraw, ImageFont

BLANK_PCB = """
(kicad_pcb
\t(version 20241229)
\t(general
\t\t(thickness 1.6)
\t\t(legacy_teardrops no)
\t)
\t(layers
\t\t(0 "F.Cu" signal)
\t\t(2 "B.Cu" signal)
\t\t(13 "F.Paste" user)
\t\t(15 "B.Paste" user)
\t\t(5 "F.SilkS" user "F.Silkscreen")
\t\t(7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user)
\t\t(3 "B.Mask" user)
\t\t(25 "Edge.Cuts" user)
\t)
\t(setup
\t)
"""

KICAD_3D_VIEWER_CONFIG = """
{
  "layer_presets": [
    {
      "name": "empty",
      "layers": [
        "th_models",
        "smd_models"
      ],
      "colors": [
        {
          "color": "rgb(191, 156, 59)",
          "layer": "copper"
        }
      ]
    }
  ]
}
"""

class Footprint:
    def __init__(self, entry, params):
        self.pathlib_entry = entry
        self._text = None
        self.model = None
        self.params = params.get(entry.name, {})

    def __str__(self):
        return f"<Footprint: {self.pathlib_entry.name}>"

    def get_filename(self):
        return self.pathlib_entry.name

    def get_title(self):
        if "title" in self.params:
            return self.params["title"]
        else:
            return self.pathlib_entry.name.removesuffix(".kicad_mod")

    def get_text(self, config):
        return self._text + self._make_edge_cuts(config) + b")\n"

    def get_size(self, config):
        if config["pcb_shape"] == "circle":
            return math.sqrt((self.w / 2) ** 2 + (self.h / 2) ** 2) * 2
        elif config["pcb_shape"] == "rect":
            return max(self.w, self.h)
        else:
            raise ValueError(f"Invalid PCB shape: {config['pcb_shape']}")

    def load(self):
        footprint_file = open(self.pathlib_entry.absolute(), "rb")
        element_re = re.compile(r"(\t*)\(([^\n ]+) *(.*)")

        self._text = b""

        context = ""
        pad = {}
        self.min_x = float("inf")
        self.min_y = float("inf")
        self.max_x = float("-inf")
        self.max_y = float("-inf")

        while True:
            raw_line = footprint_file.readline()
            if not raw_line:
                break

            line = raw_line.decode().rstrip()
            if line[0] == ")":
                raw_line = footprint_file.readline()
                assert not raw_line
                break
            self._text += b"\t" + raw_line

            element_match = element_re.match(line)
            if not element_match:
                continue

            indentation = len(element_match[1])
            element_name = element_match[2]
            element_attribs = element_match[3]

            if indentation == 1:
                context = element_name
                if element_name == "property":
                    self._text += b"\t\t(hide yes)\n"
                elif element_name == "model":
                    self.model = element_attribs[1:-1]
                elif element_name == "pad":
                    pad = {}
            elif indentation == 2:
                if context in ["fp_line", "fp_rect"]:
                    if element_name in ["start", "end"]:
                        assert element_attribs.endswith(")")
                        x, y = [float(n) for n in element_attribs[:-1].split()]
                        self.min_x = min(self.min_x, x)
                        self.min_y = min(self.min_y, y)
                        self.max_x = max(self.max_x, x)
                        self.max_y = max(self.max_y, y)
                elif context == "pad":
                    if element_name == "at":
                        pad["x"], pad["y"] = [
                            float(n) for n in element_attribs[:-1].split()[:2]
                        ]
                    elif element_name == "size":
                        pad["w"], pad["h"] = [
                            float(n) for n in element_attribs[:-1].split()
                        ]

                    if "x" in pad and "w" in pad:
                        self.min_x = min(self.min_x, pad["x"] - pad["w"] / 2)
                        self.min_y = min(self.min_y, pad["y"] - pad["h"] / 2)
                        self.max_x = max(self.max_x, pad["x"] + pad["w"] / 2)
                        self.max_y = max(self.max_y, pad["y"] + pad["h"] / 2)
                        pad = {}

        footprint_file.close()

        self.w = self.max_x - self.min_x
        self.h = self.max_y - self.min_y

    def has_model(self, config):
        if not self.model:
            return False

        models_path_re = re.compile(r"\${KICAD[\d]+_3DMODEL_DIR}")
        models_path = models_path_re.sub(config["models_path"], self.model)
        models_pathlib = pathlib.Path(models_path)
        return models_pathlib.exists()

    def _make_edge_cuts(self, config):
        mid_x = self.min_x + self.w / 2
        mid_y = self.min_y + self.h / 2

        if config["pcb_shape"] == "circle":
            if config["pcb_size"] == "auto":
                r = self.get_size(config) / 2
            else:
                r = config["pcb_size"] / 2

            text = (
                f"\t\t(fp_circle\n"
                f"\t\t\t(center {mid_x} {mid_y})\n"
                f"\t\t\t(end {mid_x - r} {mid_y})\n"
                f"\t\t\t(fill no)\n"
                f'\t\t\t(layer "Edge.Cuts")\n'
                f"\t\t)\n"
            )
        elif config["pcb_shape"] == "rect":
            if config["pcb_size"] == "auto":
                d = self.get_size(config)
            else:
                d = config["pcb_size"]

            x0 = mid_x - d / 2
            x1 = mid_x + d / 2
            y0 = mid_y - d / 2
            y1 = mid_y + d / 2

            text = (
                f"\t\t(fp_rect\n"
                f"\t\t\t(start {x0} {y0})\n"
                f"\t\t\t(end {x1} {y1})\n"
                f"\t\t\t(fill no)\n"
                f'\t\t\t(layer "Edge.Cuts")\n'
                f"\t\t)\n"
            )
        else:
            raise ValueError(f"Invalid PCB shape: {config['pcb_shape']}")

        return text.encode()


def get_footprints(config, params, footprint_paths):
    footprints = []

    for footprint_path in footprint_paths:
        footprint_path = pathlib.Path(footprint_path)

        if not footprint_path.exists():
            raise ValueError(f"Footprint doesn't exist: {footprint_path}")

        if footprint_path.is_dir():
            dir_footprints = []
            for dir_entry in footprint_path.iterdir():
                if not dir_entry.name.endswith(".kicad_mod"):
                    continue
                footprint = Footprint(dir_entry, params)
                footprint.load()
                dir_footprints.append(footprint)
            dir_footprints.sort(key=lambda f: f.pathlib_entry.absolute().parts[-2:])
            footprints += dir_footprints
        elif footprint_path.is_file():
            footprint = Footprint(footprint_path, params)
            footprint.load()
            footprints.append(footprint)

    return footprints


def get_footprints_from_model_generator(
    config, params, generator_path, footprints_path
):
    footprints_path = pathlib.Path(footprints_path)
    if not footprints_path.is_dir():
        raise ValueError(f"Footprints path must be a directory: {footprints_path}")

    generator_file = open(generator_path)

    model = None
    models = []
    refs = {}

    title_re = re.compile(r"^([^ ][^:]+): *(&[^ ]*)?$")
    param_re = re.compile(r"^ +([^:]+): *(.*)$")

    while True:
        line = generator_file.readline()
        if not line:
            break
        line = line.rstrip()

        if line.lstrip().startswith("#"):
            continue

        title_match = title_re.match(line)
        if title_match:
            title, ref = title_match[1], title_match[2]
            model = {"title": title}
            models.append(model)
            if ref:
                assert ref[0] == "&"
                ref = ref[1:]
                refs[ref] = model
            continue

        param_match = param_re.match(line)
        if param_match:
            assert model
            param, value = param_match[1], param_match[2]

            if param == "modelName":
                assert value == model["title"]
            elif param == "destination_dir":
                model["destination_dir"] = value
            elif param == "<<":
                assert value[0] == "*"
                model["parent"] = refs[value[1:]]

    generator_file.close()

    footprints = []

    for model in models:
        m = model
        while "destination_dir" not in m:
            m = m["parent"]

        assert m["destination_dir"].endswith(".3dshapes")
        footprint_dirname = m["destination_dir"].removesuffix(".3dshapes") + ".pretty"
        footprint_pathlib = (
            pathlib.Path(footprints_path)
            / footprint_dirname
            / f"{model['title']}.kicad_mod"
        )

        if not footprint_pathlib.is_file():
            print(f"Warning: Missing footprint: {footprint_pathlib}")
            continue

        footprint = Footprint(footprint_pathlib, params)
        footprint.load()
        footprints.append(footprint)

    return footprints


def draw_footprint_title(config, footprint_title: str, footprint_im):
    line_max = 25
    lines_max = 2
    stroke = 4

    title = footprint_title.split("\n")
    lines = []

    for line_index, line in enumerate(title):
        while line:
            lines.append(line[:line_max])
            line = line[line_max:]

    if len(lines) > lines_max:
        lines[lines_max - 1] = lines[lines_max - 1][:-1] + "…"
    lines = lines[:lines_max]

    footprint_im_draw = ImageDraw.Draw(footprint_im)

    for line_index, line in enumerate(lines):
        line_y = int(
            footprint_im.size[1] * 0.95
            - (lines_max - 1 - line_index) * config["font_size"]
        )
        footprint_im_draw.text(
            (footprint_im.size[0] / 2, line_y),
            line,
            anchor="ms",
            font=config["im_font"],
            fill=(255, 255, 255),
            stroke_width=stroke,
            stroke_fill=(0, 0, 0),
        )


def make_gallery_page(
    config,
    footprints,
    footprints_offset: int,
    tmp_files_dir: pathlib.Path,
    composed_png: pathlib.Path,
):
    assert footprints
    footprints_chunk = footprints[
        footprints_offset : footprints_offset + config["max_per_page"]
    ]
    assert footprints_chunk
    page_index = footprints_offset // config["max_per_page"]

    composed_cols = min(config["composed_cols"], len(footprints_chunk))
    composed_rows = (
        len(footprints_chunk) // composed_cols + 1
        if len(footprints_chunk) % composed_cols
        else len(footprints_chunk) // composed_cols
    )
    composed_im = None

    # Gather footprint information in here
    footprint_infos = {}

    with ProcessPoolExecutor() as executor:

        futures = []

        for footprint_index, footprint in enumerate(footprints_chunk):
            # Construct the arguments for rendering the footprint
            render_one_fp_args = (
                config,
                footprint,
                pathlib.Path(tmp_files_dir),
            )
            future = executor.submit(render_one_footprint, *render_one_fp_args)

            footprint_infos[footprint] = {
                "index_in_chunk": footprint_index,
            }

            futures.append((future, footprint))

        # Wait for futures to complete and gather results
        for future, footprint in futures:
            try:
                output_png = future.result()
                if config["show_progress"]:
                    index = (
                        footprints_offset
                        + footprint_infos[footprint]["index_in_chunk"]
                        + 1
                    )
                    print(f"[{index}/{len(footprints)}] {footprint.get_title()}")

                # Append the result information
                footprint_infos[footprint]["output_png"] = output_png
            except ValueError as e:
                print(f"Error rendering footprint: {e}")
                return

    sorted_footprints = sorted(
        footprint_infos.items(), key=lambda fp: fp[1]["index_in_chunk"]
    )

    # Iterate the footprints and paste into the composed image
    for footprint, footprint_info in sorted_footprints:

        footprint_im = Image.open(footprint_info["output_png"])
        footprint_index = footprint_info["index_in_chunk"]

        draw_footprint_title(config, footprint.get_title(), footprint_im)

        if config["should_make_composed"]:
            if not composed_im:
                composed_im = Image.new(
                    "RGBA",
                    (
                        footprint_im.size[0] * composed_cols,
                        footprint_im.size[1] * composed_rows,
                    ),
                )
                composed_im.save(composed_png)

            col = footprint_index % composed_cols
            row = footprint_index // composed_cols
            composed_im.paste(
                footprint_im, [footprint_im.size[0] * col, footprint_im.size[1] * row]
            )

            if config["viewer"]:
                if footprint_index % 3 == 0:
                    composed_im.save(composed_png)

                if page_index == 0 and footprint_index == 0:
                    subprocess.Popen([config["viewer"], composed_png])

        if config["directory_output_path"]:
            footprint_im.save(
                config["directory_output_path"] / f"{footprint.get_title()}.png"
            )

        footprint_im.close()

    if config["should_make_composed"]:
        composed_im.save(composed_png)

        if config["composed_output_path"]:
            path = config["composed_output_path"]
            try:
                path = path % (page_index + 1)
            except TypeError:
                pass
            composed_im.save(path)

        composed_im.close()


def render_one_footprint(
    config, footprint: Footprint, tmp_files_dir: pathlib.Path
) -> pathlib.Path:

    footprint_png = tmp_files_dir / f"{footprint.get_title()}.png"
    pcb_file = tmp_files_dir / f"{footprint.get_title()}.kicad_pcb"

    with open(pcb_file, "wb") as f:
        f.write(BLANK_PCB.encode())
        f.write(footprint.get_text(config))
        f.write(b")\n")

    kicad_cli_args = [
        "kicad-cli",
        "pcb",
        "render",
        "--width",
        str(config["img_w"]),
        "--height",
        str(config["img_h"]),
        "--zoom",
        str(config["pcb_zoom"]),
        "--rotate",
        ",".join(map(str, config["pcb_ori"])),
        "--pan",
        ",".join(map(str, config["pcb_pan"])),
    ]

    if config["render_quality"]:
        kicad_cli_args.append("--quality")
        kicad_cli_args.append(config["render_quality"])
    if config["render_preset"]:
        kicad_cli_args.append("--preset")
        kicad_cli_args.append(config["render_preset"])
    if config["render_floor"]:
        kicad_cli_args.append("--floor")

    kicad_cli_args.append("-o")
    kicad_cli_args.append(footprint_png)
    kicad_cli_args.append(pcb_file)

    if config["use_temp_home"]:
        kicad_cli_env = {"HOME": str(tmp_files_dir)}
    else:
        kicad_cli_env = None

    kicad_cli_proc = subprocess.Popen(kicad_cli_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=kicad_cli_env)
    kicad_cli_returncode = kicad_cli_proc.wait()
    if kicad_cli_returncode != 0:
        raise ValueError(
            f"Can't render footprint: {footprint.get_filename()}\n"
            f"{kicad_cli_returncode.stderr.decode()}"
        )

    return footprint_png


def make_gallery(config, footprints, tmp_files_dir: pathlib.Path, composed_png):

    if not footprints:
        print("Warning: No footprints found")
        return

    footprints_offset = 0

    while footprints_offset < len(footprints):
        make_gallery_page(
            config, footprints, footprints_offset, tmp_files_dir, composed_png
        )
        footprints_offset += config["max_per_page"]

    if config["should_make_composed"]:
        if not config["composed_output_path"]:
            print(f"Temporary composed image: {composed_png.name}")
            input("Press Enter to exit...")


def get_params(config_params, params_path):
    params_file = open(params_path, "r")
    params = json.load(params_file)
    config_params.update(params)
    params_file.close()


def vector3(arg):
    arg_re = re.compile(r"^\[([^,]*),([^,]*),([^,]*)\]$")
    arg_match = arg_re.match(arg)
    assert arg_match
    arg = arg_match.groups()
    arg = tuple(map(float, arg))

    return arg


def main():
    config = {}

    args_parser = argparse.ArgumentParser()
    args_parser.add_argument("footprint", help="Footprint file or directory.", nargs="+")
    args_parser.add_argument("-p", "--params", help="Customs JSON params file.")
    args_parser.add_argument("-g", "--generator", help="Model generator's YAML file.")
    args_parser.add_argument(
        "-c", "--composed-output", help="Composed PNG image output."
    )
    args_parser.add_argument(
        "-d",
        "--directory-output",
        type=pathlib.Path,
        help="Individual PNG images output directory.",
    )
    args_parser.add_argument(
        "--show-progress",
        action=argparse.BooleanOptionalAction,
        help="Show generation progress.",
    )
    args_parser.add_argument(
        "--models", default="/usr/share/kicad/3dmodels", help="3D models directory."
    )
    args_parser.add_argument(
        "--font-file",
        default="./fonts/Roboto/RobotoCondensed-Regular.ttf",
        help="Font file.",
    )
    args_parser.add_argument("--font-size", type=float, default="20", help="Font size.")
    args_parser.add_argument("--width", type=int, default=300, help="Sub-image width.")
    args_parser.add_argument("--height", type=int, default=300, help="Sub-image height.")
    args_parser.add_argument(
        "--max-per-page", type=int, help="Maximum footprints per page."
    )
    args_parser.add_argument(
        "--cols", type=int, default=6, help="Composed image columns count."
    )
    args_parser.add_argument(
        "--pcb-shape",
        choices=["circle", "rect"],
        default="circle",
        help="PCB shape type.",
    )
    args_parser.add_argument(
        "--pcb-size",
        default="auto",
        help="PCB size, 'auto', or 'max'.",
    )
    args_parser.add_argument(
        "--zoom", type=float, default="0.95", help="Camera zoom amount."
    )
    args_parser.add_argument(
        "--orientation", type=vector3, default="[310, 0, 45]", help="Camera orientation."
    )
    args_parser.add_argument(
        "--pan", type=vector3, default="[0, -1.5, 0]", help="Camera pan."
    )
    args_parser.add_argument(
        "--with-params",
        action=argparse.BooleanOptionalAction,
        help="Include only footprints with existing custom JSON parameters.",
    )
    args_parser.add_argument(
        "--with-model",
        action=argparse.BooleanOptionalAction,
        help="Include only footprints with existing 3D model.",
    )
    args_parser.add_argument(
        "--render-quality", help="Render quality. (options: basic, high, user)"
    )
    args_parser.add_argument("--render-preset", help="Render preset (options: empty, ...). See '--temp-home'.")
    args_parser.add_argument(
        "--render-floor",
        action=argparse.BooleanOptionalAction,
        help="Render floor shadows.",
    )
    args_parser.add_argument(
        "--use-temp-home",
        action=argparse.BooleanOptionalAction,
        help="Use a temporary home/config directory for KiCad instead the user home/config directory. This is required for '--preset empty'."
    )
    args_parser.add_argument(
        "--viewer", help="Application used for viewing during generation."
    )
    args = args_parser.parse_args()

    config["show_progress"] = args.show_progress
    config["composed_output_path"] = args.composed_output
    config["directory_output_path"] = args.directory_output
    config["models_path"] = args.models
    config["font_path"] = args.font_file
    config["font_size"] = args.font_size
    config["img_w"] = args.width
    config["img_h"] = args.height
    config["max_per_page"] = args.max_per_page
    config["composed_cols"] = args.cols
    config["pcb_shape"] = args.pcb_shape
    config["pcb_size"] = args.pcb_size
    config["pcb_zoom"] = args.zoom
    config["pcb_ori"] = args.orientation
    config["pcb_pan"] = args.pan
    config["only_with_params"] = args.with_params
    config["only_with_model"] = args.with_model
    config["render_quality"] = args.render_quality
    config["render_preset"] = args.render_preset
    config["render_floor"] = args.render_floor
    config["use_temp_home"] = args.use_temp_home
    config["viewer"] = args.viewer

    if config["directory_output_path"] and not config["directory_output_path"].is_dir():
        raise ValueError(
            f"Directory output argument is not an existing directory: {config['directory_output_path']}"
        )

    config["should_make_composed"] = (
        config["viewer"]
        or config["composed_output_path"]
        or not config["directory_output_path"]
    )

    config["im_font"] = ImageFont.truetype(config["font_path"], config["font_size"])

    if config["pcb_size"] not in ["auto", "max"]:
        config["pcb_size"] = float(config["pcb_size"])

    params = {}
    if args.params:
        get_params(params, args.params)

    if args.generator:
        if len(args.footprint) != 1:
            raise ValueError(
                f"Only one footprint directory can be used: {config['directory_output_path']}"
            )

        footprints = get_footprints_from_model_generator(
            config, params, args.generator, args.footprint[0]
        )
    else:
        footprints = get_footprints(config, params, args.footprint)
        if config["only_with_model"]:
            footprints = list(filter(lambda f: f.has_model(config), footprints))

    if not config["max_per_page"]:
        config["max_per_page"] = len(footprints)

    if config["pcb_size"] == "max":
        max_size = 0
        for footprint in footprints:
            max_size = max(max_size, footprint.get_size(config))
        config["pcb_size"] = max_size

    tmp_files_dir = tempfile.TemporaryDirectory(prefix="footprints_gallery-", delete=False)
    composed_png = tempfile.NamedTemporaryFile(suffix=".png", delete=False)

    if config["use_temp_home"]:
        kicad_home = tmp_files_dir.name
        kicad_3d_viewer_config_path = pathlib.Path(kicad_home) / ".config" / "kicad" / "9.0" / "3d_viewer.json"
        kicad_3d_viewer_config_path.parent.mkdir(parents=True, exist_ok=True)

        with kicad_3d_viewer_config_path.open("w") as f:
            f.write(KICAD_3D_VIEWER_CONFIG)

    try:
        make_gallery(
            config,
            footprints,
            pathlib.Path(tmp_files_dir.name),
            pathlib.Path(composed_png.name),
        )
    except KeyboardInterrupt:
        print()
    finally:
        tmp_files_dir.cleanup()
        composed_png.close()
        os.unlink(composed_png.name)


if __name__ == "__main__":
    main()
