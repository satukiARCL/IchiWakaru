"""Unit and integration tests for IchiWakaru pack generation and validation."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_packs, pack_core, validate_packs


class TestHeightsAndTiles(unittest.TestCase):
    """Test mathematical height partitioning and tile matrix generation."""

    def test_tom_bowie_3x3_heights(self) -> None:
        heights = pack_core.compute_layer_heights(y_base=-60, y_max=320, skill_height=3)
        self.assertEqual(heights["bottom"][0], -60)
        self.assertEqual(heights["bottom"][-1], 318)
        self.assertEqual(heights["middle"][0], -59)
        self.assertEqual(heights["middle"][-1], 319)
        self.assertEqual(heights["top"][0], -58)
        self.assertEqual(heights["top"][-1], 320)
        self.assertEqual(len(heights["bottom"]), 127)
        self.assertEqual(len(heights["middle"]), 127)
        self.assertEqual(len(heights["top"]), 127)
        combined = sorted(heights["bottom"] + heights["middle"] + heights["top"])
        self.assertEqual(combined, list(range(-60, 321)))

    def test_11x11_heights_and_head_typo_regression(self) -> None:
        heights = pack_core.compute_layer_heights(y_base=-58, y_max=320, skill_height=11)
        self.assertEqual(heights["bottom"][0], -58)
        self.assertEqual(heights["bottom"][-1], 316)
        self.assertEqual(heights["top"][0], -48)
        self.assertEqual(heights["top"][-1], 315)
        # Regression check for HEAD typos (20, 205, 216 instead of 30, 305, 316)
        self.assertIn(30, heights["bottom"])
        self.assertIn(305, heights["bottom"])
        self.assertIn(316, heights["bottom"])
        self.assertNotIn(20, heights["bottom"])
        self.assertNotIn(205, heights["bottom"])
        self.assertNotIn(216, heights["bottom"])
        # Incomplete top cycle 316..320 must include middle 317..320 and nothing > 320
        for y in (317, 318, 319, 320):
            self.assertIn(y, heights["middle"])
        self.assertNotIn(321, heights["middle"])
        combined = sorted(heights["bottom"] + heights["middle"] + heights["top"])
        self.assertEqual(combined, list(range(-58, 321)))

    def test_eternal_vice_15x13_heights(self) -> None:
        heights = pack_core.compute_layer_heights(y_base=-60, y_max=320, skill_height=13)
        self.assertEqual(heights["bottom"][0], -60)
        self.assertEqual(heights["bottom"][-1], 317)
        self.assertEqual(heights["top"][0], -48)
        self.assertEqual(heights["top"][-1], 316)
        # Incomplete top cycle 317..320 must include middle 318..320
        for y in (318, 319, 320):
            self.assertIn(y, heights["middle"])
        self.assertNotIn(321, heights["middle"])
        combined = sorted(heights["bottom"] + heights["middle"] + heights["top"])
        self.assertEqual(combined, list(range(-60, 321)))

    def test_height_offset_and_validation_bounds(self) -> None:
        heights = pack_core.compute_layer_heights(y_base=-60, y_max=320, skill_height=3, offset_y=2)
        self.assertEqual(heights["bottom"][0], -58)
        self.assertEqual(heights["middle"][0], -57)
        self.assertEqual(heights["top"][0], -56)
        self.assertEqual(
            sorted(heights["bottom"] + heights["middle"] + heights["top"]),
            list(range(-58, 321)),
        )
        with self.assertRaises(ValueError):
            pack_core.compute_layer_heights(y_base=-60, y_max=320, skill_height=1)
        with self.assertRaises(ValueError):
            pack_core.compute_layer_heights(y_base=321, y_max=320, skill_height=3)

    def test_heights_format_roundtrip(self) -> None:
        values = [-60, -1, 0, 1, 320]
        formatted = pack_core.format_heights(values)
        self.assertEqual(formatted, "(-60) (-1) 0 1 320")
        self.assertEqual(pack_core.parse_heights(formatted), values)
        with self.assertRaises(ValueError):
            pack_core.parse_heights("-60 0")
        with self.assertRaises(ValueError):
            pack_core.parse_heights("(0) 3")

    def test_tiles_matrix_offsets_and_wrapping(self) -> None:
        base = pack_core.build_tiles_matrix(3, 3, 0, 0)
        self.assertEqual(base, [[1, 2, 2], [3, 0, 0], [3, 0, 0]])

        shifted = pack_core.build_tiles_matrix(3, 3, 1, 2)
        self.assertEqual(shifted, [[0, 3, 0], [0, 3, 0], [2, 1, 2]])

        wrapped = pack_core.build_tiles_matrix(11, 11, -1, 12)
        self.assertEqual(wrapped[1][10], 1)
        flat = [cell for row in wrapped for cell in row]
        self.assertEqual(flat.count(1), 1)
        self.assertEqual(flat.count(2), 10)
        self.assertEqual(flat.count(3), 10)
        self.assertEqual(flat.count(0), 100)


class TestPngTextures(unittest.TestCase):
    """Test deterministic 16x16 RGBA PNG generation and vertical frame continuity."""

    def test_side_middle_pixels_and_colors(self) -> None:
        expected_colors = {
            "dot": (1, (255, 127, 237, 255)),
            "x": (2, (255, 127, 0, 255)),
            "y": (3, (0, 127, 255, 255)),
        }
        for layer, (active_idx, rgba) in expected_colors.items():
            for tile_idx in range(4):
                png_bytes = pack_core.get_tile_png_bytes(layer, "side_middle", tile_idx)
                w, h, bd, ct, grid = pack_core.decode_png(png_bytes)
                self.assertEqual((w, h, bd, ct), (16, 16, 8, 6))
                for y in range(16):
                    for x in range(16):
                        if tile_idx == active_idx and x in (1, 14):
                            self.assertEqual(grid[y][x], rgba)
                        else:
                            self.assertEqual(grid[y][x], (0, 0, 0, 0))

    def test_vertical_frame_continuity_across_side_textures(self) -> None:
        for layer, (active_idx, rgba) in pack_core.LAYER_SPECS.items():
            _, _, _, _, top_grid = pack_core.decode_png(
                pack_core.get_tile_png_bytes(layer, "side_top", active_idx)
            )
            _, _, _, _, mid_grid = pack_core.decode_png(
                pack_core.get_tile_png_bytes(layer, "side_middle", active_idx)
            )
            _, _, _, _, bot_grid = pack_core.decode_png(
                pack_core.get_tile_png_bytes(layer, "side_bottom", active_idx)
            )
            # Bottom of side_top meets top of side_middle; bottom of side_middle meets top of side_bottom
            self.assertEqual(top_grid[15], mid_grid[0])
            self.assertEqual(mid_grid[15], bot_grid[0])
            self.assertEqual(mid_grid[0][1], rgba)
            self.assertEqual(mid_grid[0][14], rgba)

    def test_pack_png_decodes_cleanly(self) -> None:
        w, h, _, _, _ = pack_core.decode_png((REPO_ROOT / "pack.png").read_bytes())
        self.assertEqual((w, h), (16, 16))


class TestMatchBlocksAndValidation(unittest.TestCase):
    """Test 1.18.2 matchBlocks completeness, exclusions, and repository validation."""

    def test_match_blocks_curated_categories_and_exclusions(self) -> None:
        meta, blocks = pack_core.load_match_blocks(REPO_ROOT / "config" / "match_blocks.json")
        block_set = set(blocks)
        self.assertEqual(meta["minecraft_version"], "1.18.2")
        self.assertEqual(meta["pack_format"], 8)
        self.assertEqual(len(blocks), len(block_set))
        self.assertEqual(blocks, sorted(blocks))

        # Required representative blocks added in 1.18.2 curation
        expected_present = {
            "stone",
            "deepslate",
            "oak_stairs",
            "polished_deepslate_stairs",
            "waxed_oxidized_cut_copper_stairs",
            "oak_fence",
            "oak_fence_gate",
            "oak_door",
            "iron_trapdoor",
            "stone_button",
            "oak_pressure_plate",
            "white_stained_glass",
            "cyan_stained_glass_pane",
            "shulker_box",
            "purple_shulker_box",
            "red_carpet",
            "moss_carpet",
            "pointed_dripstone",
            "snow",
            "bedrock",
        }
        self.assertTrue(expected_present.issubset(block_set))

        # Non-solid / fluid / tech / post-1.18 blocks must be excluded
        must_absent = validate_packs.FORBIDDEN_NON_SOLID_OR_TECH | validate_packs.FORBIDDEN_POST_1_18_EXACT
        self.assertEqual(block_set & must_absent, set())

    def test_validate_all_repository_and_dist(self) -> None:
        errors = validate_packs.validate_all(REPO_ROOT)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_negative_encoding_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bom_file = tmp_path / "bom.txt"
            bom_file.write_bytes(b"\xef\xbb\xbfhello\n")
            errs_bom: list[str] = []
            validate_packs.validate_text_encoding(bom_file, errs_bom)
            self.assertTrue(any("BOM" in e for e in errs_bom))

            crlf_file = tmp_path / "crlf.txt"
            crlf_file.write_bytes(b"hello\r\n")
            errs_crlf: list[str] = []
            validate_packs.validate_text_encoding(crlf_file, errs_crlf)
            self.assertTrue(any("CRLF" in e for e in errs_crlf))


class TestCustomCliAndDeterminism(unittest.TestCase):
    """Test custom pack generation via CLI without touching repo root."""

    def test_custom_skill_build_and_validate(self) -> None:
        root_mcmeta_before = (REPO_ROOT / "pack.mcmeta").read_bytes()
        _, blocks = pack_core.load_match_blocks(REPO_ROOT / "config" / "match_blocks.json")

        with tempfile.TemporaryDirectory() as tmp:
            args = build_packs.parse_args([
                "--skill", "11x11",
                "--offset-x", "3",
                "--offset-z", "7",
                "--offset-y", "1",
                "--output-dir", tmp,
            ])
            self.assertTrue(build_packs.is_custom_mode(args))
            res = build_packs.build_custom(REPO_ROOT, args)
            pack_dir = Path(res["pack_dir"])
            zip_path = Path(res["zip_path"])

            spec = pack_core.PackSpec(
                pack_name=res["pack_name"],
                skill_id="11x11",
                display_name="11x11",
                width=11,
                depth=11,
                skill_height=11,
                y_base=-58,
                y_max=320,
                offset_x=3,
                offset_z=7,
                offset_y=1,
            )
            errors: list[str] = []
            validate_packs.validate_pack_directory(pack_dir, spec, blocks, 8, errors)
            validate_packs.validate_zip_archive(
                zip_path, validate_packs.collect_pack_file_bytes(pack_dir), errors
            )
            self.assertEqual(errors, [], msg="\n".join(errors))

        self.assertEqual((REPO_ROOT / "pack.mcmeta").read_bytes(), root_mcmeta_before)

    def test_custom_height_2_omits_side_middle_and_zip_is_deterministic(self) -> None:
        _, blocks = pack_core.load_match_blocks(REPO_ROOT / "config" / "match_blocks.json")
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            cli = [
                "--skill", "custom",
                "--width", "5",
                "--depth", "4",
                "--skill-height", "2",
                "--offset-x", "1",
                "--offset-z", "2",
            ]
            res1 = build_packs.build_custom(REPO_ROOT, build_packs.parse_args([*cli, "--output-dir", tmp1]))
            res2 = build_packs.build_custom(REPO_ROOT, build_packs.parse_args([*cli, "--output-dir", tmp2]))

            pack_dir1 = Path(res1["pack_dir"])
            self.assertFalse((pack_dir1 / "assets/minecraft/optifine/ctm/dot/side_middle").exists())
            self.assertEqual(Path(res1["zip_path"]).read_bytes(), Path(res2["zip_path"]).read_bytes())

            spec = pack_core.PackSpec(
                pack_name=res1["pack_name"],
                skill_id="custom",
                display_name="Custom (5x4x2)",
                width=5,
                depth=4,
                skill_height=2,
                y_base=-60,
                y_max=320,
                offset_x=1,
                offset_z=2,
                offset_y=0,
            )
            errors: list[str] = []
            validate_packs.validate_pack_directory(pack_dir1, spec, blocks, 8, errors)
            with zipfile.ZipFile(res1["zip_path"]) as zf:
                self.assertIn("pack.mcmeta", zf.namelist())
                self.assertIn("pack.png", zf.namelist())
            self.assertEqual(errors, [], msg="\n".join(errors))

    def test_cli_entrypoints_and_error_handling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = build_packs.main([
                    "--skill", "eternal_vice_15x13",
                    "--offset-x", "4",
                    "--offset-z", "9",
                    "--output-dir", tmp,
                ])
            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["pack_name"], "IchiWakaru_eternal_vice_15x13_ox4_oz9")
            self.assertTrue(Path(payload["zip_path"]).is_file())

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                bad_rc = build_packs.main(["--skill", "nonexistent_skill", "--output-dir", tmp])
            self.assertEqual(bad_rc, 2)
            self.assertIn("Unknown skill", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
