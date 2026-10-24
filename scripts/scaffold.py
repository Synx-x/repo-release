#!/usr/bin/env python3
"""Copy the plugin's templates into a repo, without overwriting anything.

    python3 scaffold.py /path/to/repo
    python3 scaffold.py . --license Apache-2.0 --name mytool --owner Synx-x

Copies `templates/repo/` as a tree, renames `gitignore` to `.gitignore`, and
substitutes the placeholders it can. Files that already exist are skipped and
reported, because the usual case is adding the missing pieces to a repo that
already has a README worth keeping.

Never overwrites. `--force` is deliberately absent: a scaffold that clobbers a
hand-written README is a scaffold that gets run once and never trusted again.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = PLUGIN_ROOT / "templates"

RENAMES = {"gitignore": ".gitignore", "ci.yml": "ci.yml"}

SUBSTITUTIONS = {
    "<name>": "name",
    "<YEAR>": "year",
    "<NAME>": "owner",
    "<repo-url>": "repo_url",
}


def destination_for(relative: Path) -> Path:
    """ci.yml ships at the repo root in the template and belongs in .github."""
    if relative.as_posix() == "ci.yml":
        return Path(".github") / "workflows" / "ci.yml"
    name = RENAMES.get(relative.name, relative.name)
    return relative.parent / name


def substitute(text: str, values: dict[str, str]) -> str:
    for token, key in SUBSTITUTIONS.items():
        if key in values and values[key]:
            text = text.replace(token, values[key])
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scaffold", description=__doc__)
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--name", default="")
    parser.add_argument("--owner", default="")
    parser.add_argument("--repo-url", default="")
    parser.add_argument(
        "--license",
        default="MIT",
        help="MIT or Apache-2.0. Ignored when a LICENSE already exists.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    target = Path(args.repo).expanduser().resolve()
    if not target.is_dir():
        print(f"not a directory: {target}", file=sys.stderr)
        return 2

    values = {"name": args.name, "owner": args.owner, "repo_url": args.repo_url}

    written, skipped = [], []
    for source in sorted((TEMPLATES / "repo").rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(TEMPLATES / "repo")
        dest = target / destination_for(relative)
        if dest.exists():
            skipped.append(dest.relative_to(target).as_posix())
            continue
        written.append(dest.relative_to(target).as_posix())
        if args.dry_run:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_text(encoding="utf-8")
        dest.write_text(substitute(text, values), encoding="utf-8")

    license_source = TEMPLATES / "license" / f"{args.license}.txt"
    license_dest = target / "LICENSE"
    if license_dest.exists():
        skipped.append("LICENSE")
    elif not license_source.exists():
        print(f"no license template named {args.license}", file=sys.stderr)
        return 2
    else:
        written.append("LICENSE")
        if not args.dry_run:
            text = license_source.read_text(encoding="utf-8")
            license_dest.write_text(substitute(text, values), encoding="utf-8")

    verb = "would write" if args.dry_run else "wrote"
    for path in written:
        print(f"{verb} {path}")
    for path in skipped:
        print(f"kept   {path} (already exists)")
    print(f"\n{len(written)} {verb}, {len(skipped)} kept")

    if written:
        print("\nNext: fill the <> placeholders, then run")
        print(f"  python3 {PLUGIN_ROOT / 'scripts' / 'validate.py'} {target} --profile public")
    return 0


if __name__ == "__main__":
    sys.exit(main())
