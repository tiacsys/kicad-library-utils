#! /usr/bin/env python

# Note: cadquery is not imported here, because importing it is slow
# and this could be done just before the lines which make use of it.

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from file_resolver import get_resolver

if TYPE_CHECKING:
    import cadquery as cq


class _LoadStepFileError(Exception):
    def __init__(self, path: Path):
        self.path = path
        self.message = f"Can't load STEP file: {path}"
        super().__init__(self.message)


@dataclass
class DiffColors:
    unchanged: "cq.Color"
    added: "cq.Color"
    removed: "cq.Color"


@dataclass
class StepDiffStats:
    """
    All the statistics about the volume difference between two STEP files.
    """

    old_volume: float
    new_volume: float
    added_volume: float
    removed_volume: float

    @property
    def changed_volume(self) -> float:
        return self.added_volume + self.removed_volume

    @property
    def added_volume_proportion(self) -> float:
        if self.old_volume == 0:
            if self.new_volume == 0:
                return 0.0
            return float("inf")

        return self.added_volume / self.old_volume

    @property
    def removed_volume_proportion(self) -> float:
        if self.old_volume == 0:
            return 0.0

        return self.removed_volume / self.old_volume

    @property
    def changed_volume_proportion(self) -> float:
        if self.old_volume == 0:
            if self.new_volume == 0:
                return 0.0
            return float("inf")

        return self.changed_volume / self.old_volume


@dataclass
class StepDiffResult:
    """All the information about the difference between two STEP files."""

    model_name: str
    old_model: "cq.Workplane"
    new_model: "cq.Workplane"
    model_added: "cq.Workplane"
    model_removed: "cq.Workplane"
    stats: StepDiffStats


def load_step_file(path: Path) -> "cq.Workplane":
    import cadquery as cq

    try:
        model = cq.importers.importStep(str(path))
        return model
    except ValueError:
        raise _LoadStepFileError(path)


def get_step_diff(old_path: Path, new_path: Path) -> StepDiffResult:

    old_model = load_step_file(old_path)
    new_model = load_step_file(new_path)

    old_volume = old_model.val().Volume()
    new_volume = new_model.val().Volume()

    if old_volume == 0 or new_volume == 0:
        model_added = new_model
        model_removed = old_model
    else:
        model_added = new_model.cut(old_model)
        model_removed = old_model.cut(new_model)

    added_volume = model_added.val().Volume()
    removed_volume = model_removed.val().Volume()

    return StepDiffResult(
        model_name=old_path.stem,
        old_model=old_model,
        new_model=new_model,
        model_added=model_added,
        model_removed=model_removed,
        stats=StepDiffStats(
            old_volume=old_volume,
            new_volume=new_volume,
            added_volume=added_volume,
            removed_volume=removed_volume,
        ),
    )


def save_step_diff(
    step_diff: StepDiffResult, output_file_path: Path, colors: DiffColors
) -> None:
    import cadquery as cq

    if output_file_path.is_dir():
        print(f"Can't overwrite directory: {output_file_path}")
        return

    try:
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"Make directory permission denied: {output_file_path.parent}")
        return
    except (FileExistsError, NotADirectoryError):
        print(f"Can't make directory: {output_file_path.parent}")
        return

    try:
        output_file_path.touch()
    except PermissionError:
        print(f"Write permission denied: {output_file_path}")
        return

    if step_diff.old_model.val().Volume() == 0:
        unchanged = step_diff.old_model
    else:
        unchanged = step_diff.old_model.intersect(step_diff.new_model)

    assembly = cq.Assembly(name=step_diff.model_name)
    assembly = assembly.add(
        unchanged,
        name="unchanged",
        color=colors.unchanged,
    )
    assembly = assembly.add(
        step_diff.model_added,
        name="added",
        color=colors.added,
    )
    assembly = assembly.add(
        step_diff.model_removed,
        name="removed",
        color=colors.removed,
    )
    assembly.export(str(output_file_path), "STEP")


