# pyright: reportUnusedCallResult = false
"""Tangle the ChordPro blocks of an Org songbook with Emacs.

Each block is written to a file named after its heading, using
`heading-tangle-path` from the bundled tangle.el.
"""

from __future__ import annotations

import subprocess
from argparse import ArgumentParser, Namespace
from importlib.resources import as_file, files
from pathlib import Path


def create_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Tangle an Org songbook into ChordPro files")
    parser.add_argument("path", type=Path, help="Org file to tangle")
    return parser


def run(args: Namespace) -> None:
    path: Path = args.path  # pyright: ignore[reportAny]
    with as_file(files("reprise") / "tangle.el") as el:
        subprocess.run(
            [
                "emacs",
                "--batch",
                "--eval",
                "(require 'org)",
                "-l",
                str(el),
                "--eval",
                f"(org-babel-tangle-file {quote(str(path))})",
            ],
            check=True,
        )


def quote(s: str) -> str:
    """Quote S as an Emacs Lisp string."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
