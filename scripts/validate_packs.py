"""Validate IchiWakaru repository files, generated packs, ZIPs, and bundles."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys
import zipfile
from typing import Sequence

try:
    from . import pack_core
except ImportError:
    import pack_core


REPO_ROOT = Path(__file__).resolve().parent.parent
UTF8_BOM = b"\xef\xbb\xbf"

FORBIDDEN_NON_SOLID_OR_TECH = {
    "air",
    "cave_air",
    "void_air",
    "water",
    "lava",
    "bubble_column",
    "moving_piston",
    "piston_head",
    "barrier",
    "light",
    "structure_void",
    "structure_block",
    "command_block",
    "chain_command_block",
    "repeating_command_block",
    "jigsaw",
    "end_portal",
    "end_gateway",
    "nether_portal",
    "fire",
    "soul_fire",
}

FORBIDDEN_POST_1_18_EXACT = {
    "frogspawn",
    "mud",
    "packed_mud",
    "mud_bricks",
    "mud_brick_slab",
    "mud_brick_stairs",
    "mud_brick_wall",
    "mangrove_log",
    "stripped_mangrove_log",
    "mangrove_wood",
    "stripped_mangrove_wood",
    "mangrove_roots",
    "muddy_mangrove_roots",
    "mangrove_leaves",
    "mangrove_propagule",
    "mangrove_planks",
    "mangrove_slab",
    "mangrove_stairs",
    "mangrove_fence",
    "mangrove_fence_gate",
    "mangrove_door",
    "mangrove_trapdoor",
    "mangrove_pressure_plate",
    "mangrove_button",
    "mangrove_sign",
    "mangrove_wall_sign",
    "ochre_froglight",
    "pearlescent_froglight",
    "verdant_froglight",
    "reinforced_deepslate",
    "sculk",
    "sculk_catalyst",
    "sculk_shrieker",
    "sculk_vein",
    "cherry_log",
    "cherry_planks",
    "bamboo_planks",
    "calibrated_sculk_sensor",
}

TEXT_EXTENSIONS = {".json", ".mcmeta", ".properties", ".py", ".md", ".txt"}
TEXT_FILENAMES = {".gitignore"}


def collect_repo_text_files(repo_root: Path) -> list[Path]:
    """Collect all repository-managed text files (excluding .git and dist)."""
    files: list[Path] = []
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(repo_root).parts
        if rel_parts[0] in {".git", "dist", "__pycache__", ".pytest_cache", ".venv", "venv"}:
            continue
        if "__pycache__" in rel_parts:
            continue
        if path.suffix.lower() in TEXT_EXTENSIONS or path.name in TEXT_FILENAMES:
            files.append(path)
    return files


def validate_text_encoding(path: Path, errors: list[str]) -> str | None:
    """Verify no UTF-8 BOM, valid UTF-8 decoding, and trailing newline."""
    raw = path.read_bytes()
    if raw.startswith(UTF8_BOM):
        errors.append(f"{path}: UTF-8 BOM detected")
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        errors.append(f"{path}: invalid UTF-8 ({exc})")
        return None
    if text and not text.endswith("\n"):
        errors.append(f"{path}: missing trailing newline")
    if "\r\n" in text:
        errors.append(f"{path}: CRLF line ending detected (expected LF)")
    return text


def validate_match_blocks_config(repo_root: Path, errors: list[str]) -> list[str]:
    """Validate config/match_blocks.json syntax, uniqueness, sorting, and block exclusions."""
    mb_path = repo_root / "config" / "match_blocks.json"
    text = validate_text_encoding(mb_path, errors)
    if text is None:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"{mb_path}: invalid JSON ({exc})")
        return []

    if data.get("minecraft_version") != "1.18.2" or data.get("pack_format") != 8:
        errors.append(f"{mb_path}: unexpected minecraft_version/pack_format metadata")

    blocks = data.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        errors.append(f"{mb_path}: 'blocks' must be a non-empty list")
        return []

    seen: set[str] = set()
    duplicates: list[str] = []
    for b in blocks:
        if not isinstance(b, str) or not b or " " in b or b.startswith("minecraft:"):
            errors.append(f"{mb_path}: invalid block identifier {b!r}")
            continue
        if b in seen:
            duplicates.append(b)
        seen.add(b)

    if duplicates:
        errors.append(f"{mb_path}: duplicate block IDs: {duplicates[:10]}")
    if blocks != sorted(blocks):
        errors.append(f"{mb_path}: 'blocks' list is not sorted ascending")

    bad_non_solid = sorted(seen & FORBIDDEN_NON_SOLID_OR_TECH)
    if bad_non_solid:
        errors.append(f"{mb_path}: contains excluded non-solid/tech blocks: {bad_non_solid}")

    sample_19 = set(data.get("post_1_18_forbidden_sample", [])) | FORBIDDEN_POST_1_18_EXACT
    bad_19 = sorted(seen & sample_19)
    if bad_19:
        errors.append(f"{mb_path}: contains post-1.18.2 blocks: {bad_19}")

    return blocks


def parse_properties_file(text: str) -> dict[str, str]:
    """Parse OptiFine CTM .properties text with backslash line continuation."""
    lines = text.splitlines()
    props: dict[str, str] = {}
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        idx += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Malformed property line: {line!r}")
        key, val = line.split("=", 1)
        chunks: list[str] = []
        current = val
        while current.endswith("\\"):
            chunks.append(current[:-1])
            if idx >= len(lines):
                raise ValueError(f"Dangling line continuation for key {key}")
            current = lines[idx]
            idx += 1
        chunks.append(current)
        props[key.strip()] = "\n".join(chunks)
    return props


def validate_png_tile(path: Path, layer: str, shape: str, tile_idx: int, errors: list[str]) -> None:
    """Validate that a CTM PNG is 16x16 RGBA and matches exact expected pixels."""
    if not path.is_file():
        errors.append(f"Missing PNG tile: {path}")
        return
    try:
        w, h, bd, ct, grid = pack_core.decode_png(path.read_bytes())
    except Exception as exc:
        errors.append(f"{path}: invalid PNG ({exc})")
        return

    if (w, h, bd, ct) != (16, 16, 8, 6):
        errors.append(f"{path}: expected 16x16 8-bit RGBA (ct=6), got {(w, h, bd, ct)}")
        return

    active_idx, rgba = pack_core.LAYER_SPECS[layer]
    expected_grid = pack_core.build_rgba_grid(shape, rgba if tile_idx == active_idx else None)
    if grid != expected_grid:
        errors.append(f"{path}: pixel RGBA values do not match expected pattern for {layer}/{shape}/{tile_idx}")


def validate_pack_png(path: Path, errors: list[str]) -> None:
    """Validate pack.png exists and is a valid 16x16 PNG."""
    if not path.is_file():
        errors.append(f"Missing pack.png: {path}")
        return
    try:
        w, h, _, _, _ = pack_core.decode_png(path.read_bytes())
        if (w, h) != (16, 16):
            errors.append(f"{path}: expected 16x16 pack icon, got {w}x{h}")
    except Exception as exc:
        errors.append(f"{path}: invalid PNG ({exc})")


def validate_pack_mcmeta(
    path: Path,
    expected_pack_format: int,
    errors: list[str],
) -> None:
    """Validate pack.mcmeta UTF-8 encoding and JSON schema."""
    if not path.is_file():
        errors.append(f"Missing pack.mcmeta: {path}")
        return
    text = validate_text_encoding(path, errors)
    if text is None:
        return
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON ({exc})")
        return

    pack_obj = data.get("pack")
    if not isinstance(pack_obj, dict):
        errors.append(f"{path}: missing 'pack' object")
        return
    if pack_obj.get("pack_format") != expected_pack_format:
        errors.append(f"{path}: pack_format={pack_obj.get('pack_format')} != {expected_pack_format}")
    desc = pack_obj.get("description")
    if not isinstance(desc, str) or not desc.strip():
        errors.append(f"{path}: empty or non-string description")


def validate_pack_directory(
    pack_dir: Path,
    spec: pack_core.PackSpec,
    expected_blocks: Sequence[str],
    expected_pack_format: int,
    errors: list[str],
) -> None:
    """Validate all CTM .properties, PNGs, heights invariants, and pack metadata."""
    validate_pack_mcmeta(pack_dir / "pack.mcmeta", expected_pack_format, errors)
    validate_pack_png(pack_dir / "pack.png", errors)

    ctm_dir = pack_dir / "assets" / "minecraft" / "optifine" / "ctm"
    if not ctm_dir.is_dir():
        errors.append(f"Missing CTM directory: {ctm_dir}")
        return

    expected_heights = pack_core.compute_layer_heights(
        y_base=spec.y_base,
        y_max=spec.y_max,
        skill_height=spec.skill_height,
        offset_y=spec.offset_y,
    )
    expected_tiles = pack_core.build_tiles_matrix(
        width=spec.width,
        depth=spec.depth,
        offset_x=spec.offset_x,
        offset_z=spec.offset_z,
    )
    expected_blocks_str = " ".join(expected_blocks)

    expected_rel_files: set[str] = set()
    active_rules = [r for r in pack_core.RULE_DEFINITIONS if expected_heights[r[4]]]
    active_shapes = list(dict.fromkeys(r[0] for r in active_rules))

    for layer in pack_core.LAYER_SPECS:
        for shape in active_shapes:
            for tile_idx in range(4):
                rel = f"{layer}/{shape}/{tile_idx}.png"
                expected_rel_files.add(rel)
                validate_png_tile(ctm_dir / rel, layer, shape, tile_idx, errors)

        parsed_heights_by_key: dict[str, list[int]] = {}
        for shape, prop_name, expected_faces, expected_symmetry, height_key in active_rules:
            rel = f"{layer}/{shape}/{prop_name}"
            expected_rel_files.add(rel)
            prop_path = ctm_dir / rel
            if not prop_path.is_file():
                errors.append(f"Missing properties file: {prop_path}")
                continue

            text = validate_text_encoding(prop_path, errors)
            if text is None:
                continue

            try:
                props = parse_properties_file(text)
            except Exception as exc:
                errors.append(f"{prop_path}: parse error ({exc})")
                continue

            if props.get("matchBlocks") != expected_blocks_str:
                errors.append(f"{prop_path}: matchBlocks does not match config/match_blocks.json")
            if props.get("connect") != "material":
                errors.append(f"{prop_path}: expected connect=material, got {props.get('connect')!r}")
            if props.get("method") != "overlay_repeat":
                errors.append(f"{prop_path}: expected method=overlay_repeat, got {props.get('method')!r}")
            if props.get("faces") != expected_faces:
                errors.append(f"{prop_path}: expected faces={expected_faces}, got {props.get('faces')!r}")
            if props.get("symmetry") != expected_symmetry:
                errors.append(f"{prop_path}: expected symmetry={expected_symmetry}, got {props.get('symmetry')!r}")

            if props.get("width") != str(spec.width) or props.get("height") != str(spec.depth):
                errors.append(
                    f"{prop_path}: expected width={spec.width}, height={spec.depth}, "
                    f"got width={props.get('width')}, height={props.get('height')}"
                )

            # Validate tiles matrix structure and token counts
            raw_tiles = props.get("tiles", "")
            tile_rows = [row.strip().split() for row in raw_tiles.splitlines() if row.strip()]
            flat_tiles = [int(tok) for row in tile_rows for tok in row]
            if len(tile_rows) != spec.depth or any(len(r) != spec.width for r in tile_rows):
                errors.append(f"{prop_path}: tiles dimensions do not match {spec.width}x{spec.depth}")
            elif len(flat_tiles) != spec.width * spec.depth:
                errors.append(f"{prop_path}: tile count {len(flat_tiles)} != {spec.width * spec.depth}")
            elif [[int(t) for t in row] for row in tile_rows] != expected_tiles:
                errors.append(f"{prop_path}: tiles matrix mismatch for offset ({spec.offset_x}, {spec.offset_z})")

            # Validate heights syntax, ordering, spacing, and bounds
            try:
                parsed_h = pack_core.parse_heights(props.get("heights", ""))
            except Exception as exc:
                errors.append(f"{prop_path}: invalid heights format ({exc})")
                continue

            if parsed_h != sorted(parsed_h) or len(parsed_h) != len(set(parsed_h)):
                errors.append(f"{prop_path}: heights must be strictly ascending without duplicates")
            if parsed_h != expected_heights[height_key]:
                errors.append(f"{prop_path}: heights do not match mathematical progression for {height_key}")
            if height_key in ("bottom", "top") and len(parsed_h) >= 2:
                diffs = {parsed_h[i + 1] - parsed_h[i] for i in range(len(parsed_h) - 1)}
                if diffs != {spec.skill_height}:
                    errors.append(f"{prop_path}: {height_key} height step {diffs} != {spec.skill_height}")

            parsed_heights_by_key[height_key] = parsed_h

        # Partition invariant: bottom, middle, top must cleanly partition [effective_y_base, y_max]
        if set(parsed_heights_by_key) == {k for k, v in expected_heights.items() if v}:
            combined = [y for seq in parsed_heights_by_key.values() for y in seq]
            expected_range = list(range(spec.effective_y_base, spec.y_max + 1))
            if len(combined) != len(set(combined)):
                errors.append(f"{ctm_dir / layer}: overlapping Y coordinates across bottom/middle/top")
            elif sorted(combined) != expected_range:
                errors.append(
                    f"{ctm_dir / layer}: union of bottom/middle/top does not cover "
                    f"[{spec.effective_y_base}, {spec.y_max}] without gaps"
                )

    actual_rel_files = {
        p.relative_to(ctm_dir).as_posix() for p in ctm_dir.rglob("*") if p.is_file()
    }
    extra = sorted(actual_rel_files - expected_rel_files)
    missing = sorted(expected_rel_files - actual_rel_files)
    if extra:
        errors.append(f"{ctm_dir}: unexpected extra files: {extra}")
    if missing:
        errors.append(f"{ctm_dir}: missing expected files: {missing}")


def collect_pack_file_bytes(pack_dir: Path) -> dict[str, bytes]:
    """Collect relative POSIX file path -> bytes for a pack's pack.mcmeta, pack.png, and assets/."""
    files: dict[str, bytes] = {}
    for fixed in ("pack.mcmeta", "pack.png"):
        fp = pack_dir / fixed
        if fp.is_file():
            files[fixed] = fp.read_bytes()
    assets_dir = pack_dir / "assets"
    if assets_dir.is_dir():
        for p in sorted(assets_dir.rglob("*")):
            if p.is_file():
                files[p.relative_to(pack_dir).as_posix()] = p.read_bytes()
    return files


