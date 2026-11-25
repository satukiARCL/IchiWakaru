"""Build IchiWakaru resource packs, ZIP archives, and release bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Sequence

try:
    from . import pack_core
except ImportError:
    import pack_core


REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_custom_spec(
    args: argparse.Namespace,
    skills: dict[str, pack_core.SkillConfig],
) -> pack_core.PackSpec:
    """Resolve CLI arguments into a single PackSpec for custom pack generation."""
    if args.skill is None:
        base: pack_core.SkillConfig | None = None
        skill_id = "custom"
        display_name = "Custom"
        default_width = None
        default_depth = None
        default_height = None
        default_y_base = -60
        default_y_max = 320
    elif args.skill == "custom":
        base = None
        skill_id = "custom"
        display_name = "Custom"
        default_width = None
        default_depth = None
        default_height = None
        default_y_base = -60
        default_y_max = 320
    else:
        if args.skill not in skills:
            valid = ", ".join([*skills.keys(), "custom"])
            raise ValueError(f"Unknown skill '{args.skill}'. Valid choices: {valid}")
        base = skills[args.skill]
        skill_id = base.skill_id
        display_name = base.display_name
        default_width = base.width
        default_depth = base.depth
        default_height = base.skill_height
        default_y_base = base.y_base
        default_y_max = base.y_max

    width = args.width if args.width is not None else default_width
    if width is None:
        raise ValueError("--width is required when using --skill custom (or omitting --skill)")
    depth = args.depth if args.depth is not None else (default_depth if default_depth is not None else width)
    skill_height = args.skill_height if args.skill_height is not None else default_height
    if skill_height is None:
        raise ValueError("--skill-height is required when using --skill custom (or omitting --skill)")
    y_base = args.y_base if args.y_base is not None else default_y_base
    y_max = args.y_max if args.y_max is not None else default_y_max

    ox = args.offset_x % width
    oz = args.offset_z % depth
    oy = args.offset_y

    if args.pack_name:
        pack_name = args.pack_name
    elif base is not None and (width != base.width or depth != base.depth or skill_height != base.skill_height):
        pack_name = pack_core.default_pack_name(
            skill_id,
            ox,
            oz,
            oy,
            suffix=f"{width}x{depth}x{skill_height}",
        )
    elif base is None:
        pack_name = pack_core.default_pack_name(
            f"custom_{width}x{depth}x{skill_height}",
            ox,
            oz,
            oy,
        )
    else:
        pack_name = pack_core.default_pack_name(skill_id, ox, oz, oy)

    if base is None or width != base.width or depth != base.depth or skill_height != base.skill_height:
        resolved_display = f"{display_name} ({width}x{depth}x{skill_height})" if base is None else f"{display_name} {width}x{depth}x{skill_height}"
    else:
        resolved_display = display_name

    return pack_core.PackSpec(
        pack_name=pack_name,
        skill_id=skill_id,
        display_name=resolved_display,
        width=width,
        depth=depth,
        skill_height=skill_height,
        y_base=y_base,
        y_max=y_max,
        offset_x=ox,
        offset_z=oz,
        offset_y=oy,
    )


def build_default_root_spec(
    config: dict[str, object],
    skills: dict[str, pack_core.SkillConfig],
) -> pack_core.PackSpec:
    """Create the PackSpec corresponding to repository root assets/."""
    root_cfg = config["default_root_pack"]
    assert isinstance(root_cfg, dict)
    skill = skills[str(root_cfg["skill"])]
    ox = int(root_cfg["offset_x"])
    oz = int(root_cfg["offset_z"])
    oy = int(root_cfg.get("offset_y", 0))
    return pack_core.PackSpec(
        pack_name=pack_core.default_pack_name(skill.skill_id, ox, oz, oy),
        skill_id=skill.skill_id,
        display_name=skill.display_name,
        width=skill.width,
        depth=skill.depth,
        skill_height=skill.skill_height,
        y_base=skill.y_base,
        y_max=skill.y_max,
        offset_x=ox,
        offset_z=oz,
        offset_y=oy,
    )


def build_all(repo_root: Path, sync_root_only: bool = False) -> dict[str, object]:
    """Synchronize root pack and build all configured packs, zips, and bundles."""
    config, skills = pack_core.load_packs_config(repo_root / "config" / "packs.json")
    _, match_blocks = pack_core.load_match_blocks(repo_root / "config" / "match_blocks.json")
    pack_png_bytes = (repo_root / "pack.png").read_bytes()

    pack_format = int(config["pack_format"])  # type: ignore[arg-type]
    author = str(config["author"])
    license_name = str(config["license"])

    root_spec = build_default_root_spec(config, skills)
    pack_core.build_pack_tree(
        dest_dir=repo_root,
        spec=root_spec,
        match_blocks=match_blocks,
        pack_png_bytes=pack_png_bytes,
        pack_format=pack_format,
        author=author,
        license_name=license_name,
        sync_root_mode=True,
    )

    if sync_root_only:
        return {"root_pack": root_spec.pack_name, "packs": [], "bundles": []}

    dist_dir = repo_root / "dist"
    packs_dir = dist_dir / "packs"
    zips_dir = dist_dir / "zips"
    bundles_dir = dist_dir / "bundles"

    for sub in (packs_dir, zips_dir, bundles_dir):
        if sub.exists():
            shutil.rmtree(sub)
        sub.mkdir(parents=True, exist_ok=True)

    built_packs: list[str] = []
    all_zip_paths: list[Path] = []
    built_bundles: list[str] = []

    for skill in skills.values():
        skill_zips: list[Path] = []
        for ox, oz in skill.offsets:
            pack_name = pack_core.default_pack_name(skill.skill_id, ox, oz)
            spec = pack_core.PackSpec(
                pack_name=pack_name,
                skill_id=skill.skill_id,
                display_name=skill.display_name,
                width=skill.width,
                depth=skill.depth,
                skill_height=skill.skill_height,
                y_base=skill.y_base,
                y_max=skill.y_max,
                offset_x=ox,
                offset_z=oz,
                offset_y=0,
            )
            pack_out = packs_dir / pack_name
            pack_core.build_pack_tree(
                dest_dir=pack_out,
                spec=spec,
                match_blocks=match_blocks,
                pack_png_bytes=pack_png_bytes,
                pack_format=pack_format,
                author=author,
                license_name=license_name,
                sync_root_mode=False,
            )

            zip_path = zips_dir / f"{pack_name}.zip"
            zip_path.write_bytes(pack_core.create_pack_zip_bytes(pack_out))
            skill_zips.append(zip_path)
            all_zip_paths.append(zip_path)
            built_packs.append(pack_name)

        skill_bundle = bundles_dir / f"IchiWakaru_{skill.skill_id}.zip"
        pack_core.write_bundle_zip(skill_bundle, skill_zips)
        built_bundles.append(skill_bundle.name)

    all_bundle = bundles_dir / "IchiWakaru_All.zip"
    pack_core.write_bundle_zip(all_bundle, all_zip_paths)
    built_bundles.append(all_bundle.name)

    return {
        "root_pack": root_spec.pack_name,
        "packs": built_packs,
        "bundles": built_bundles,
    }


def build_custom(
    repo_root: Path,
    args: argparse.Namespace,
) -> dict[str, object]:
    """Build a single custom pack according to CLI arguments without touching root assets."""
    config, skills = pack_core.load_packs_config(repo_root / "config" / "packs.json")
    _, match_blocks = pack_core.load_match_blocks(repo_root / "config" / "match_blocks.json")
    pack_png_bytes = (repo_root / "pack.png").read_bytes()

    pack_format = int(config["pack_format"])  # type: ignore[arg-type]
    author = str(config["author"])
    license_name = str(config["license"])

    spec = resolve_custom_spec(args, skills)
    out_base = Path(args.output_dir)
    if not out_base.is_absolute():
        out_base = repo_root / out_base
    pack_dir = out_base / spec.pack_name

    pack_core.build_pack_tree(
        dest_dir=pack_dir,
        spec=spec,
        match_blocks=match_blocks,
        pack_png_bytes=pack_png_bytes,
        pack_format=pack_format,
        author=author,
        license_name=license_name,
        sync_root_mode=False,
    )

    zip_path: Path | None = None
    if not args.no_zip:
        zip_path = out_base / f"{spec.pack_name}.zip"
        zip_path.write_bytes(pack_core.create_pack_zip_bytes(pack_dir))

    return {
        "pack_name": spec.pack_name,
        "pack_dir": str(pack_dir),
        "zip_path": str(zip_path) if zip_path else None,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Build IchiWakaru resource packs, ZIP archives, and release bundles."
    )
    parser.add_argument(
        "--sync-root-only",
        action="store_true",
        help="Only synchronize repository root pack.mcmeta and assets/ to the default pack.",
    )
    parser.add_argument(
        "--skill",
        type=str,
        default=None,
        help="Skill ID to build a custom pack from (tom_bowie_3x3, 11x11, eternal_vice_15x13, custom).",
    )
    parser.add_argument("--offset-x", type=int, default=0, help="Horizontal X offset (default: 0).")
    parser.add_argument("--offset-z", type=int, default=0, help="Horizontal Z offset (default: 0).")
    parser.add_argument("--offset-y", type=int, default=0, help="Vertical Y offset (default: 0).")
    parser.add_argument("--width", type=int, default=None, help="Override repeat width (X size).")
    parser.add_argument("--depth", type=int, default=None, help="Override repeat depth (Z size).")
    parser.add_argument("--skill-height", type=int, default=None, help="Override vertical repeat height (>= 2).")
    parser.add_argument("--y-base", type=int, default=None, help="Override base Y coordinate.")
    parser.add_argument("--y-max", type=int, default=None, help="Override maximum Y coordinate (default: 320).")
    parser.add_argument("--pack-name", type=str, default=None, help="Custom output pack folder/zip name.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="dist/custom",
        help="Output base directory for custom pack generation (default: dist/custom).",
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="Skip creating a ZIP archive in custom generation mode.",
    )
    return parser.parse_args(argv)


def is_custom_mode(args: argparse.Namespace) -> bool:
    """Return True when any custom pack generation flag was provided."""
    return any([
        args.skill is not None,
        args.offset_x != 0,
        args.offset_z != 0,
        args.offset_y != 0,
        args.width is not None,
        args.depth is not None,
        args.skill_height is not None,
        args.y_base is not None,
        args.y_max is not None,
        args.pack_name is not None,
        args.no_zip,
        args.output_dir != "dist/custom",
    ])


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    if args.sync_root_only and is_custom_mode(args):
        print("Error: --sync-root-only cannot be combined with custom pack options.", file=sys.stderr)
        return 2

    if is_custom_mode(args):
        try:
            result = build_custom(REPO_ROOT, args)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    result = build_all(REPO_ROOT, sync_root_only=args.sync_root_only)
    print(
        f"Root synced: {result['root_pack']} | "
        f"Packs built: {len(result['packs'])} | "
        f"Bundles built: {len(result['bundles'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