def color(arg) -> tuple[float, float, float, float]:
    arg_re = re.compile(r"^([^,]*),([^,]*),([^,]*)(,[^,]*)?$")
    arg_match = arg_re.match(arg)
    assert arg_match
    arg = arg.split(",")
    if len(arg) == 3:
        arg.append("1.0")
    arg = tuple(map(float, arg))

    assert len(arg) == 4
    assert all(0.0 <= c <= 1.0 for c in arg)

    import cadquery as cq

    return cq.Color(*arg)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Check STEP files for changes. You can provide two files, "
            "two directories, or a local Git repository. "
        )
    )
    parser.add_argument(
        "path1", type=Path, help="STEP file, directory, or local Git repo."
    )
    parser.add_argument(
        "path2", type=Path, nargs="?", help="Second STEP file, or directory."
    )
    parser.add_argument(
        "-g",
        "--glob",
        action="append",
        help="Filter files with a GLOB expression.",
    )
    parser.add_argument(
        "--ignore-missing",
        action="store_true",
        help="Ignore missing files when comparing two directories or a repo.",
    )
    parser.add_argument(
        "-e",
        "--epsilon",
        type=float,
        default="0.001",
        help="Volume change epsilon (default 0.1%%).",
    )
    parser.add_argument(
        "-o", "--diff-output", type=Path, help="Diff output directory or file."
    )

    # Note: The colors here are have different values for each main
    # color channel on purpose. If one color is "0.0, 0.0, 0.5", and
    # another is "0.0, 0.5, 0.0", then KiCad draws those two color as
    # if they are the same!
    parser.add_argument(
        "--diff-unchanged-color",
        type=color,
        default=color("0.0, 0.0, 0.50001, 1.0"),
        help="Diff unchanged color (default '0.0, 0.0, 0.5, 1.0').",
    )
    parser.add_argument(
        "--diff-added-color",
        type=color,
        default=color("0.0, 0.50002, 0.0, 1.0"),
        help="Diff added color (default '0.0, 0.5, 0.0, 1.0').",
    )
    parser.add_argument(
        "--diff-removed-color",
        type=color,
        default=color("0.50003, 0.0, 0.0, 1.0"),
        help="Diff removed color (default '0.5, 0.0, 0.0, 1.0').",
    )

    args = parser.parse_args()

    colors = DiffColors(
        unchanged=args.diff_unchanged_color,
        added=args.diff_added_color,
        removed=args.diff_removed_color,
    )

    def filter_files(path: Path) -> bool:
        path = Path(path)

        if path.suffix.lower() != ".step":
            return False

        if args.glob:
            return any(path.full_match(g) for g in args.glob)
        else:
            return True

    errors_count = 0
    resolver = get_resolver(args.path1, args.path2, filter_files)
    files_checked = False

    for pair in sorted(resolver.files, key=lambda pair: pair.name):
        old_file = Path(pair.file1)
        new_file = Path(pair.file2)

        if not old_file.exists() or not new_file.exists():
            if not args.ignore_missing:
                errors_count += 1
                print(f"{pair.name}: MISSING")
            continue

        files_checked = True
        print(f"{pair.name}: ", end="", flush=True)
        try:
            step_diff = get_step_diff(old_file, new_file)
        except _LoadStepFileError as e:
            print("ERROR")
            print(f"WARNING: {e.message}")
            errors_count += 1
            continue

        if step_diff.stats.changed_volume_proportion > args.epsilon:
            print(f"CHANGED ({step_diff.stats.changed_volume_proportion * 100:.2f}%)")
            errors_count += 1
            if args.diff_output:
                assert isinstance(args.diff_output, Path)
                if args.path1.is_file():
                    diff_file = args.diff_output
                else:
                    diff_file = args.diff_output / pair.name

                print(f"Saving diff: {diff_file}")
                save_step_diff(step_diff, diff_file, colors)
        else:
            print("OK")

    if errors_count:
        print(
            f"WARNING: {errors_count} {'error' if errors_count == 1 else 'errors'} found"
        )
    elif not files_checked:
        print("WARNING: No files checked")

    return 1 if errors_count else 0


if __name__ == "__main__":
    sys.exit(main())
