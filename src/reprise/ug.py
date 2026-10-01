# pyright: reportUnusedCallResult = false
"""Convert an Ultimate Guitar chords page into a ChordPro file.

Pages such as https://es.ultimate-guitar.com/tab/shimshai/abuelito-fuego-chords-2396375
embed the song as JSON in a `js-store` element. Its content is plain text with
chords marked as [ch]Am[/ch] on lines above the lyrics, and section headers
such as [Verse] or [Chorus] on lines of their own.

The script writes the song as a .cho file with the chords placed inline and
adds a definition to the `chords` array of the ChordPro configuration for every
chord that ChordPro does not know yet, using the voicing shown on the page.
"""

from __future__ import annotations

import json
import re
import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from reprise.brazile import CONFIG, unknown_chords, update_config

CHORD = re.compile(r"\[ch\](.*?)\[/ch\]")
HEADER = re.compile(r"^\[(?P<name>[A-Za-z][A-Za-z -]*?)\s*(?P<number>\d+)?\]$")

# Section headers that map onto a ChordPro environment; others become comments.
SECTIONS = {
    "verse": "verse",
    "chorus": "chorus",
    "pre-chorus": "prechorus",
    "prechorus": "prechorus",
    "bridge": "bridge",
    "intro": "intro",
    "outro": "outro",
    "interlude": "intermezzo",
    "instrumental": "intermezzo",
}


def create_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Convert an Ultimate Guitar chords page to ChordPro")
    parser.add_argument("source", help="URL or local path of the chords page")
    parser.add_argument("--output", "-o", type=Path, required=False)
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG,
        help=f"ChordPro config to update (default: {CONFIG})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the chord definitions instead of adding them to the config",
    )
    return parser


# ---------------------------------------------------------------- Page parsing


def fetch(source: str) -> str:
    if re.match(r"https?://", source):
        request = Request(source, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request) as response:  # pyright: ignore[reportAny]
            data: bytes = response.read()  # pyright: ignore[reportAny]
        return data.decode("utf-8", errors="replace")
    return Path(source).read_text()


@dataclass
class Page:
    title: str
    artist: str
    capo: int
    key: str
    content: str
    # Chord name -> UG voicings, the first being the one shown on the page.
    applicature: dict[str, list[dict[str, Any]]]


def parse_page(html: str) -> Page:
    m = re.search(r'class="js-store" data-content="([^"]*)"', html)
    if m is None:
        sys.exit("No song data (js-store) found on the page")
    data = json.loads(unescape(m[1]))["store"]["page"]["data"]  # pyright: ignore[reportAny]
    tab = data["tab"]  # pyright: ignore[reportAny]
    view = data["tab_view"]  # pyright: ignore[reportAny]
    applicature: dict[str, list[dict[str, Any]]] = (
        view.get("applicature") or {}
    )  # pyright: ignore[reportAny]
    meta: dict[str, Any] = view.get("meta") or {}  # pyright: ignore[reportAny]
    return Page(
        title=tab["song_name"],  # pyright: ignore[reportAny]
        artist=tab["artist_name"],  # pyright: ignore[reportAny]
        capo=int(meta.get("capo") or 0),  # pyright: ignore[reportAny]
        key=tab.get("tonality_name") or "",  # pyright: ignore[reportAny]
        content=view["wiki_tab"]["content"],  # pyright: ignore[reportAny]
        applicature=applicature,
    )


# ------------------------------------------------------------ ChordPro output


def chords_at(line: str) -> list[tuple[int, str]]:
    """Chords of a marked-up line with their column in the rendered line."""
    found: list[tuple[int, str]] = []
    offset = 0
    for m in CHORD.finditer(line):
        found.append((m.start() - offset, m[1].strip()))
        offset += len(m[0]) - len(m[1])
    return found


def is_chord_line(line: str) -> bool:
    return bool(CHORD.search(line)) and not CHORD.sub("", line).strip(" |-x0123456789")


def is_lyric_line(line: str) -> bool:
    return bool(line.strip()) and not is_chord_line(line) and not HEADER.match(line.strip())


