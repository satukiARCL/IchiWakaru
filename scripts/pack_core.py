"""Core generation and validation utilities for IchiWakaru resource packs."""

from __future__ import annotations

from dataclasses import dataclass
import io
import json
from pathlib import Path
import shutil
import struct
import zipfile
import zlib
from typing import Mapping, Sequence


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FIXED_ZIP_DATE_TIME = (2026, 1, 1, 0, 0, 0)
TILE_SIZE = 16

LAYER_SPECS: dict[str, tuple[int, tuple[int, int, int, int]]] = {
    "dot": (1, (255, 127, 237, 255)),
    "x": (2, (255, 127, 0, 255)),
    "y": (3, (0, 127, 255, 255)),
}

RULE_DEFINITIONS: tuple[tuple[str, str, str, str, str], ...] = (
    ("top_and_bottom", "bottom.properties", "bottom", "opposite", "bottom"),
    ("top_and_bottom", "top.properties", "top", "opposite", "top"),
    ("side_bottom", "side_bottom.properties", "sides", "all", "bottom"),
    ("side_middle", "side_middle.properties", "sides", "all", "middle"),
    ("side_top", "side_top.properties", "sides", "all", "top"),
)

SHAPE_DIRS: tuple[str, ...] = ("top_and_bottom", "side_bottom", "side_middle", "side_top")


