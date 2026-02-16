from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tame",
        description="TAME — Terminal Agent Management Environment",
    )
    parser.add_argument("--config", help="Path to config file")
    parser.add_argument("--theme", help="Override theme (dark, light, dracula, etc.)")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    from tame.app import TAMEApp

    app = TAMEApp(
        config_path=args.config, theme_override=args.theme, verbose=args.verbose
    )
    app.run()


if __name__ == "__main__":
    main()