def merge(chords: list[tuple[int, str]], lyrics: str) -> str:
    """Insert the chords into the lyrics at their columns."""
    width = max(col for col, _ in chords)
    text = lyrics.ljust(width)
    for col, name in reversed(chords):
        text = text[:col] + f"[{name}]" + text[col:]
    return text.rstrip()


def chord_only(chords: list[tuple[int, str]]) -> str:
    return " ".join(f"[{name}]" for _, name in chords)


def body_lines(content: str) -> Iterator[str]:
    lines = [
        line.rstrip()
        for line in content.replace("\r\n", "\n")
        .replace("[tab]", "")
        .replace("[/tab]", "")
        .split("\n")
    ]
    section: str | None = None
    # Chords of the previous line, waiting to see whether lyrics follow.
    pending: list[tuple[int, str]] | None = None
    for line in lines:
        if pending is not None:
            if is_lyric_line(line):
                yield merge(pending, line)
                pending = None
                continue
            yield chord_only(pending)
            pending = None
        if m := HEADER.match(line.strip()):
            if section is not None:
                yield f"{{end_of_{section}}}"
            name, number = m["name"].strip(), m["number"]
            section = SECTIONS.get(name.lower())
            if section is not None:
                yield f"{{start_of_{section} {number}}}" if number else f"{{start_of_{section}}}"
            else:
                yield f"{{c: {name}{' ' + number if number else ''}}}"
        elif is_chord_line(line):
            pending = chords_at(line)
        else:
            yield CHORD.sub(r"\1", line)
    if pending is not None:
        yield chord_only(pending)
    if section is not None:
        yield f"{{end_of_{section}}}"


def tidy(lines: Iterator[str]) -> Iterator[str]:
    """Collapse runs of blank lines and drop blanks just inside or before a section boundary."""
    pending_blank = False
    at_start = True
    for line in lines:
        if not line.strip():
            pending_blank = not at_start
            continue
        if pending_blank and not line.startswith("{end_of_"):
            yield ""
        pending_blank = False
        at_start = line.startswith("{start_of_")
        yield line


def render(source: str, page: Page) -> Iterator[str]:
    yield f"# Converted from {source}"
    yield f"{{title: {page.title}}}"
    yield f"{{artist: {page.artist}}}"
    yield f"{{capo: {page.capo}}}"
    if page.key:
        yield f"{{key: {page.key}}}"
    yield ""
    yield from tidy(body_lines(page.content))


# ------------------------------------------------------------- Config update


def config_entry(name: str, voicing: dict[str, Any]) -> str:
    """UG frets are absolute and listed from the high E string; ChordPro wants low E first."""
    frets: list[int] = list(reversed(voicing["frets"]))  # pyright: ignore[reportAny]
    fretted = [f for f in frets if f > 0]
    base = min(fretted) if fretted and max(fretted) > 4 else 1
    rel = " ".join("x" if f < 0 else "0" if f == 0 else str(f - base + 1) for f in frets)
    return f'    {{ name: "{name}" base: {base} frets: [ {rel} ] }}'


@contextmanager
def out(path: Path | None, mode: str = "wt"):
    if not path:
        yield sys.stdout
    else:
        with open(path, mode) as fh:
            yield fh


def run(args: Namespace) -> None:
    source: str = args.source  # pyright: ignore[reportAny]
    config: Path = args.config  # pyright: ignore[reportAny]

    page = parse_page(fetch(source))
    cho = "\n".join(render(source, page)) + "\n"
    with out(args.output) as fh:  # pyright: ignore[reportAny]
        fh.write(cho)

    unknown = unknown_chords(cho, config)
    entries = [
        config_entry(name, page.applicature[name][0])
        for name in sorted(unknown)
        if page.applicature.get(name)
    ]
    if missing := sorted(name for name in unknown if not page.applicature.get(name)):
        print(f"No voicing on the page for: {', '.join(missing)}", file=sys.stderr)
    if not entries:
        if not unknown:
            print("All chords are known to ChordPro", file=sys.stderr)
    elif args.dry_run:  # pyright: ignore[reportAny]
        print("\n".join(entries), file=sys.stderr)
    else:
        update_config(config, entries)
        print(f"Added {len(entries)} chord(s) to {config}", file=sys.stderr)
