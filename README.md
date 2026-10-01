# songbook

Tools for building ChordPro songbooks from Org files.

```sh
make install                                  # installs the `songbook` command with uv
songbook tangle songs/pop.org                 # tangle chordpro blocks, files named after headings
songbook preprocess build/pop/song.cho -o …   # normalize a tangled .cho file
songbook brazile <url> -o song.cho            # convert a brazile.net tab page
songbook ug <url> -o song.cho                 # convert an Ultimate Guitar chords page
```

`brazile` and `ug` add unknown chords to `chordpro.json` in the current directory (override with `--config`).
