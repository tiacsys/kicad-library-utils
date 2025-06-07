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
import pathlib
import re
import subprocess
import tempfile

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


class Footprint:
    def __init__(self, entry, params):
        self.pathlib_entry = entry
        self.text = None
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

    def load(self, config):
        footprint_file = open(self.pathlib_entry.absolute(), "rb")
        element_re = re.compile(r"(\t*)\(([^\n ]+) *(.*)")

        self.text = b""

        context = ""
        min_x = 0
        min_y = 0
        max_x = 0
        max_y = 0

        while True:
            raw_line = footprint_file.readline()
            if not raw_line:
                break

            line = raw_line.decode().rstrip()
            if line[0] == ")":
                self.text += self._make_edge_cuts(config, min_x, min_y, max_x, max_y)
            self.text += b"\t" + raw_line

            element_match = element_re.match(line)
            if not element_match:
                continue

            indentation = len(element_match[1])
            element_name = element_match[2]
            element_attribs = element_match[3]

            if indentation == 1:
                context = element_name
                if element_name == "property":
                    self.text += b"\t\t(hide yes)\n"
                elif element_name == "model":
                    self.model = element_attribs[1:-1]
            elif indentation == 2:
                if context in ["fp_line", "fp_rect"]:
                    if element_name in ["start", "end"]:
                        assert element_attribs.endswith(")")
                        x, y = [float(n) for n in element_attribs[:-1].split()]
                        min_x = min(min_x, x)
                        min_y = min(min_y, y)
                        max_x = max(max_x, x)
                        max_y = max(max_y, y)

        footprint_file.close()

    def has_model(self, config):
        models_path_re = re.compile(r"\${KICAD[\d]+_3DMODEL_DIR}")
        models_path = models_path_re.sub(config["models_path"], self.model)
        models_pathlib = pathlib.Path(models_path)
        return models_pathlib.exists()

    def _make_edge_cuts(self, config, min_x, min_y, max_x, max_y):
        w = max_x - min_x
        h = max_y - min_y
        mid_x = min_x + w / 2
        mid_y = min_y + h / 2
        pcb_size = config["pcb_size"]

        if config["pcb_shape"] == "circle":
            if pcb_size is not None:
                r = pcb_size / 2
            else:
                r = math.sqrt((w / 2) ** 2 + (h / 2) ** 2)

            fp_rect = (
                f"\t(fp_circle\n"
                f"\t\t(center {mid_x} {mid_y})\n"
                f"\t\t(end {mid_x - r} {mid_y})\n"
                f"\t\t(fill no)\n"
                f'\t\t(layer "Edge.Cuts")\n'
                f"\t)\n"
            )
        elif config["pcb_shape"] == "rect":
            if pcb_size is None:
                pcb_size = max(w, h)

            x0 = mid_x - pcb_size / 2
            x1 = mid_x + pcb_size / 2
            y0 = mid_y - pcb_size / 2
            y1 = mid_y + pcb_size / 2

            fp_rect = (
                f"\t(fp_rect\n"
                f"\t\t(start {x0} {y0})\n"
                f"\t\t(end {x1} {y1})\n"
                f"\t\t(fill no)\n"
                f'\t\t(layer "Edge.Cuts")\n'
                f"\t)\n"
            )
        else:
            raise ValueError(f"Invalid PCB shape: {config['pcb_shape']}")

        return fp_rect.encode()


def get_footprints_from_footprints_dir(config, params):
    footprints_dir = pathlib.Path(config["footprints_path"])

    if not footprints_dir.is_dir():
        raise ValueError(
            f"Footprints argument is not a directory: {config['footprints_path']}"
        )

    footprints = []

    for dir_entry in footprints_dir.iterdir():
        if not dir_entry.name.endswith(".kicad_mod"):
            continue
        footprint = Footprint(dir_entry, params)
        footprint.load(config)
        footprints.append(footprint)

    return footprints


def get_footprints_from_model_generator(config, params, generator_path):
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
        footprint_pathlib = pathlib.Path(
            f"{config['footprints_path']}/{footprint_dirname}/{model['title']}.kicad_mod"
        )

        if not footprint_pathlib.is_file():
            print(f"Warning: Missing footprint: {model['title']}")
            continue

        footprint = Footprint(footprint_pathlib, params)
        footprint.load(config)
        footprints.append(footprint)

    return footprints


