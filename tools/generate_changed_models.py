#!/usr/bin/env python
import argparse
import os
import subprocess
import tempfile

from yaml_diff import compare_yamls


def emit_changed_generator_invocations(prev_hash: str, cur_hash: str):
    with tempfile.TemporaryDirectory() as tmpdirname:
        basedir = (
            subprocess.check_output("git rev-parse --show-toplevel", shell=True)
            .strip()
            .decode("utf-8")
        )
        changed_files = set(
            subprocess.check_output(
                f"git diff-tree --diff-filter=M --no-commit-id --oneline --name-only -r {prev_hash} {cur_hash}",
                shell=True,
            )
            .decode("utf-8")
            .split("\n")
        )
        changed_files.remove("")
        subprocess.run(
            f"git --work-tree={tmpdirname} checkout {prev_hash} -- .", shell=True
        )
        invocations = []
        for i in changed_files:
            if ".yaml" in i and "3d-model" in i:
                genname = i.split("/")[1]
                diff = compare_yamls(
                    os.path.join(tmpdirname, i), os.path.join(basedir, i)
                )
                if diff is not None:
                    added, changed, deleted = diff
                    for part in added.union(changed):
                        invocations.append(f"./generator.py -l {genname} -p {part} -v")
        return invocations


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Find modified yamls in 3d generator data and emit generator invocations."
    )
    parser.add_argument(
        "--prev", "-p", type=str, help="old commit hash", default="HEAD~1"
    )
    parser.add_argument("--cur", "-c", type=str, help="new commit hash", default="HEAD")
    parser.add_argument(
        "--output", "-o", type=str, help="output directory for 3d models", required=True
    )
    parser.add_argument(
        "--isolated", "-i", action="store_true", help="run in isolated shell"
    )

    args = parser.parse_args()
    basedir = (
        subprocess.check_output("git rev-parse --show-toplevel", shell=True)
        .strip()
        .decode("utf-8")
    )

    invocations = emit_changed_generator_invocations(args.prev, args.cur)
    os.chdir(os.path.join(basedir, "3d-model-generators"))

    for i in invocations:
        command = f"{i} -o {os.path.realpath(args.output)}"

        if args.isolated:
            command = f'env -i HOME="$HOME" bash -l -c "{command}"'
        print(f"Running {command}")
        subprocess.run(command, shell=True)
