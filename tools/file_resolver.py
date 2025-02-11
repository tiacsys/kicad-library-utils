""" "
This is a module to perform a common action in CI workflows: find a list of`
corresponding files in two directories, or (soon) in different git commits, and
present them in a way that can be used by other tools (e.g. a diff tool).
"""

import abc
import os
from pathlib import Path


class ResolvedFilePair:
    """
    Represents a pair of files that are to be compared.
    """

    # File A
    file1: Path
    # File B
    file2: Path
    # The name of the pair (hopefully unique), but stripped of any
    # prefix such that "re-rooting" it in the other file's 'context'
    # would find a counterpart (if it exists).
    #
    # This is useful for constructing the output file names.
    # It can still contain slashes, so it's not directly a file name, but
    # it's a relative path, so it can be used to construct a file name.
    #
    # E.g. for two files A and B, it's just B.
    #      for a files in directories A and C: A/B and C/D, it's D.
    #
    # Note that in either example, the actual file _names_ don't have
    # to match - there could be other criteria for declaring a resolved
    # match.
    name: str

    def __init__(self, file1, file2, name):
        self.file1 = Path(file1)
        self.file2 = Path(file2)
        self.name = Path(name)


class FileResolver(abc.ABC):
    """
    This is something that can resolve a list of files to be compared.
    """

    @property
    @abc.abstractmethod
    def files(self) -> list[ResolvedFilePair]:
        raise NotImplementedError("This is an abstract method")


class DirectFileResolver(FileResolver):
    """
    This is the obvious one that takes two (lists of) files and yields
    them as pairs.
    """

    def __init__(self, path1, path2, file_filter=None):
        if not isinstance(path1, list):
            path1 = [path1]
        if not isinstance(path2, list):
            path2 = [path2]

        if len(path1) != len(path2):
            raise ValueError("The two lists must have the same length")

        if file_filter is not None:
            path1 = [f for f in path1 if file_filter(f)]
            path2 = [f for f in path2 if file_filter(f)]

        self._files = list(ResolvedFilePair(path1, path2, path2))

    @property
    def files(self) -> list[ResolvedFilePair]:
        return self._files


class DirectoryFileResolver(FileResolver):
    """
    This is a class that takes two directories and finds all files in
    them and yields them as pairs.
    """

    def __init__(self, path1, path2, recursive=True, file_filter=None):

        if not os.path.isdir(path1) or not os.path.isdir(path2):
            raise ValueError("Both paths must be directories")

        # Iterate over the files in some directory, obeying the filter
        def list_files(path):
            if not recursive:
                for file in os.listdir(path):
                    if file_filter is None or file_filter(file):
                        yield os.path.join(path, file)
            else:
                for root, _, files in os.walk(path):
                    for file in files:
                        if file_filter is None or file_filter(file):
                            yield os.path.join(root, file)

        # for files yielded from a directory, get the relative path
        def get_relative_path(path):
            for f in list_files(path):
                yield os.path.relpath(f, path)

        rel_paths = set()

        for file in get_relative_path(path1):
            rel_paths.add(file)

        for file in get_relative_path(path2):
            rel_paths.add(file)

        # now we have the list of the files in either directory,
        # we can construct the counterparts in the other directories.
        # Note that some of these on either side may well NOT exist
        # (that would be file additions or deletions).

        self._files = []
        for rel_path in rel_paths:
            file1 = os.path.join(path1, rel_path)
            file2 = os.path.join(path2, rel_path)
            self._files.append(ResolvedFilePair(file1, file2, rel_path))

    @property
    def files(self) -> list[ResolvedFilePair]:
        return self._files


def get_resolver(path1, path2, file_filter=None):
    """
    Construct a resolver based on the paths given.
    """

    if os.path.isdir(path1) and os.path.isdir(path2):
        return DirectoryFileResolver(path1, path2, file_filter=file_filter)
    elif os.path.isfile(path1) and os.path.isfile(path2):
        return DirectFileResolver(path1, path2, file_filer=file_filter)

    raise ValueError(f"Not sure how to resolve the paths given: {path1}, {path2}")