def validate_zip_archive(
    zip_path: Path,
    expected_files: dict[str, bytes],
    errors: list[str],
) -> None:
    """Verify pack ZIP has pack.mcmeta/pack.png/assets/ at root and matches directory bytes."""
    if not zip_path.is_file():
        errors.append(f"Missing ZIP archive: {zip_path}")
        return
    with zipfile.ZipFile(zip_path, mode="r") as zf:
        names = zf.namelist()
        if "pack.mcmeta" not in names or "pack.png" not in names:
            errors.append(f"{zip_path}: missing pack.mcmeta or pack.png at ZIP root")
            return
        if not any(n.startswith("assets/minecraft/optifine/ctm/") for n in names):
            errors.append(f"{zip_path}: missing assets/minecraft/optifine/ctm/ at ZIP root")
            return
        actual_files = {n: zf.read(n) for n in names if not n.endswith("/")}
        if actual_files != expected_files:
            errors.append(f"{zip_path}: ZIP contents diverge from pack directory")


def validate_bundle_archive(
    bundle_path: Path,
    expected_zips: dict[str, bytes],
    errors: list[str],
) -> None:
    """Verify bundle ZIP contains expected pack ZIPs at its root and each inner ZIP is valid."""
    if not bundle_path.is_file():
        errors.append(f"Missing bundle archive: {bundle_path}")
        return
    with zipfile.ZipFile(bundle_path, mode="r") as bz:
        names = [n for n in bz.namelist() if not n.endswith("/")]
        if set(names) != set(expected_zips):
            errors.append(
                f"{bundle_path}: expected entries {sorted(expected_zips)}, got {sorted(names)}"
            )
            return
        for name in names:
            if "/" in name:
                errors.append(f"{bundle_path}: nested directory entry {name!r} (must be flat at root)")
                continue
            inner_bytes = bz.read(name)
            if inner_bytes != expected_zips[name]:
                errors.append(f"{bundle_path}: inner ZIP {name} diverges from dist/zips/{name}")
                continue
            with zipfile.ZipFile(io.BytesIO(inner_bytes), mode="r") as iz:
                inames = set(iz.namelist())
                if "pack.mcmeta" not in inames or "pack.png" not in inames:
                    errors.append(f"{bundle_path}:{name}: invalid resource pack root structure")


