from __future__ import annotations

import shutil
from argparse import Namespace
from pathlib import Path

import aiohttp
import pytest

from reprise import brazile
from reprise.brazile import Chord, LineBuilder, Voicing
from tests.conftest import Site

FIXTURE = Path(__file__).parent / "fixtures" / "brazile.html"
URL = "https://www.brazile.net/guitar/Tabs/test-tab.html"


@pytest.fixture
def html() -> str:
    return FIXTURE.read_text()


@pytest.fixture
def rows(html: str) -> list[list[Chord]]:
    return list(brazile.parse_rows(brazile.pre_lines(html)))


def test_parse_metadata(html: str) -> None:
    meta = brazile.parse_metadata(html)

    assert meta == brazile.Metadata(
        title="Test Song",
        subtitle="(A Subtitle)",
        artist="João Performer",
        composer="Some Composer",
        album="The Album (1958)",
        transcriber="A Transcriber",
    )


def test_parse_metadata_falls_back_to_title() -> None:
    meta = brazile.parse_metadata("<title> Other Song (tablature)</title>")

    assert meta == brazile.Metadata(title="Other Song")


def test_parse_rows_reads_diagrams(rows: list[list[Chord]]) -> None:
    assert [[(c.name, c.voicing) for c in row] for row in rows] == [
        [
            ("Am", Voicing(base=1, frets=[None, 0, 2, 2, 1, 0])),
            ("C", Voicing(base=1, frets=[None, 3, 2, 0, 1, 0])),
        ],
        [
            ("A#m6", Voicing(base=5, frets=[2, None, 1, 2, 2, None])),
            ("Am", Voicing(base=1, frets=[None, 0, 2, 2, 1, 0])),
        ],
    ]


def test_parse_rows_reads_lyrics_per_column(rows: list[list[Chord]]) -> None:
    assert [[c.lyrics for c in row] for row in rows] == [
        [["Hel-"], ["lo world"]],
        [["sing a", "long"], []],
    ]


def test_render(html: str, rows: list[list[Chord]]) -> None:
    lines = list(brazile.render(URL, brazile.parse_metadata(html), rows))

    assert lines == [
        f"# Converted from {URL}",
        "# Transcribed by A Transcriber",
        "{title: Test Song}",
        "{subtitle: (A Subtitle)}",
        "{artist: João Performer}",
        "{composer: Some Composer}",
        "{album: The Album (1958)}",
        "{capo: 0}",
        "",
        "{start_of_verse}",
        "[Am]Hel[C]lo world",
        "[A#m6]sing a long [Am]",
        "{end_of_verse}",
    ]


@pytest.mark.parametrize(
    ("raw", "name"),
    [
        ("A# m6", "A#m6"),
        ("DM7/F#", "Dmaj7/F#"),
        ("A7 sus 4", "A7sus4"),
        ("Dm7", "Dm7"),
    ],
)
def test_normalize_name(raw: str, name: str) -> None:
    assert brazile.normalize_name(raw) == name


def test_line_builder_carries_hyphenated_word_to_next_line() -> None:
    builder = LineBuilder()
    builder.add("one", "C")
    builder.add("two thr-", "G")

    assert builder.flush() == "[C]one [G]two"
    builder.add("ee", "Am")
    assert builder.flush() == "thr[Am]ee"


def test_config_entry() -> None:
    voicing = Voicing(base=5, frets=[2, None, 1, 2, 2, None])

    assert voicing.config_entry("A#m6") == '    { name: "A#m6" base: 5 frets: [ 2 x 1 2 2 x ] }'


def test_voicings_keeps_first_voicing(rows: list[list[Chord]]) -> None:
    found = brazile.voicings(rows, {"Am", "A#m6"})

    assert found == {
        "Am": Voicing(base=1, frets=[None, 0, 2, 2, 1, 0]),
        "A#m6": Voicing(base=5, frets=[2, None, 1, 2, 2, None]),
    }


def test_update_config_appends_to_chords(tmp_path: Path) -> None:
    config = tmp_path / "chordpro.json"
    _ = config.write_text('settings : {}\nchords : [\n    { name: "X" }\n]\n')

    brazile.update_config(config, ['    { name: "Y" }'])

    assert config.read_text() == (
        'settings : {}\nchords : [\n    { name: "X" }\n    { name: "Y" }\n]\n'
    )


def test_update_config_creates_chords(tmp_path: Path) -> None:
    config = tmp_path / "chordpro.json"
    _ = config.write_text("settings : {}\n")

    brazile.update_config(config, ['    { name: "Y" }'])

    assert config.read_text() == 'settings : {}\n\nchords : [\n    { name: "Y" }\n]\n'


async def test_fetch_reads_local_file() -> None:
    assert await brazile.fetch(str(FIXTURE)) == FIXTURE.read_text()


async def test_fetch_sends_browser_user_agent(site: Site) -> None:
    url = site.serve("/tab.html", "page")

    assert await brazile.fetch(url) == "page"
    assert site.user_agents == ["Mozilla/5.0"]


async def test_fetch_decodes_latin1(site: Site) -> None:
    url = site.serve("/tab.html", "João".encode("latin-1"))

    assert await brazile.fetch(url) == "João"


async def test_fetch_raises_on_http_error(site: Site) -> None:
    url = site.serve("/tab.html", "", status=404)

    with pytest.raises(aiohttp.ClientResponseError):
        _ = await brazile.fetch(url)


@pytest.mark.skipif(not shutil.which("chordpro"), reason="chordpro not installed")
def test_run_adds_unknown_chords_from_page(tmp_path: Path) -> None:
    output = tmp_path / "song.cho"
    config = tmp_path / "chordpro.json"
    _ = config.write_text("{}\n")

    brazile.run(Namespace(source=str(FIXTURE), output=output, config=config, dry_run=False))

    assert "[Am]Hel[C]lo world" in output.read_text()
    added = [line for line in config.read_text().splitlines() if "name:" in line]
    assert all(any(f'"{n}"' in line for n in ("Am", "C", "A#m6")) for line in added)
