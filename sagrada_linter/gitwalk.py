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
    """Return [(commit_hash, unix_ts, file_content), ...] oldest->newest."""
    log = _git(repo_path, ["log", "--reverse", "--follow", "--format=%H %ct", "--", file_path])
    if not log:
        return []
    versions: List[Tuple[str, int, str]] = []
    for line in log.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        commit, ts = parts[0], int(parts[1])
        content = _git(repo_path, ["show", f"{commit}:{file_path}"])
        if content is not None:
            versions.append((commit, ts, content))
    return versions
