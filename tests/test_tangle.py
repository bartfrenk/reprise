from __future__ import annotations

import shutil
from argparse import Namespace
from pathlib import Path

import pytest

from reprise import tangle

SONGBOOK = """\
* Ábrete Corazón
#+begin_src chordpro :tangle (heading-tangle-path "build" "cho") :mkdirp yes
{title: Ábrete Corazón}
[C]la
#+end_src
"""


@pytest.mark.parametrize(
    ("s", "quoted"),
    [
        ("songs/pop.org", '"songs/pop.org"'),
        ('say "hi"', '"say \\"hi\\""'),
        ("C:\\songs", '"C:\\\\songs"'),
    ],
)
def test_quote(s: str, quoted: str) -> None:
    assert tangle.quote(s) == quoted


@pytest.mark.skipif(not shutil.which("emacs"), reason="emacs not installed")
def test_run_names_files_after_headings(tmp_path: Path) -> None:
    org = tmp_path / "songs.org"
    _ = org.write_text(SONGBOOK)

    tangle.run(Namespace(path=org))

    assert (tmp_path / "build" / "abrete-corazon.cho").read_text() == (
        "{title: Ábrete Corazón}\n[C]la\n"
    )
