from __future__ import annotations

import json
import shutil
from argparse import Namespace
from html import escape
from pathlib import Path

import pytest

from reprise import ug
from reprise.ug import Fingering, Page
from tests.conftest import Site

URL = "https://tabs.ultimate-guitar.com/tab/test/test-song-chords-1"

CONTENT = "\r\n".join(
    [
        "[Intro]",
        "[ch]Am[/ch]  [ch]C[/ch]",
        "",
        "",
        "[Verse 1]",
        "[ch]Am[/ch]    [ch]G[/ch]",
        "Hello there my world",
        "  [ch]C[/ch]",
        "end",
        "[Solo]",
        "e|--0--|",
    ]
)


def page_html(tab_view: dict[str, object] | None = None, tonality_name: str | None = "Am") -> str:
    view: dict[str, object] = {
        "wiki_tab": {"content": CONTENT},
        "applicature": {
            "Am": [{"frets": [0, 1, 2, 2, 0, -1]}],
            "Bm": [{"frets": [7, 7, 7, 9, 9, 7]}, {"frets": [2, 3, 4, 4, 2, -1]}],
        },
        "meta": {"capo": "2"},
        **(tab_view or {}),
    }
    store = {
        "store": {
            "page": {
                "data": {
                    "tab": {
                        "song_name": "Test Song",
                        "artist_name": "Test Artist",
                        "tonality_name": tonality_name,
                    },
                    "tab_view": view,
                }
            }
        }
    }
    return f'<div class="js-store" data-content="{escape(json.dumps(store))}"></div>'


def test_parse_page() -> None:
    page = ug.parse_page(page_html())

    assert page == Page(
        title="Test Song",
        artist="Test Artist",
        capo=2,
        key="Am",
        content=CONTENT,
        applicature={
            "Am": [Fingering(frets=[0, 1, 2, 2, 0, -1])],
            "Bm": [Fingering(frets=[7, 7, 7, 9, 9, 7]), Fingering(frets=[2, 3, 4, 4, 2, -1])],
        },
    )


def test_parse_page_treats_empty_lists_as_missing() -> None:
    page = ug.parse_page(page_html({"applicature": [], "meta": []}, tonality_name=None))

    assert (page.capo, page.key, page.applicature) == (0, "", {})


def test_parse_page_without_store_exits() -> None:
    with pytest.raises(SystemExit):
        _ = ug.parse_page("<html></html>")


def test_render() -> None:
    lines = list(ug.render(URL, ug.parse_page(page_html())))

    assert lines == [
        f"# Converted from {URL}",
        "{title: Test Song}",
        "{artist: Test Artist}",
        "{capo: 2}",
        "{key: Am}",
        "",
        "{start_of_intro}",
        "[Am] [C]",
        "{end_of_intro}",
        "{start_of_verse 1}",
        "[Am]Hello [G]there my world",
        "en[C]d",
        "{end_of_verse}",
        "{c: Solo}",
        "e|--0--|",
    ]


@pytest.mark.parametrize(
    ("frets", "entry"),
    [
        ([0, 1, 2, 2, 0, -1], '    { name: "X" base: 1 frets: [ x 0 2 2 1 0 ] }'),
        ([7, 7, 7, 9, 9, 7], '    { name: "X" base: 7 frets: [ 1 3 3 1 1 1 ] }'),
    ],
)
def test_config_entry(frets: list[int], entry: str) -> None:
    assert ug.config_entry("X", Fingering(frets=frets)) == entry


async def test_fetch_reads_url(site: Site) -> None:
    url = site.serve("/tab", page_html())

    assert await ug.fetch(url) == page_html()
    assert site.user_agents == ["Mozilla/5.0"]


async def test_fetch_reads_local_file(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    _ = path.write_text(page_html())

    assert await ug.fetch(str(path)) == page_html()


@pytest.mark.skipif(not shutil.which("chordpro"), reason="chordpro not installed")
def test_run_dry_run_leaves_config(tmp_path: Path) -> None:
    output = tmp_path / "song.cho"
    config = tmp_path / "chordpro.json"
    _ = config.write_text("{}\n")

    source = tmp_path / "page.html"
    _ = source.write_text(page_html())

    ug.run(Namespace(source=str(source), output=output, config=config, dry_run=True))

    assert "[Am]Hello [G]there my world" in output.read_text()
    assert config.read_text() == "{}\n"
