"""Minimal git-history walker (vendored): list a file's versions oldest->newest.

Pure stdlib (``git`` subprocess only) — no network beyond git, no ML.
"""
import subprocess
from typing import List, Optional, Tuple


def _git(repo_path: str, args: List[str]) -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", repo_path] + args,
                             capture_output=True, text=True, check=True)
        return out.stdout
    except subprocess.CalledProcessError:
        return None


def walk_file_history(repo_path: str, file_path: str) -> List[Tuple[str, int, str]]:
    """Return [(commit_hash, unix_ts, file_content), ...] oldest->newest.

    Follows renames: ``--follow`` reports the commits, and ``--name-status`` tells us the path
    the file had *at each commit*. Older revisions recorded under a previous name are fetched
    under that historical name instead of being silently skipped (``git show <commit>:<path>``
    would fail for the current path at a pre-rename commit).
    """
    # NOTE: --follow does NOT compose with --reverse (git follows only to the first rename when
    # reversed), so we read newest->oldest and reverse in Python. A leading NUL (%x00) per commit
    # makes the header unambiguous even when a subject or path contains spaces; --name-status
    # appends the path(s) touched in that commit so we can fetch each revision under its own name.
    log = _git(repo_path, ["log", "--follow", "--format=%x00%H %ct",
                           "--name-status", "--", file_path])
    if not log:
        return []
    versions: List[Tuple[str, int, str]] = []
    for record in log.split("\x00"):
        rec_lines = [ln for ln in record.splitlines() if ln.strip()]
        if not rec_lines:
            continue
        header = rec_lines[0].split()
        if len(header) < 2:
            continue
        commit, ts = header[0], int(header[1])
        # The file's path AT this commit = the last tab-field of the name-status line. For a
        # rename ("R100\told\tnew") that is the new path; for A/M it is the single path. Fall
        # back to the query path if no status line is present.
        path_at = file_path
        for st in rec_lines[1:]:
            fields = st.split("\t")
            if len(fields) >= 2:
                path_at = fields[-1]
        content = _git(repo_path, ["show", f"{commit}:{path_at}"])
        if content is not None:
            versions.append((commit, ts, content))
    versions.reverse()          # git gave newest->oldest; the contract is oldest->newest
    return versions
