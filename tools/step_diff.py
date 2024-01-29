#! /usr/bin/env python

import cadquery as cq

import argparse
import logging
import sys
import os
import pathlib


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


class FileFinderDirect():
    """
    Directly find the file (doesn't look anything up)
    """

    def __init__(self, path1):
        self.path1 = path1

    def find_files(self, path2):
        return self.path1, path2


class SameFileInEachDir:

    def __init__(self, path1, path2):
        self.path1 = pathlib.Path(path1)
        self.path2 = pathlib.Path(path2)

    def find_files(self, tail):
        return self.path1 / tail, self.path2 / tail


def get_all_steps_in_dir(path):
    """
    Get all STEP filenames in a directory
    """
    files = [pathlib.Path(x).name for x in os.listdir(path)]
    files = [x for x in files if x.endswith(".step")]
    return files


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

    parser.add_argument("path1", help="First file or dir")
    parser.add_argument("path2",
                        help="Second file or dir (dir uses all files and compares each against path1)")

    args = parser.parse_args()

    if args.verbose > 0:
        logging.basicConfig(level=logging.INFO)
    elif args.verbose > 1:
        logging.basicConfig(level=logging.DEBUG)

    if os.path.isfile(args.path1) and os.path.isfile(args.path2):
        file_finder = FileFinderDirect(args.path1)
    elif os.path.isdir(args.path1) and os.path.isdir(args.path2):
        file_finder = SameFileInEachDir(args.path2, args.path2)
    else:
        raise RuntimeError("Can't do file lookup of this type yet")

    differ = StepDiffer(args.epsilon)

    if os.path.isfile(args.path2):
        # Single file
        files = [args.path2]
    else:
        # Iterate dir 2, and look up in dir 1
        files = get_all_steps_in_dir(args.path2)

    # How to create the output directory
    def create_output_dir():
        os.makedirs(args.output, exist_ok=True)

    for file in files:

        file1, file2 = file_finder.find_files(file)

        logging.info(f"Comparing {file1} and {file2}")

        significant_diff, diff_model = differ.perform_diff(file1, file2)

        if args.output is not None:
            create_output_dir()
            out_filename = os.path.join(args.output, pathlib.Path(file).name)
            logging.debug(f"Writing output to {file}")
            diff_model.save(out_filename, "STEP")

        if args.expect_zero and significant_diff:
            sys.exit(1)

    sys.exit(0)
