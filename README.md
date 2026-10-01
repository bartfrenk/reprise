# reprise

Tools for building ChordPro songbooks from Org files.

```sh
make install                                  # installs the `reprise` command with uv
reprise tangle songs/pop.org                  # tangle chordpro blocks, files named after headings
reprise preprocess build/pop/song.cho -o …    # normalize a tangled .cho file
reprise brazile <url> -o song.cho             # convert a brazile.net tab page
reprise ug <url> -o song.cho                  # convert an Ultimate Guitar chords page
```

`brazile` and `ug` add unknown chords to `chordpro.json` in the current directory (override with `--config`).
