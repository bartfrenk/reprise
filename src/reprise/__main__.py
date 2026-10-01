from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import Protocol

from reprise import brazile, preprocess, tangle, ug


class Command(Protocol):
    """A subcommand module: builds its own parser and runs with the parsed arguments."""

    def create_parser(self) -> ArgumentParser: ...

    def run(self, args: Namespace) -> None: ...


COMMANDS: dict[str, Command] = {
    "tangle": tangle,
    "preprocess": preprocess,
    "brazile": brazile,
    "ug": ug,
}


def main() -> None:
    parser = ArgumentParser(prog="reprise", description="Tools for ChordPro songbooks")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, module in COMMANDS.items():
        sub = module.create_parser()
        _ = subparsers.add_parser(
            name, parents=[sub], add_help=False, help=sub.description, description=sub.description
        )
    args = parser.parse_args()
    command: str = args.command  # pyright: ignore[reportAny]
    COMMANDS[command].run(args)


if __name__ == "__main__":
    main()
