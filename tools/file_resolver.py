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

        self._files = [ResolvedFilePair(p[0], p[1], p[1]) for p in zip(path1, path2)]

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

        # Iterate over the files in some directory
        def list_files(path):
            if not recursive:
                for file in os.listdir(path):
                    yield os.path.join(path, file)
            else:
                for root, _, files in os.walk(path):
                    for file in files:
                        yield os.path.join(root, file)

        # for files yielded from a directory, get the relative path
        def get_relative_path(path):
            for f in list_files(path):
                rel_path = os.path.relpath(f, path)
                if file_filter is None or file_filter(rel_path):
                    yield rel_path

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


class GitIndexResolver(FileResolver):
    """
    This is a class that resolves files changed (but not yet committed)
    in a Git repository
    """

    def __init__(self, repo, file_filter=None):
        self.repo = repo

        import tempfile

        # Note: The git module is imported here and not at the top
        # level for this module, because it's an external library, and
        # this module could be used without it too.
        import git

        self.repo = git.Repo(repo)
        self.repo_diffs = self.repo.index.diff(None)
        self.file_filter = file_filter

        # Lives until the resolver is deleted
        self.temp_dir = tempfile.TemporaryDirectory(prefix="kicad-library-utils-")

    @property
    def files(self):

        files = []

        for diff in self.repo_diffs:
            if not diff.a_path:
                continue

            if diff.a_path != diff.b_path:
                continue

            assert diff.change_type in ["M", "D"]

            rel_path = diff.a_path

            if self.file_filter is not None:
                if not self.file_filter(Path(rel_path)):
                    continue

            self.repo.index.checkout(rel_path, prefix=f"{self.temp_dir.name}{os.sep}")

            temp_file = os.path.join(self.temp_dir.name, rel_path)
            curr_file = os.path.join(self.repo.working_tree_dir, rel_path)
            files.append(ResolvedFilePair(temp_file, curr_file, rel_path))

        return files


def get_resolver(path1: Path, path2=None, file_filter=None):
    """
    Construct a resolver based on the paths given.
    """

    path1 = Path(path1)

    if not path1.exists():
        raise ValueError(f"Path doesn't exist: {path1}")

    if path2 is not None:
        path2 = Path(path2)

        if not path2.exists():
            raise ValueError(f"Path doesn't exist: {path2}")

        if path1.is_dir() and path2.is_dir():
            return DirectoryFileResolver(path1, path2, file_filter=file_filter)

        if path1.is_file() and path2.is_file():
            return DirectFileResolver(path1, path2, file_filter=file_filter)
    else:
        if path1.is_dir() and (path1 / ".git").is_dir():
            return GitIndexResolver(path1, file_filter=file_filter)

    raise ValueError(
        f"Two directories, two files, or a local git repository must be provided: {path1}"
        + ("" if path2 is None else f", {path2}")
    )
