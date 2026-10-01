from argparse import ArgumentParser

from reprise import brazile, preprocess, tangle, ug

COMMANDS = {
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
        subparsers.add_parser(
            name, parents=[sub], add_help=False, help=sub.description, description=sub.description
        )
    args = parser.parse_args()
    COMMANDS[args.command].run(args)  # pyright: ignore[reportAny]


if __name__ == "__main__":
    main()