def validate_all(repo_root: Path) -> list[str]:
    """Run full validation across repository sources, root pack, dist packs, zips, and bundles."""
    errors: list[str] = []

    for text_file in collect_repo_text_files(repo_root):
        validate_text_encoding(text_file, errors)

    packs_cfg_path = repo_root / "config" / "packs.json"
    try:
        config, skills = pack_core.load_packs_config(packs_cfg_path)
    except Exception as exc:
        errors.append(f"{packs_cfg_path}: failed to load ({exc})")
        return errors

    expected_blocks = validate_match_blocks_config(repo_root, errors)
    if not expected_blocks:
        return errors

    pack_format = int(config["pack_format"])  # type: ignore[arg-type]
    root_cfg = config["default_root_pack"]
    assert isinstance(root_cfg, dict)
    root_skill = skills[str(root_cfg["skill"])]
    root_spec = pack_core.PackSpec(
        pack_name=pack_core.default_pack_name(
            root_skill.skill_id,
            int(root_cfg["offset_x"]),
            int(root_cfg["offset_z"]),
            int(root_cfg.get("offset_y", 0)),
        ),
        skill_id=root_skill.skill_id,
        display_name=root_skill.display_name,
        width=root_skill.width,
        depth=root_skill.depth,
        skill_height=root_skill.skill_height,
        y_base=root_skill.y_base,
        y_max=root_skill.y_max,
        offset_x=int(root_cfg["offset_x"]),
        offset_z=int(root_cfg["offset_z"]),
        offset_y=int(root_cfg.get("offset_y", 0)),
    )

    validate_pack_directory(repo_root, root_spec, expected_blocks, pack_format, errors)

    dist_packs_dir = repo_root / "dist" / "packs"
    dist_zips_dir = repo_root / "dist" / "zips"
    dist_bundles_dir = repo_root / "dist" / "bundles"

    expected_pack_names: set[str] = set()
    all_zip_bytes: dict[str, bytes] = {}
    expected_bundle_names: set[str] = {"IchiWakaru_All.zip"}

    for skill in skills.values():
        skill_zip_bytes: dict[str, bytes] = {}
        expected_bundle_names.add(f"IchiWakaru_{skill.skill_id}.zip")
        for ox, oz in skill.offsets:
            pack_name = pack_core.default_pack_name(skill.skill_id, ox, oz)
            expected_pack_names.add(pack_name)
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
            pack_dir = dist_packs_dir / pack_name
            if not pack_dir.is_dir():
                errors.append(f"Missing built pack directory: {pack_dir}")
                continue
            validate_pack_directory(pack_dir, spec, expected_blocks, pack_format, errors)

            pack_files = collect_pack_file_bytes(pack_dir)
            zip_path = dist_zips_dir / f"{pack_name}.zip"
            validate_zip_archive(zip_path, pack_files, errors)
            if zip_path.is_file():
                zbytes = zip_path.read_bytes()
                skill_zip_bytes[zip_path.name] = zbytes
                all_zip_bytes[zip_path.name] = zbytes

        validate_bundle_archive(
            dist_bundles_dir / f"IchiWakaru_{skill.skill_id}.zip",
            skill_zip_bytes,
            errors,
        )

    validate_bundle_archive(
        dist_bundles_dir / "IchiWakaru_All.zip",
        all_zip_bytes,
        errors,
    )

    # Check root pack matches built default pack byte-for-byte
    built_root_dir = dist_packs_dir / root_spec.pack_name
    if built_root_dir.is_dir():
        root_files = collect_pack_file_bytes(repo_root)
        built_root_files = collect_pack_file_bytes(built_root_dir)
        if root_files != built_root_files:
            errors.append(
                f"Repository root pack diverges from built default pack {built_root_dir}"
            )

    # Check no stale extra folders/zips exist in dist/packs, dist/zips, dist/bundles
    if dist_packs_dir.is_dir():
        actual_packs = {p.name for p in dist_packs_dir.iterdir() if p.is_dir()}
        if actual_packs != expected_pack_names:
            errors.append(
                f"dist/packs mismatch: extra={sorted(actual_packs - expected_pack_names)}, "
                f"missing={sorted(expected_pack_names - actual_packs)}"
            )
    if dist_zips_dir.is_dir():
        actual_zips = {p.name for p in dist_zips_dir.glob("*.zip")}
        expected_zips = {f"{n}.zip" for n in expected_pack_names}
        if actual_zips != expected_zips:
            errors.append(
                f"dist/zips mismatch: extra={sorted(actual_zips - expected_zips)}, "
                f"missing={sorted(expected_zips - actual_zips)}"
            )
    if dist_bundles_dir.is_dir():
        actual_bundles = {p.name for p in dist_bundles_dir.glob("*.zip")}
        if actual_bundles != expected_bundle_names:
            errors.append(
                f"dist/bundles mismatch: extra={sorted(actual_bundles - expected_bundle_names)}, "
                f"missing={sorted(expected_bundle_names - actual_bundles)}"
            )

    return errors


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Validate IchiWakaru repository and build artifacts.")
    parser.parse_args(argv)

    errors = validate_all(REPO_ROOT)
    if errors:
        print(f"Validation FAILED with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    config, skills = pack_core.load_packs_config(REPO_ROOT / "config" / "packs.json")
    _, blocks = pack_core.load_match_blocks(REPO_ROOT / "config" / "match_blocks.json")
    total_packs = sum(len(s.offsets) for s in skills.values())
    print(
        f"Validation PASSED: root synced, {len(skills)} skills, {total_packs} packs/zips, "
        f"{len(skills) + 1} bundles, {len(blocks)} matchBlocks (1.18.2), 0 BOM/encoding/integrity issues."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