def make_gallery(config, footprints):
    if not footprints:
        print("Warning: Non valid footprints found")
        return

    footprint_png = tempfile.NamedTemporaryFile(suffix=".png")
    gallery_png = tempfile.NamedTemporaryFile(suffix=".png")
    pcb_file = tempfile.NamedTemporaryFile(suffix=".kicad_pcb")

    footprint_start_pos = pcb_file.write(BLANK_PCB.encode())

    footprint_im = Image.new("RGBA", (10, 10))
    footprint_im.save(footprint_png.name)
    footprint_im.close()

    title_lines_max = 2
    title_stroke = 4
    title_im_font = ImageFont.truetype(config["font_path"], config["font_size"])

    gallery_cols = min(config["gallery_cols"], len(footprints))
    gallery_rows = (
        len(footprints) // gallery_cols + 1
        if len(footprints) % gallery_cols
        else len(footprints) // gallery_cols
    )
    gallery_im = None
    img_w = -1
    img_h = -1

    for footprint_index, footprint in enumerate(footprints):
        if config["show_progress"]:
            print(
                f"[{footprint_index + 1}/{len(footprints)}] {footprint.get_filename()}"
            )

        pcb_file.write(footprint.text)
        pcb_file.write(b")\n")
        pcb_file.file.flush()

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
            "-o",
            footprint_png.name,
            pcb_file.name,
        ]
        if config["raytrace"]:
            kicad_cli_args.append("--floor")
        subprocess.run(kicad_cli_args, capture_output=True)

        footprint_im = Image.open(footprint_png.name)

        if not gallery_im:
            img_w, img_h = footprint_im.size
            gallery_im = Image.new("RGBA", (img_w * gallery_cols, img_h * gallery_rows))
            gallery_im.save(gallery_png.name)
            if config["viewer"]:
                subprocess.Popen([config["viewer"], gallery_png.name])

        footprint_im_draw = ImageDraw.Draw(footprint_im)
        title_lines = footprint.get_title().split("\n")
        for title_line_index, title_line in enumerate(title_lines[:title_lines_max]):
            title_line_y = int(
                img_h * 0.95
                - (title_lines_max - 1 - title_line_index) * config["font_size"]
            )
            footprint_im_draw.text(
                (img_w / 2, title_line_y),
                title_line,
                anchor="ms",
                font=title_im_font,
                fill=(255, 255, 255),
                stroke_width=title_stroke,
                stroke_fill=(0, 0, 0),
            )

        footprint_im.save(footprint_png.name)

        col = footprint_index % gallery_cols
        row = footprint_index // gallery_cols
        gallery_im.paste(footprint_im, [img_w * col, img_h * row])
        footprint_im.close()

        if config["viewer"] and footprint_index and footprint_index % 3 == 0:
            gallery_im.save(gallery_png.name)

        pcb_file.seek(footprint_start_pos)
        pcb_file.truncate()

    gallery_im.save(gallery_png.name)

    if config["gallery_output_path"]:
        gallery_im.save(config["gallery_output_path"])
    else:
        print(f"Temporary gallery image: {gallery_png.name}")
        input("Press Enter to exit...")
    gallery_im.close()
    pcb_file.close()
    footprint_png.close()


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
    args_parser.add_argument(
        "-f", "--footprints", help="footprints directory", required=True
    )
    args_parser.add_argument("-p", "--params", help="customs JSON params file")
    args_parser.add_argument("-g", "--generator", help="model generator's YAML file")
    args_parser.add_argument("-o", "--output", help="gallery PNG image output")
    args_parser.add_argument(
        "--show-progress",
        action=argparse.BooleanOptionalAction,
        help="show generation progress",
    )
    args_parser.add_argument(
        "--models", default="/usr/share/kicad/3dmodels", help="3D models directory"
    )
    args_parser.add_argument(
        "--font-file",
        default="./fonts/Roboto/RobotoCondensed-Regular.ttf",
        help="font file",
    )
    args_parser.add_argument("--font-size", type=float, default="20", help="font size")
    args_parser.add_argument("--width", type=int, default=300, help="sub-image width")
    args_parser.add_argument("--height", type=int, default=300, help="sub-image height")
    args_parser.add_argument(
        "--cols", type=int, default=6, help="gallery columns count"
    )
    args_parser.add_argument(
        "--pcb-shape",
        choices=["circle", "rect"],
        default="circle",
        help="PCB shape type",
    )
    args_parser.add_argument(
        "--pcb-size", type=float, help="PCB size/diameter (or automatic)"
    )
    args_parser.add_argument(
        "--zoom", type=float, default="0.95", help="camera zoom amount"
    )
    args_parser.add_argument(
        "--orientation", type=vector3, default="[310, 0, 45]", help="camera orientation"
    )
    args_parser.add_argument(
        "--pan", type=vector3, default="[0, -1.5, 0]", help="camera pan"
    )
    args_parser.add_argument(
        "--with-params",
        action=argparse.BooleanOptionalAction,
        help="include only footprints with existing custom JSON parameters",
    )
    args_parser.add_argument(
        "--with-model",
        action=argparse.BooleanOptionalAction,
        help="include only footprints with existing 3D model",
    )
    args_parser.add_argument(
        "--raytrace", action=argparse.BooleanOptionalAction, help="use raytracing"
    )
    args_parser.add_argument(
        "--viewer", help="application used for viewing during generation"
    )
    args = args_parser.parse_args()

    config["show_progress"] = args.show_progress
    config["gallery_output_path"] = args.output
    config["footprints_path"] = args.footprints
    config["models_path"] = args.models
    config["font_path"] = args.font_file
    config["font_size"] = args.font_size
    config["img_w"] = args.width
    config["img_h"] = args.height
    config["gallery_cols"] = args.cols
    config["pcb_shape"] = args.pcb_shape
    config["pcb_size"] = args.pcb_size
    config["pcb_zoom"] = args.zoom
    config["pcb_ori"] = args.orientation
    config["pcb_pan"] = args.pan
    config["only_with_params"] = args.with_params
    config["only_with_model"] = args.with_model
    config["raytrace"] = args.raytrace
    config["viewer"] = args.viewer

    params = {}
    if args.params:
        get_params(params, args.params)

    if args.generator:
        footprints = get_footprints_from_model_generator(config, params, args.generator)
    else:
        footprints = get_footprints_from_footprints_dir(config, params)
        if config["only_with_model"]:
            footprints = list(filter(lambda f: f.has_model(config), footprints))
        footprints.sort(key=lambda f: f.pathlib_entry)

    make_gallery(config, footprints)


if __name__ == "__main__":
    main()
