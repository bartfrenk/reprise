from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from reprise import preprocess


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "song.cho"
    _ = path.write_text(text)
    return path


def test_rewrites_named_environment_marker(tmp_path: Path) -> None:
    path = write(tmp_path, "{start_of_verse chorus1}\n[C]la\n{end_of_verse}\n")

    assert list(preprocess.process(path)) == [
        "{start_of_verse: chorus1}",
        "[C]la",
        "{end_of_verse}",
    ]


def test_flows_description_paragraphs(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "{start_of_description}\nline one\nline two\n\npara two\n{end_of_description}\n",
    )

    assert list(preprocess.process(path)) == [
        "{start_of_description}",
        "line one line two",
        "",
        "para two",
        "{end_of_description}",
    ]


def test_reports_unmatched_end_marker(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, "{start_of_verse}\n{end_of_chorus}\n")

    _ = list(preprocess.process(path))

    assert "Invalid marker end_of_chorus" in capsys.readouterr().err


def test_run_writes_output_file(tmp_path: Path) -> None:
    path = write(tmp_path, "{start_of_verse}\nla\n{end_of_verse}\n")
    output = tmp_path / "out.cho"

    preprocess.run(Namespace(path=path, output=output))

    assert output.read_text() == "{start_of_verse}\nla\n{end_of_verse}"
