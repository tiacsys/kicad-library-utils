#! /usr/bin/env python

import cadquery as cq

import argparse
import logging
import sys
import os
import pathlib

sys.path.append(os.path.join(os.path.dirname(__file__), "."))

from file_resolver import get_resolver


class StepDiffer:

    def __init__(self, epsilon: float):
        self.epsilon = epsilon
        self.added_colour = cq.Color(0.0, 0.5, 0.0)
        self.removed_colour = cq.Color(0.5, 0.0, 0.0)

    def perform_diff(self, file1, file2):
        object1 = cq.importers.importStep(str(file1))
        object2 = cq.importers.importStep(str(file2))

        object1_volume = object1.val().Volume()
        object2_volume = object2.val().Volume()

        added_shape = object2.cut(object1)
        removed_shape = object1.cut(object2)

        added_volume = added_shape.val().Volume()
        removed_volume = removed_shape.val().Volume()

        difference_volume = added_volume + removed_volume

        diff_volume_proportion = difference_volume / object1_volume

        logging.info(f"Object 1 volume: {object1_volume:.2f}")
        logging.info(f"Object 2 volume: {object2_volume:.2f}")
        logging.info(f"Added volume: {added_volume:.2f}")
        logging.info(f"Removed volume: {removed_volume:.2f}")
        logging.info(f"Difference volume: {difference_volume:.2f}")
        logging.info(f"Proportional difference: {100 * diff_volume_proportion:.2f}%")

        significant_diff = diff_volume_proportion > self.epsilon

        assembly = None

        if significant_diff:

            assembly = cq.Assembly() \
                .add(added_shape,
                     name="added",
                     color=self.added_colour) \
                .add(removed_shape,
                     name="removed",
                     color=self.removed_colour)

        return significant_diff, assembly


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Diff two STEP files")
    parser.add_argument("-o", "--output",
                        help="Output difference shape to file")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase verbosity")
    parser.add_argument("-z", "--expect-zero", action="store_true",
                        help="Expect zero difference (return code non-zero if not)")
    parser.add_argument("-e", "--epsilon", type=float, default=0.001,
                        help="Volume epsilon for zero check (default 0.1%%)")

    parser.add_argument("path1", help="First file or directory")
    parser.add_argument("path2",
                        help="Second file or dir (dir uses all files and compares each against path1)")

    args = parser.parse_args()

    if args.verbose > 0:
        logging.basicConfig(level=logging.INFO)
    elif args.verbose > 1:
        logging.basicConfig(level=logging.DEBUG)

    def step_filter(file: pathlib.Path):
        return file.endswith(".step")

    file_resolver = get_resolver(args.path1, args.path2, file_filter=step_filter)

    differ = StepDiffer(args.epsilon)

    # How to create the output directory
    def create_output_dir():
        os.makedirs(args.output, exist_ok=True)

    for resolved_pair in file_resolver.files:

        logging.info(f"Comparing {resolved_pair.file1} and {resolved_pair.file2}")

        significant_diff, diff_model = differ.perform_diff(
            resolved_pair.file1, resolved_pair.file2
        )

        if args.output is not None:
            create_output_dir()
            out_filename = os.path.join(args.output, resolved_pair.name)
            logging.debug(f"Writing output to {resolved_pair.name.name}")
            diff_model.save(out_filename, "STEP")

        if args.expect_zero and significant_diff:
            sys.exit(1)

    sys.exit(0)
