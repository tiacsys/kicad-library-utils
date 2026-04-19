""" "
This is a module to perform a common action in CI workflows: find a list of`
corresponding files in two directories, or (soon) in different git commits, and
present them in a way that can be used by other tools (e.g. a diff tool).
"""

import abc
import logging
import os
from pathlib import Path


class ResolvedFilePair:
    """
    Represents a pair of files that are to be compared.
    There is no guarantee that either of those files exists.
    The user should call .exists() on them before accessing them.
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
    name: Path

    def __init__(self, file1, file2, name):
        self.file1 = Path(file1)
        self.file2 = Path(file2)
        self.name = Path(name)

    def __repr__(self):
        return f'ResolvedFilePair("{self.file1}", "{self.file2}", "{self.name}")'


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
        self.repo_diffs = self.repo.index.diff(None)  # get the uncommitted changes
        self.file_filter = file_filter
        self.index = self.repo.index

        # Lives until the resolver is deleted
        # TODO: it does not get deleted, because we are not using this as a context
        #       we need to implement the __enter__ and __exit__ method
        self.temp_dir = Path(
            tempfile.TemporaryDirectory(prefix="kicad-library-utils-").name
        )

    @property
    def files(self):

        files = []

        for diff in self.repo_diffs:
            # default file paths and names
            rel_path = (
                diff.a_path
            )  # this is the 'old' filename, relative to the git root directory
            curr_file = Path(self.repo.working_tree_dir).joinpath(rel_path)
            prev_file = Path(
                "does_not_exist"
            )  # this is a workaround because we cannot create Path(None)

            # skip this change if we want to filter it out
            if self.file_filter is not None:
                if not self.file_filter(Path(rel_path)):
                    continue

            # depending on the change type (addition, deletion, move, ...) we
            # need to perform different actions
            match diff.change_type:
                case "D":
                    # Deleted file, that means the current file is none
                    curr_file = Path("does_not_exist")
                    # we need to checkout the old file, use empty string as marker that
                    # the prev_file needs to be fetched from git
                    prev_file = ""
                    logging.debug(f"File {rel_path} was deleted.")
                case "A":
                    # File was added there is no prev_file
                    prev_file = Path("does_not_exist")
                    logging.debug(f"File {rel_path} was added.")
                case "M":
                    # Modified file, the old and new name are the same
                    # they exists in both trees
                    # mark prev_file so we fetch it from git
                    prev_file = ""
                    logging.debug(f"File {rel_path} was modified.")
                case "R":
                    # currently we don't track renames
                    # We could extend ResolvedFilePair have a 'renamed' property
                    continue
                case "C":
                    # file was copied, to nothing
                    # one could argue that this should be handled like an addition...
                    continue
                case _:
                    # Unknown change type, don't to anything but warn
                    # This could be
                    logging.warn(
                        f"Change-type {diff.change_type} of file {rel_path} ignored"
                    )
                    continue

            # we want to pull the contents of the previous version from git
            if prev_file == "":
                # the file we want to check out might be in a subdir,
                # we need to create it
                prev_file = self.temp_dir.joinpath(rel_path)
                prev_file.parent.mkdir(parents=True, exist_ok=True)

                # create a new file, write the blob contents to it
                with open(prev_file, "wb") as checkout_file:
                    diff.a_blob.stream_data(checkout_file)

            # we set all required variables (some might be None), add this to the list of changed files
            files.append(ResolvedFilePair(prev_file, curr_file, rel_path))

        return files


class GitHistoryResolver(GitIndexResolver):
    """
    This is a class that resolves files changed between two commits
    in a Git repository
    """

    def __init__(self, repo, commit_id, file_filter=None):
        # do the same initial setup as the GitIndexResolver
        super().__init__(repo, file_filter)

        try:
            # select the first commit that matches the passed commit_id
            commit_iterator = self.repo.iter_commits(all=True)
            self.commit = list(
                filter(lambda commit: str(commit) == commit_id, commit_iterator)
            )[0]
        except IndexError:
            raise ValueError(f"Could not resolve commit with id {commit_id}")

        # point the index we use to checkout file to the commit
        self.index = self.commit.repo.index
        # now build the diff based on the commit we just extracted
        head = self.repo.commit()
        self.repo_diffs = self.commit.diff(head)


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
            # path2 could be a git revision-id
            if len(path2.name) == 40 and path1.is_dir() and (path1 / ".git").is_dir():
                return GitHistoryResolver(
                    repo=path1, commit_id=path2.name, file_filter=file_filter
                )
            else:
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
