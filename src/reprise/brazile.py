# pyright: reportUnusedCallResult = false
"""Convert a tablature page from brazile.net into a ChordPro file.

Pages such as https://www.brazile.net/guitar/Tabs/chega-tab.html contain a
<pre> block with rows of ASCII chord diagrams, each followed by the lyric
fragments sung over those chords (in columns aligned with the diagrams).

The script writes the song as a .cho file and adds a definition to the
`chords` array of the ChordPro configuration for every chord that ChordPro
does not know yet, using the voicing from the page.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen

CONFIG = Path("chordpro.json")

GRID = re.compile(r"\+-\+-\+-\+-\+-\+")
STRINGS = 6
# Width of a diagram including the base fret column, e.g. "+-+-+-+-+-+ 12".
DIAGRAM_WIDTH = 14


def create_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Convert a brazile.net tablature page to ChordPro")
    parser.add_argument("source", help="URL or local path of the tablature page")
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
        # The site refuses the default Python-urllib user agent.
        request = Request(source, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request) as response:  # pyright: ignore[reportAny]
            data: bytes = response.read()  # pyright: ignore[reportAny]
    else:
        data = Path(source).read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def strip_tags(html: str) -> str:
    return unescape(re.sub(r"<[^>]*>", "", html))


def html_lines(html: str) -> list[str]:
    """Split an HTML fragment on <br>/<p> and return the non-empty text lines."""
    parts = re.split(r"<br\s*/?>|</?p>", html, flags=re.IGNORECASE)
    lines = (" ".join(strip_tags(part).split()) for part in parts)
    return [line for line in lines if line]


@dataclass
class Metadata:
    title: str
    subtitle: str | None = None
    artist: str | None = None
    composer: str | None = None
    album: str | None = None
    transcriber: str | None = None


def parse_metadata(html: str) -> Metadata:
    h2 = re.search(r"<h2>(.*?)</h2>", html, flags=re.IGNORECASE | re.DOTALL)
    title_lines = html_lines(h2[1]) if h2 else []
    if not title_lines:
        title = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        title_lines = [strip_tags(title[1]).replace("(tablature)", "").strip()] if title else ["?"]
    meta = Metadata(title=title_lines[0])
    if len(title_lines) > 1:
        meta.subtitle = title_lines[1]

    # The credits live in the first <center> block, after the heading.
    center = re.search(r"</h2>(.*?)</center>", html, flags=re.IGNORECASE | re.DOTALL)
    for line in html_lines(center[1]) if center else []:
        if m := re.match(r"Written by (.*)", line):
            meta.composer = m[1]
        elif m := re.match(r"Performed by (.*)", line):
            meta.artist = m[1]
        elif m := re.match(r"Transcribed by (.*)", line):
            meta.transcriber = m[1]
    if center and (album := re.search(r"<i>(.*?)</i>", center[1], flags=re.DOTALL)):
        meta.album = " ".join(strip_tags(album[1]).split())
    return meta


def pre_lines(html: str) -> list[str]:
    blocks = re.findall(r"<pre>(.*?)</pre>", html, flags=re.IGNORECASE | re.DOTALL)
    text = unescape(re.sub(r"<[^>]*>", "", "\n".join(blocks)))
    return text.expandtabs().splitlines()


# ------------------------------------------------------------- Diagram parsing


@dataclass
class Voicing:
    base: int
    # Fret per string (low E first), relative to base: None is muted, 0 is open.
    frets: list[int | None]

    def config_entry(self, name: str) -> str:
        frets = " ".join("x" if f is None else str(f) for f in self.frets)
        return f'    {{ name: "{name}" base: {self.base} frets: [ {frets} ] }}'


@dataclass
class Chord:
    name: str
    voicing: Voicing
    lyrics: list[str] = field(default_factory=list)


def normalize_name(raw: str) -> str:
    """Turn e.g. "A# m6", "DM7/F#" or "A7 sus 4" into "A#m6", "Dmaj7/F#", "A7sus4"."""
    name = "".join(raw.split())
    return re.sub(r"^([A-G][#b]?)M(?=\d)", r"\1maj", name)


def column(line: str, start: int, end: int | None) -> str:
    return line[start:end].strip() if end is not None else line[start:].strip()


def split_names(line: str, starts: list[int]) -> list[str]:
    """Chord names are separated by at least two spaces; fall back to slicing."""
    names = re.split(r"\s{2,}", line.strip())
    if len(names) == len(starts):
        return names
    ends: list[int | None] = [*starts[1:], None]
    return [column(line, s, e) for s, e in zip(starts, ends)]


def parse_voicing(rows: list[str], bottom: str, start: int) -> Voicing:
    first = rows[0][start + 11 : start + DIAGRAM_WIDTH + 2]
    base = int(m[0]) if (m := re.search(r"\d+", first)) else 1
    frets: list[int | None] = []
    for string in range(STRINGS):
        col = start + 2 * string
        fretted = [i + 1 for i, row in enumerate(rows) if row[col : col + 1] == "o"]
        marker = bottom[col : col + 1]
        if fretted:
            # Several dots on one string can't be played, the lowest one sounds.
            frets.append(max(fretted))
        elif marker == "O":
            frets.append(0)
        else:
            frets.append(None)
    return Voicing(base=base, frets=frets)


def parse_rows(lines: list[str]) -> Iterator[list[Chord]]:
    """Yield the chords of each row of diagrams, with the lyrics below them."""
    # A block of diagrams starts with a grid line below the line with chord names.
    blocks = [
        i
        for i, line in enumerate(lines)
        if i > 0 and GRID.search(line) and "|" not in lines[i - 1]
    ]
    for n, top in enumerate(blocks):
        starts = [m.start() for m in GRID.finditer(lines[top])]
        # String rows alternate with grid lines; the line after the last grid line
        # marks the muted (x) and open (O) strings.
        rows: list[str] = []
        i = top + 1
        while i + 1 < len(lines) and "|" in lines[i] and GRID.search(lines[i + 1]):
            rows.append(lines[i])
            i += 2
        bottom = lines[i] if i < len(lines) else ""
        names = split_names(lines[top - 1], starts)

        lyrics_end = blocks[n + 1] - 1 if n + 1 < len(blocks) else len(lines)
        lyric_lines = [line for line in lines[i + 1 : lyrics_end] if line.strip()]

        ends: list[int | None] = [*starts[1:], None]
        yield [
            Chord(
                name=normalize_name(name),
                voicing=parse_voicing(rows, bottom, start),
                lyrics=[text for line in lyric_lines if (text := column(line, start, end))],
            )
            for name, start, end in zip(names, starts, ends)
        ]


# ------------------------------------------------------------ ChordPro output


@dataclass
class LineBuilder:
    """Joins lyric fragments, gluing words that were hyphenated across columns."""

    text: str = ""
    # The previous fragment ended in a hyphen, so the next one continues the word.
    open_word: bool = False

    def add(self, fragment: str, chord: str | None = None) -> None:
        continues = self.open_word or fragment.startswith("-")
        fragment = fragment.lstrip("-")
        if self.text and not continues and (fragment or chord):
            self.text += " "
        if continues:
            self.text = self.text.rstrip("-")
        if chord:
            self.text += f"[{chord}]"
        self.text += fragment
        if fragment:
            self.open_word = fragment.endswith("-")

    def flush(self) -> str:
        """Return the finished line, leaving a word that continues on the next line."""
        head, carry = self.text, ""
        if self.open_word:
            head, _, carry = self.text.rpartition(" ")
            carry = carry.rstrip("-")
        self.text = carry
        return head


def song_lines(rows: Iterable[list[Chord]]) -> Iterator[str]:
    """One line per row of diagrams."""
    builder = LineBuilder()
    for row in rows:
        for chord in row:
            builder.add(chord.lyrics[0] if chord.lyrics else "", chord.name)
            for fragment in chord.lyrics[1:]:
                builder.add(fragment)
        if line := builder.flush():
            yield line
    if builder.text:
        yield builder.text


def render(source: str, meta: Metadata, rows: list[list[Chord]]) -> Iterator[str]:
    yield f"# Converted from {source}"
    if meta.transcriber:
        yield f"# Transcribed by {meta.transcriber}"
    yield f"{{title: {meta.title}}}"
    if meta.subtitle:
        yield f"{{subtitle: {meta.subtitle}}}"
    if meta.artist:
        yield f"{{artist: {meta.artist}}}"
    if meta.composer:
        yield f"{{composer: {meta.composer}}}"
    if meta.album:
        yield f"{{album: {meta.album}}}"
    yield "{capo: 0}"
    yield ""
    yield "{start_of_verse}"
    yield from song_lines(rows)
    yield "{end_of_verse}"


# ------------------------------------------------------------- Config update


def unknown_chords(cho: str, config: Path) -> set[str]:
    """Ask ChordPro which chords of the song it has no diagram for."""
    if not shutil.which("chordpro"):
        sys.exit("chordpro not found on PATH, cannot determine the unknown chords")
    with tempfile.TemporaryDirectory() as tmp:
        song = Path(tmp) / "song.cho"
        song.write_text(cho)
        result = subprocess.run(
            ["chordpro", str(song), f"--config={config}", "--output", str(Path(tmp) / "song.pdf")],
            capture_output=True,
            text=True,
        )
    unknown: set[str] = set()
    for line in result.stderr.splitlines():
        if m := re.search(r'Unknown chord: "?(.*?)"?$', line):
            unknown.add(m[1])
        elif m := re.search(r"No chord diagram defined for (.*) \(skipped\)", line):
            unknown.update(re.findall(r'"([^"]+)"', m[1]))
    return unknown


def voicings(rows: Iterable[list[Chord]], names: set[str]) -> dict[str, Voicing]:
    """The first voicing on the page of each of the given chords."""
    found: dict[str, Voicing] = {}
    for chord in (chord for row in rows for chord in row if chord.name in names):
        if chord.name not in found:
            found[chord.name] = chord.voicing
        elif found[chord.name] != chord.voicing:
            print(f"Ignoring alternative voicing for {chord.name}", file=sys.stderr)
    return found


def update_config(config: Path, entries: list[str]) -> None:
    text = config.read_text()
    m = re.search(r"^chords\s*:\s*\[.*?^\]", text, flags=re.MULTILINE | re.DOTALL)
    if m is None:
        text = text.rstrip("\n") + "\n\nchords : [\n" + "\n".join(entries) + "\n]\n"
    else:
        end = m.end() - 1
        text = text[:end] + "\n".join(entries) + "\n" + text[end:]
    config.write_text(text)


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

    html = fetch(source)
    rows = list(parse_rows(pre_lines(html)))
    if not rows:
        sys.exit(f"No chord diagrams found in {source}")
    cho = "\n".join(render(source, parse_metadata(html), rows)) + "\n"
    with out(args.output) as fh:  # pyright: ignore[reportAny]
        fh.write(cho)

    unknown = unknown_chords(cho, config)
    entries = [v.config_entry(name) for name, v in voicings(rows, unknown).items()]
    if not entries:
        print("All chords are known to ChordPro", file=sys.stderr)
    elif args.dry_run:  # pyright: ignore[reportAny]
        print("\n".join(entries), file=sys.stderr)
    else:
        update_config(config, entries)
        print(f"Added {len(entries)} chord(s) to {config}", file=sys.stderr)
