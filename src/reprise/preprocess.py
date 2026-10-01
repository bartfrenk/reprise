# pyright: reportUnusedCallResult = false

from __future__ import annotations

import re
import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self, override


def create_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Normalize a tangled ChordPro file")
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", "-o", type=Path, required=False)
    return parser


PATTERN = re.compile(r"\{(?P<boundary>start|end)_of_(?P<kind>\w+)(?: (?P<name>\w+))?\}")


@dataclass
class Env:
    kind: str
    name: str | None

    @classmethod
    def from_match(cls, m: re.Match[str]) -> Self:
        return cls(kind=m["kind"], name=m["name"])

    def start(self) -> Iterator[str]:
        if self.name:
            yield f"{{start_of_{self.kind}: {self.name}}}"
        else:
            yield f"{{start_of_{self.kind}}}"

    def end(self) -> Iterator[str]:
        yield f"{{end_of_{self.kind}}}"

    def transform(self, line: str) -> Iterator[str]:
        yield line.removesuffix("\n")


@dataclass
class Description(Env):
    """Environment that flows the text by removing newlines"""

    buf: str = ""

    @override
    def start(self) -> Iterator[str]:
        yield from super().start()

    @override
    def end(self) -> Iterator[str]:
        if self.buf:
            yield self.buf
        yield from super().end()

    @override
    def transform(self, line: str) -> Iterator[str]:
        if not line.strip():
            if self.buf:
                yield self.buf
            yield line.removesuffix("\n")
            self.buf = ""
        else:
            if self.buf:
                self.buf = self.buf + " " + line.removesuffix("\n")
            else:
                self.buf = line.removesuffix("\n")


def env_from_match(m: re.Match[str]) -> Env:
    match m["kind"]:
        case "description":
            return Description.from_match(m)
        case _:
            return Env.from_match(m)


@dataclass
class State:
    env: Env | None

    @classmethod
    def init(cls) -> Self:
        return cls(None)

    def update(self, marker: Marker) -> Iterator[str]:
        match marker.boundary:
            case "start":
                self.env = marker.env
                yield from self.env.start()
            case "end" if self.env and self.env.kind == marker.env.kind:
                yield from self.env.end()
                self.env = None
            case _:
                print(self)
                print(f"Invalid marker {marker}", file=sys.stderr)

    def transform(self, line: str) -> Iterator[str]:
        if self.env:
            yield from self.env.transform(line)
        else:
            yield line.removesuffix("\n")


@dataclass
class Marker:

    boundary: Literal["start", "end"]
    env: Env

    @classmethod
    def from_match(cls, m: re.Match[str]) -> Self:
        match m["boundary"]:
            case "start":
                return cls(boundary="start", env=env_from_match(m))
            case "end":
                return cls(boundary="end", env=env_from_match(m))
            case s:
                raise ValueError(f"Invalid boundary '{s}'")

    @classmethod
    def from_line(cls, line: str) -> Self | None:
        if m := PATTERN.match(line):
            return cls.from_match(m)
        return None

    @override
    def __str__(self) -> str:
        return f"{self.boundary}_of_{self.env.kind}: {self.env.name}"


@contextmanager
def out(path: Path | None, mode: str = "wt"):
    if not path:
        yield sys.stdout
    else:
        with open(path, mode) as fh:
            yield fh


def process(path: Path) -> Iterator[str]:
    state = State.init()
    with open(path, "r") as fh:
        for line in fh:
            if marker := Marker.from_line(line):
                yield from state.update(marker)
            else:
                yield from state.transform(line)


def run(args: Namespace) -> None:
    data = "\n".join(process(args.path))  # pyright: ignore[reportAny]
    with out(args.output) as fh:  # pyright: ignore[reportAny]
        fh.write(data)