@dataclass(frozen=True)
class SkillConfig:
    """Definition of a seichi skill area and vertical repeat period."""

    skill_id: str
    display_name: str
    width: int
    depth: int
    skill_height: int
    y_base: int
    y_max: int
    offsets: tuple[tuple[int, int], ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "SkillConfig":
        offsets = tuple((int(pair[0]), int(pair[1])) for pair in data["offsets"])  # type: ignore[index]
        return cls(
            skill_id=str(data["id"]),
            display_name=str(data["display_name"]),
            width=int(data["width"]),  # type: ignore[arg-type]
            depth=int(data["depth"]),  # type: ignore[arg-type]
            skill_height=int(data["skill_height"]),  # type: ignore[arg-type]
            y_base=int(data["y_base"]),  # type: ignore[arg-type]
            y_max=int(data["y_max"]),  # type: ignore[arg-type]
            offsets=offsets,
        )


@dataclass(frozen=True)
class PackSpec:
    """Resolved specification for building a single IchiWakaru resource pack."""

    pack_name: str
    skill_id: str
    display_name: str
    width: int
    depth: int
    skill_height: int
    y_base: int
    y_max: int
    offset_x: int
    offset_z: int
    offset_y: int = 0

    def __post_init__(self) -> None:
        if self.width < 1 or self.depth < 1:
            raise ValueError(f"width and depth must be >= 1, got {self.width}x{self.depth}")
        if self.skill_height < 2:
            raise ValueError(f"skill_height must be >= 2, got {self.skill_height}")
        if self.y_base + self.offset_y > self.y_max:
            raise ValueError(
                f"effective y_base ({self.y_base + self.offset_y}) exceeds y_max ({self.y_max})"
            )

    @property
    def normalized_ox(self) -> int:
        """Horizontal X offset wrapped into [0, width)."""
        return self.offset_x % self.width

    @property
    def normalized_oz(self) -> int:
        """Horizontal Z offset wrapped into [0, depth)."""
        return self.offset_z % self.depth

    @property
    def effective_y_base(self) -> int:
        """Effective starting Y coordinate after applying offset_y."""
        return self.y_base + self.offset_y


def default_pack_name(
    skill_id: str,
    offset_x: int,
    offset_z: int,
    offset_y: int = 0,
    suffix: str = "",
) -> str:
    """Build canonical pack name from skill ID and offsets."""
    name = f"IchiWakaru_{skill_id}_ox{offset_x}_oz{offset_z}"
    if offset_y != 0:
        name += f"_oy{offset_y}"
    if suffix:
        name += f"_{suffix}"
    return name


def load_packs_config(config_path: Path) -> tuple[dict[str, object], dict[str, SkillConfig]]:
    """Load config/packs.json and return raw config dict and skill lookup."""
    data = json.loads(config_path.read_text(encoding="utf-8"))
    skills = {s.skill_id: s for s in (SkillConfig.from_dict(item) for item in data["skills"])}
    return data, skills


def load_match_blocks(config_path: Path) -> tuple[dict[str, object], list[str]]:
    """Load config/match_blocks.json and return metadata dict and block IDs."""
    data = json.loads(config_path.read_text(encoding="utf-8"))
    blocks = [str(b) for b in data["blocks"]]
    return data, blocks


def write_text_utf8(path: Path, content: str) -> None:
    """Write UTF-8 text without BOM, LF line endings, and trailing newline."""
    if not content.endswith("\n"):
        content += "\n"
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(normalized.encode("utf-8"))


def compute_layer_heights(
    y_base: int,
    y_max: int,
    skill_height: int,
    offset_y: int = 0,
) -> dict[str, list[int]]:
    """Compute bottom, middle, and top Y-coordinate lists up to y_max inclusive."""
    if skill_height < 2:
        raise ValueError(f"skill_height must be >= 2, got {skill_height}")
    effective_base = y_base + offset_y
    if effective_base > y_max:
        raise ValueError(f"effective_base ({effective_base}) exceeds y_max ({y_max})")

    bottom: list[int] = []
    middle: list[int] = []
    top: list[int] = []

    k = 0
    while True:
        cycle_start = effective_base + skill_height * k
        if cycle_start > y_max:
            break
        bottom.append(cycle_start)
        for dy in range(1, skill_height - 1):
            mid_y = cycle_start + dy
            if mid_y <= y_max:
                middle.append(mid_y)
        top_y = cycle_start + skill_height - 1
        if top_y <= y_max:
            top.append(top_y)
        k += 1

    return {"bottom": bottom, "middle": middle, "top": top}


def format_heights(values: Sequence[int]) -> str:
    """Format heights in OptiFine/Continuity syntax where negatives are parenthesized."""
    return " ".join(f"({v})" if v < 0 else str(v) for v in values)


def parse_heights(raw: str) -> list[int]:
    """Parse OptiFine/Continuity heights value string into a list of integers."""
    tokens = raw.strip().split()
    parsed: list[int] = []
    for tok in tokens:
        if tok.startswith("(") and tok.endswith(")"):
            val = int(tok[1:-1])
            if val >= 0:
                raise ValueError(f"Non-negative height wrapped in parentheses: {tok}")
            parsed.append(val)
        else:
            val = int(tok)
            if val < 0:
                raise ValueError(f"Negative height missing parentheses: {tok}")
            parsed.append(val)
    return parsed


def build_tiles_matrix(width: int, depth: int, offset_x: int, offset_z: int) -> list[list[int]]:
    """Generate width x depth CTM overlay_repeat tile index matrix."""
    if width < 1 or depth < 1:
        raise ValueError(f"width and depth must be >= 1, got {width}x{depth}")
    ox = offset_x % width
    oz = offset_z % depth
    matrix: list[list[int]] = []
    for row in range(depth):
        line: list[int] = []
        for col in range(width):
            if col == ox and row == oz:
                line.append(1)
            elif row == oz:
                line.append(2)
            elif col == ox:
                line.append(3)
            else:
                line.append(0)
        matrix.append(line)
    return matrix


def format_tiles_block(matrix: Sequence[Sequence[int]]) -> str:
    """Format tiles= multiline block using OptiFine backslash continuation."""
    lines = ["tiles=\\"]
    last_idx = len(matrix) - 1
    for idx, row in enumerate(matrix):
        joined = " ".join(str(v) for v in row)
        suffix = " \\" if idx < last_idx else ""
        lines.append(f"    {joined}{suffix}")
    return "\n".join(lines)


def render_properties(
    match_blocks: Sequence[str],
    faces: str,
    symmetry: str,
    heights: Sequence[int],
    tiles_matrix: Sequence[Sequence[int]],
) -> str:
    """Render a single CTM .properties file content."""
    if not heights:
        raise ValueError("heights must not be empty")
    width = len(tiles_matrix[0])
    depth = len(tiles_matrix)
    lines = [
        f"matchBlocks={' '.join(match_blocks)}",
        "connect=material",
        "method=overlay_repeat",
        f"faces={faces}",
        f"symmetry={symmetry}",
        f"heights={format_heights(heights)}",
        f"width={width}",
        f"height={depth}",
        format_tiles_block(tiles_matrix),
    ]
    return "\n".join(lines) + "\n"


def shape_pixel_mask(shape: str) -> set[tuple[int, int]]:
    """Return active (x, y) pixel coordinates in a 16x16 texture for the given rule shape."""
    coords: set[tuple[int, int]] = set()
    if shape == "top_and_bottom":
        for i in range(1, 15):
            coords.add((i, 1))
            coords.add((i, 14))
            coords.add((1, i))
            coords.add((14, i))
    elif shape == "side_bottom":
        for y in range(0, 15):
            coords.add((1, y))
            coords.add((14, y))
        for x in range(1, 15):
            coords.add((x, 14))
    elif shape == "side_middle":
        for y in range(0, 16):
            coords.add((1, y))
            coords.add((14, y))
    elif shape == "side_top":
        for y in range(1, 16):
            coords.add((1, y))
            coords.add((14, y))
        for x in range(1, 15):
            coords.add((x, 1))
    else:
        raise ValueError(f"Unknown shape: {shape}")
    return coords


def build_rgba_grid(
    shape: str,
    rgba: tuple[int, int, int, int] | None,
) -> list[list[tuple[int, int, int, int]]]:
    """Construct a 16x16 RGBA pixel grid for a shape (transparent if rgba is None)."""
    transparent = (0, 0, 0, 0)
    if rgba is None:
        return [[transparent for _ in range(TILE_SIZE)] for _ in range(TILE_SIZE)]
    active = shape_pixel_mask(shape)
    return [
        [rgba if (x, y) in active else transparent for x in range(TILE_SIZE)]
        for y in range(TILE_SIZE)
    ]


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def encode_rgba_png(grid: Sequence[Sequence[tuple[int, int, int, int]]]) -> bytes:
    """Encode an RGBA pixel grid (8-bit, color type 6) into PNG bytes."""
    height = len(grid)
    width = len(grid[0]) if height else 0
    if width == 0 or height == 0:
        raise ValueError("PNG grid must be non-empty")

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = bytearray()
    for row in grid:
        if len(row) != width:
            raise ValueError("Inconsistent PNG row width")
        raw.append(0)  # Filter type 0 (None)
        for r, g, b, a in row:
            raw.extend((r, g, b, a))

    idat = zlib.compress(bytes(raw), level=9)
    return b"".join((
        PNG_SIGNATURE,
        _png_chunk(b"IHDR", ihdr),
        _png_chunk(b"IDAT", idat),
        _png_chunk(b"IEND", b""),
    ))


def _unfilter_scanlines(raw: bytes, width: int, height: int, bit_depth: int, channels: int) -> list[bytes]:
    bits_per_pixel = bit_depth * channels
    row_bytes = (width * bits_per_pixel + 7) // 8
    bpp = max(1, bits_per_pixel // 8)
    expected = height * (1 + row_bytes)
    if len(raw) != expected:
        raise ValueError(f"Unexpected decompressed PNG size: {len(raw)} != {expected}")

    rows: list[bytes] = []
    prev = bytes(row_bytes)
    pos = 0
    for _ in range(height):
        ftype = raw[pos]
        pos += 1
        row = bytearray(raw[pos : pos + row_bytes])
        pos += row_bytes
        for i in range(row_bytes):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ftype == 0:
                pass
            elif ftype == 1:
                row[i] = (row[i] + a) & 0xFF
            elif ftype == 2:
                row[i] = (row[i] + b) & 0xFF
            elif ftype == 3:
                row[i] = (row[i] + ((a + b) >> 1)) & 0xFF
            elif ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[i] = (row[i] + pr) & 0xFF
            else:
                raise ValueError(f"Unsupported PNG filter type: {ftype}")
        prev = bytes(row)
        rows.append(prev)
    return rows


def decode_png(data: bytes) -> tuple[int, int, int, int, list[list[tuple[int, int, int, int]]]]:
    """Decode PNG bytes into (width, height, bit_depth, color_type, rgba_grid)."""
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("Invalid PNG signature")

    pos = len(PNG_SIGNATURE)
    idat = bytearray()
    plte: list[tuple[int, int, int]] = []
    trns = b""
    width = height = bit_depth = color_type = 0
    seen_ihdr = False
    seen_iend = False

    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError("Truncated PNG chunk header")
        length, ctype = struct.unpack(">I4s", data[pos : pos + 8])
        pos += 8
        if pos + length + 4 > len(data):
            raise ValueError(f"Truncated PNG chunk {ctype!r}")
        chunk_data = data[pos : pos + length]
        crc_actual = zlib.crc32(ctype + chunk_data) & 0xFFFFFFFF
        crc_expected = struct.unpack(">I", data[pos + length : pos + length + 4])[0]
        if crc_actual != crc_expected:
            raise ValueError(f"PNG CRC mismatch in chunk {ctype!r}")
        pos += length + 4

        if ctype == b"IHDR":
            width, height, bit_depth, color_type, comp, flt, inter = struct.unpack(">IIBBBBB", chunk_data)
            if comp != 0 or flt != 0 or inter != 0:
                raise ValueError(f"Unsupported PNG compression/filter/interlace: {(comp, flt, inter)}")
            seen_ihdr = True
        elif ctype == b"PLTE":
            if len(chunk_data) % 3 != 0:
                raise ValueError("Invalid PLTE length")
            plte = [
                (chunk_data[i], chunk_data[i + 1], chunk_data[i + 2])
                for i in range(0, len(chunk_data), 3)
            ]
        elif ctype == b"tRNS":
            trns = chunk_data
        elif ctype == b"IDAT":
            idat.extend(chunk_data)
        elif ctype == b"IEND":
            seen_iend = True
            break

    if not seen_ihdr or not seen_iend:
        raise ValueError("Missing IHDR or IEND chunk")

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ValueError(f"Unsupported color_type: {color_type}")

    raw = zlib.decompress(bytes(idat))
    rows = _unfilter_scanlines(raw, width, height, bit_depth, channels)
    grid: list[list[tuple[int, int, int, int]]] = []

    for row in rows:
        prow: list[tuple[int, int, int, int]] = []
        if color_type == 6 and bit_depth == 8:
            for x in range(width):
                prow.append((row[x * 4], row[x * 4 + 1], row[x * 4 + 2], row[x * 4 + 3]))
        elif color_type == 2 and bit_depth == 8:
            for x in range(width):
                prow.append((row[x * 3], row[x * 3 + 1], row[x * 3 + 2], 255))
        elif color_type == 4 and bit_depth == 8:
            for x in range(width):
                v, a = row[x * 2], row[x * 2 + 1]
                prow.append((v, v, v, a))
        elif color_type == 0 and bit_depth == 8:
            for x in range(width):
                v = row[x]
                prow.append((v, v, v, 255))
        elif color_type == 3 and bit_depth in (1, 2, 4, 8):
            mask = (1 << bit_depth) - 1
            per_byte = 8 // bit_depth
            for x in range(width):
                b = row[x // per_byte]
                shift = 8 - bit_depth * ((x % per_byte) + 1)
                idx = (b >> shift) & mask
                rgb = plte[idx]
                alpha = trns[idx] if idx < len(trns) else 255
                prow.append((rgb[0], rgb[1], rgb[2], alpha))
        else:
            raise ValueError(f"Unsupported PNG format: color_type={color_type}, bit_depth={bit_depth}")
        grid.append(prow)

    return width, height, bit_depth, color_type, grid


_PNG_CACHE: dict[tuple[str, str, int], bytes] = {}


def get_tile_png_bytes(layer: str, shape: str, tile_idx: int) -> bytes:
    """Return deterministic 16x16 RGBA PNG bytes for (layer, shape, tile_idx)."""
    key = (layer, shape, tile_idx)
    cached = _PNG_CACHE.get(key)
    if cached is not None:
        return cached

    active_idx, rgba = LAYER_SPECS[layer]
    grid = build_rgba_grid(shape, rgba if tile_idx == active_idx else None)
    data = encode_rgba_png(grid)
    _PNG_CACHE[key] = data
    return data


def build_pack_mcmeta(
    spec: PackSpec,
    pack_format: int = 8,
    author: str = "x256x",
    license_name: str = "CC0",
) -> str:
    """Render pack.mcmeta JSON string."""
    offset_parts = [f"ox={spec.normalized_ox}", f"oz={spec.normalized_oz}"]
    if spec.offset_y != 0:
        offset_parts.append(f"oy={spec.offset_y}")
    description = f"IchiWakaru ({spec.display_name} / {', '.join(offset_parts)}) - made by {author} {license_name}"
    payload = {
        "pack": {
            "pack_format": pack_format,
            "description": description,
        }
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def build_pack_tree(
    dest_dir: Path,
    spec: PackSpec,
    match_blocks: Sequence[str],
    pack_png_bytes: bytes,
    pack_format: int = 8,
    author: str = "x256x",
    license_name: str = "CC0",
    sync_root_mode: bool = False,
) -> None:
    """Write complete pack files to dest_dir (preserving non-CTM repo files when sync_root_mode=True)."""
    ctm_root = dest_dir / "assets" / "minecraft" / "optifine" / "ctm"

    if sync_root_mode:
        if ctm_root.exists():
            shutil.rmtree(ctm_root)
    else:
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "pack.png").write_bytes(pack_png_bytes)

    write_text_utf8(
        dest_dir / "pack.mcmeta",
        build_pack_mcmeta(spec, pack_format=pack_format, author=author, license_name=license_name),
    )

    heights_map = compute_layer_heights(
        y_base=spec.y_base,
        y_max=spec.y_max,
        skill_height=spec.skill_height,
        offset_y=spec.offset_y,
    )
    tiles_matrix = build_tiles_matrix(
        width=spec.width,
        depth=spec.depth,
        offset_x=spec.offset_x,
        offset_z=spec.offset_z,
    )

    active_rules = [
        rule for rule in RULE_DEFINITIONS if heights_map[rule[4]]
    ]
    active_shapes = list(dict.fromkeys(rule[0] for rule in active_rules))

    for layer in LAYER_SPECS:
        for shape in active_shapes:
            shape_dir = ctm_root / layer / shape
            shape_dir.mkdir(parents=True, exist_ok=True)
            for tile_idx in range(4):
                (shape_dir / f"{tile_idx}.png").write_bytes(
                    get_tile_png_bytes(layer, shape, tile_idx)
                )

        for shape, prop_name, faces, symmetry, height_key in active_rules:
            prop_path = ctm_root / layer / shape / prop_name
            content = render_properties(
                match_blocks=match_blocks,
                faces=faces,
                symmetry=symmetry,
                heights=heights_map[height_key],
                tiles_matrix=tiles_matrix,
            )
            write_text_utf8(prop_path, content)


def create_pack_zip_bytes(pack_dir: Path) -> bytes:
    """Create deterministic ZIP bytes with pack.mcmeta, pack.png, assets/ at ZIP root."""
    buf = io.BytesIO()
    targets: list[Path] = [pack_dir / "pack.mcmeta", pack_dir / "pack.png"]
    assets_dir = pack_dir / "assets"
    targets.extend(sorted(p for p in assets_dir.rglob("*") if p.is_file()))

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file_path in targets:
            rel = file_path.relative_to(pack_dir).as_posix()
            info = zipfile.ZipInfo(filename=rel, date_time=FIXED_ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, file_path.read_bytes())
    return buf.getvalue()


def write_bundle_zip(bundle_path: Path, zip_paths: Sequence[Path]) -> None:
    """Create a bundle ZIP containing individual pack ZIP files at the archive root."""
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for zp in sorted(zip_paths, key=lambda p: p.name):
            info = zipfile.ZipInfo(filename=zp.name, date_time=FIXED_ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, zp.read_bytes())
