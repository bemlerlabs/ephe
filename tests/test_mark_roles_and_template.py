"""The mark's roles, its template cut, and the six things `asset_check` proves.

`app/src/assets/mark.svg` carries no colour of its own: it names roles
(`var(--token)`) and `scripts/brand_palette.py` is the table the icon kit, the
in-app vector and the social card all read. The rasters concretise those roles to
a hex at build time. The creature's eyes are knockouts rather than paint, so the
vector needs no ground role to keep its face on either theme.

The five frozen hexes that used to sit in the generator are why this file exists:
the icon kit painted the paper red (#d83828) on its near-black field (4.03:1,
under the 4.5:1 floor), the in-app vector carried the same literal where no
`currentColor` reaches it, and no template cut existed anywhere. Every leg of
`scripts/asset_check.py` below was proven by breaking a planted copy of the
surface and requiring the refusal.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from brand_palette import ROLES  # noqa: E402  (path bootstrap above)

ASSET_CHECK = ROOT / "scripts" / "asset_check.py"
GENERATOR = ROOT / "scripts" / "generate_brand_assets.py"
PWA_NAMES = ("favicon.png", "icon-192.png", "icon-512.png", "icon-maskable-192.png",
             "icon-maskable-512.png", "apple-touch-icon-180.png")
#: What a planted surface needs before the mark half of the leg has anything to
#: judge: the vector family, the template raster, the stylesheet the roles resolve
#: in, and the two script files the boundary and geometry checks read.
COPIED = (
    "scripts/brand_palette.py",
    "scripts/generate_brand_assets.py",
    "app/src/styles/globals.css",
    "app/src/components/shell/EpheMark.tsx",
    "app/src/assets/mark.svg",
    "app/src/assets/mark-mono.svg",
    "app/src-tauri/icons/tray-mono.png",
)
FROZEN_RED = "#d83828"
FROZEN_RED_RGB = (0xD8, 0x38, 0x28)
INK_RED_RGB = (0xE8, 0x54, 0x3F)
ICON_FIELD = (0x12, 0x12, 0x12)


def generator_namespace(script: Path = GENERATOR) -> dict:
    """The generator's definitions, without its write phase (it writes on import)."""
    src = script.read_text(encoding="utf-8")
    src = src[: src.index('if __name__ != "__main__":')]
    src = src.replace("from playwright.sync_api import sync_playwright", "")
    namespace: dict = {"__name__": "brand_prefix", "__file__": str(script)}
    exec(compile(src, "brand_prefix", "exec"), namespace)
    return namespace


def checkerboard(path: Path, size: int = 64) -> None:
    """A two-tone asset: maximum contrast at any resample, so the floor cannot refuse it."""
    from PIL import Image

    image = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    for x in range(0, size, 8):
        for y in range(0, size, 8):
            if (x // 8 + y // 8) % 2:
                for px in range(x, min(x + 8, size)):
                    for py in range(y, min(y + 8, size)):
                        image.putpixel((px, py), (255, 255, 255, 255))
    image.save(path)


def plant_surface(root: Path) -> Path:
    """A copy of the repository's mark surface, small enough to break on purpose."""
    public = root / "app" / "public"
    icons = root / "app" / "src-tauri" / "icons"
    for directory in (public, icons, root / "app" / "src" / "assets", root / "scripts"):
        directory.mkdir(parents=True, exist_ok=True)
    for name in PWA_NAMES:
        checkerboard(public / name)
    checkerboard(icons / "icon.png")
    (public / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"></svg>\n', encoding="utf-8")
    (public / "manifest.json").write_text(json.dumps({
        "name": "Ephe", "icons": [{"src": name, "sizes": "192x192", "type": "image/png"}
                                  for name in PWA_NAMES],
    }, indent=2) + "\n", encoding="utf-8")
    (root / "app" / "index.html").write_text(
        "<html><head><link rel=\"icon\" href=\"/favicon.svg\">"
        "<link rel=\"manifest\" href=\"/manifest.json\">"
        "<script type=\"module\" src=\"/src/main.tsx\"></script></head><body></body></html>\n",
        encoding="utf-8")
    (root / "app" / "src" / "main.tsx").write_text("export {}\n", encoding="utf-8")
    for relative in COPIED:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return root


def run_gate(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ASSET_CHECK), "--root", str(root), *extra],
        text=True, capture_output=True, check=False, cwd=ROOT,
    )


def edit(path: Path, old: str, new: str) -> None:
    """Replace `old` with `new` in `path`, refusing a no-op edit."""
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{path.name} carries no {old!r} to break"
    path.write_text(text.replace(old, new), encoding="utf-8")


def css() -> str:
    return (ROOT / "app" / "src" / "styles" / "globals.css").read_text(encoding="utf-8")


def forest_table() -> dict[str, str]:
    """{--token: value} for the one ground the product ships."""
    found: dict[str, str] = {}
    for match in re.finditer(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;{}]+);", css()):
        found.setdefault(match.group(1), match.group(2).strip())
    return found


def resolved(token: str) -> str:
    """The literal `token` ends at, following the sheet's var() links."""
    table = forest_table()
    value = table[token]
    for _ in range(4):
        link = re.fullmatch(r"var\(\s*(--[a-zA-Z0-9-]+)\s*\)", value)
        if link is None:
            return value
        value = table[link.group(1)]
    raise AssertionError(f"{token} still links somewhere else in the sheet")


def hsl_rgb(literal: str) -> tuple[int, int, int]:
    """An `hsl()` literal as the 8-bit channels a browser paints."""
    match = re.fullmatch(r"hsl\(\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*\)", literal)
    assert match, f"not an hsl() literal: {literal}"
    hue, sat, light = (float(group) for group in match.groups())
    sat, light = sat / 100.0, light / 100.0
    a = sat * min(light, 1 - light)

    def channel(n: float) -> int:
        k = (n + hue / 30.0) % 12
        return round((light - a * max(-1.0, min(k - 3, min(9 - k, 1.0)))) * 255)

    red, green, blue = (channel(n) for n in (0, 8, 4))
    return red, green, blue


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    def linear(value: float) -> float:
        value = value / 255.0
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(value) for value in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(one: tuple[int, int, int], two: tuple[int, int, int]) -> float:
    high, low = sorted((relative_luminance(one), relative_luminance(two)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class TestTheRoleTable:
    """`scripts/brand_palette.py` against the sheet and the terminal surface."""

    def test_every_role_names_a_property_the_sheet_declares(self):
        sheet = css()
        for role in ROLES.values():
            if role.token == "currentColor":
                continue
            assert f"{role.token}:" in sheet, f"{role.name} names {role.token}, which the sheet omits"

    def test_the_mark_red_is_the_sheet_red(self):
        forest = hsl_rgb(resolved("--color-firefly"))
        assert forest == hsl_rgb(resolved("--color-brand")) == (0xE8, 0x54, 0x3F)
        # The raster halves are the sheet's own spellings, so the icon paints what
        # the app paints.
        assert ROLES["brand"].hex.upper() == "#E8543F"
        assert ROLES["brand_glow"].hex.upper() == "#F1705F"
        assert ROLES["brand_glow"].hex.upper() == "#%02X%02X%02X" % hsl_rgb(
            resolved("--color-firefly-glow"))

    def test_the_mark_red_is_the_terminals_accent(self):
        import ui.palette as terminal

        assert ROLES["brand"].hex.upper() == terminal.ACCENT.upper()

    def test_the_mark_red_clears_the_floor_on_the_shipped_ground(self):
        red = hsl_rgb(resolved("--color-firefly"))
        ground = hsl_rgb(resolved("--color-canvas"))
        ratio = contrast(red, ground)
        assert ratio >= 4.5, f"the mark red measures {ratio:.2f}:1 on the canvas"

    def test_the_tuned_ink_pair_measures_the_quoted_ratio(self):
        ratio = contrast(hsl_rgb(resolved("--color-firefly")),
                         hsl_rgb(resolved("--color-canvas")))
        assert round(ratio, 2) == 5.13, f"the tuned pair measures {ratio:.2f}:1"

    def test_the_frozen_literal_would_have_failed_the_same_floor(self):
        frozen = hsl_rgb("hsl(5.45 69.3% 50.2%)")
        assert frozen == FROZEN_RED_RGB
        ratio = contrast(frozen, hsl_rgb(resolved("--color-canvas")))
        assert round(ratio, 2) == 4.01, f"the frozen literal measured {ratio:.2f}:1"


class TestTheInAppVector:
    def test_the_vector_paints_no_literal_and_names_roles(self):
        text = (ROOT / "app/src/assets/mark.svg").read_text(encoding="utf-8")
        literals = re.findall(
            r'(?:fill|stroke|stop-color)="(#[0-9a-fA-F]{3,8}|rgba?\([^"]*\)|hsla?\([^"]*\))"', text)
        assert literals == [], f"the mark paints the literal(s) {literals}"
        assert "var(--" in text
        # The shipped in-app vector is the moth's full cut: the folded sheet is
        # painted by its own gradient, not the bee's eye pair.
        assert 'id="bspc-paper"' in text, "the in-app mark is not the moth's full cut"

    def test_the_creature_carries_the_roles_and_the_thread(self):
        text = (ROOT / "app/src/assets/mark.svg").read_text(encoding="utf-8")
        # The sheet: two gradient faces, both resolved through roles.
        assert 'stop-color="var(--color-figure-paper)"' in text
        assert 'stop-color="var(--color-figure-paper-lit)"' in text
        # The thread ties the wings with the product red — the one accent the
        # mark spends, and the same colour the interface uses for custody.
        assert 'stroke="var(--color-firefly)"' in text
        assert 'id="bspc-paper"' in text
        # A role reference or a currentColor, never a hex colour. `url(#id)` is not a
        # colour and is allowed, so this looks for a hash followed by hex digits.
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", text), (
            "the in-app mark reaches its colour through roles, not literals"
        )

    def test_the_stylesheet_keeps_the_host_colour_on_the_ink_role(self):
        rule = re.search(r"\.ephe-mark\s*\{([^}]*)\}", css())
        assert rule, "the stylesheet carries no .ephe-mark rule"
        assert "color: var(--color-ink)" in rule.group(1)
        assert "color: var(--color-brand)" not in rule.group(1)


class TestTheTemplateCut:
    def test_the_modifier_multiplies_a_band_and_leaves_the_routing_alone(self):
        namespace = generator_namespace()
        cuts, modifiers = namespace["MARK_CUTS"], namespace["MARK_MODIFIERS"]
        route, name = namespace["mark_variant_for"], namespace["mark_asset_for"]
        assert len(cuts) == 3, "a fourth entry would collide with the pinned routing"
        assert modifiers == ("mono",)
        assert [route(size) for size in (16, 24, 32)] == ["mark-micro"] * 3
        assert name(44, mono=True) == "mark-compact+mono"
        assert name(16) == "mark-micro"
        assert name(512, mono=True) == "mark+mono"

    def test_the_template_ships_as_a_vector_and_as_one_plane(self):
        vector = (ROOT / "app/src/assets/mark-mono.svg").read_text(encoding="utf-8")
        # One ink, and the creature's silhouette: no letter to punch out of the
        # body, so the whole cut is the outline the tray tints.
        assert "currentColor" in vector
        assert re.search(r'(?:fill|stop-color)="#', vector) is None

        from PIL import Image

        with Image.open(ROOT / "app/src-tauri/icons/tray-mono.png") as image:
            assert image.size == (44, 44)
            small = image.convert("RGBA").resize((16, 16), Image.Resampling.LANCZOS)
            visible = {(r, g, b) for r, g, b, a in small.get_flattened_data() if a > 128}
        assert visible == {(0, 0, 0)}, f"a template carries one visible plane, not {visible}"


class TestTheShippedRaster:
    """The 32 px icon is the micro cut: the silhouette, no crease and no thread."""

    def planes(self) -> Counter:
        from PIL import Image

        with Image.open(ROOT / "app/src-tauri/icons/32x32.png") as image:
            return Counter((r, g, b) for r, g, b, a in image.convert("RGBA").get_flattened_data()
                           if a > 200)

    def test_the_small_cut_is_the_sheet_and_paints_no_red(self):
        planes = self.planes()
        # The thread is a sub-pixel line at this size, so the micro cut drops it;
        # what must survive is the paper itself.
        light = sum(count for (r, g, b), count in planes.items() if r > 180 and b > 140)
        assert light > 100, "the icon no longer paints the sheet"
        assert planes[FROZEN_RED_RGB] == 0, "the icon still paints the frozen paper red"
        assert planes[INK_RED_RGB] == 0, "the micro cut carries no thread"

    def test_the_visible_red_measures_above_the_floor_on_the_icon_field(self):
        assert round(contrast(INK_RED_RGB, ICON_FIELD), 2) == 5.15
        assert round(contrast(FROZEN_RED_RGB, ICON_FIELD), 2) == 4.03


class TestTheGateOnTheRepository:
    def test_the_mark_surface_is_clean_and_the_tuned_pair_is_recorded(self):
        done = run_gate(ROOT)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "0 problem(s)" in done.stdout, done.stdout
        # Six in-app/public vectors: favicon.svg, mark.svg, mark-mono.svg and the
        # bee's three cuts (calm, fierce, template).
        assert "6 svg(s), 1 template asset(s)" in done.stdout, done.stdout
        assert "forest mark red" in done.stdout and "= 5.13:1" in done.stdout, done.stdout
        # The paper reading (5.42:1) left with the ground it measured; a second
        # ratio in this output would mean a second ground came back.
        assert "paper" not in done.stdout, done.stdout
        axis = re.findall(r"(mark(?:-micro|-compact)?): silhouette mass centre x=([\d.]+)",
                          done.stdout)
        assert axis, done.stdout
        # The figure is mirrored about the canvas middle; sub-pixel rounding in the
        # measurement is furniture, a lean is not.
        for name, value in axis:
            assert abs(float(value) - 256.0) <= 1.0, f"{name} leans to x={value}"


class TestTheGateOnABrokenCopy:
    """One planted defect per assertion, so the leg is proven and not recited."""

    def test_a_literal_in_the_in_app_vector_is_refused(self, tmp_path):
        root = plant_surface(tmp_path)
        edit(root / "app/src/assets/mark.svg", 'stroke="var(--color-firefly)"',
             f'stroke="{FROZEN_RED}"')
        done = run_gate(root)
        assert done.returncode == 1, done.stdout
        assert f"paints the literal(s) {FROZEN_RED}" in done.stdout, done.stdout
        # The literal is the first refusal; that the same red also sits under the
        # contrast floor is the role table's business (TestTheRoleTable measures it).

    def test_an_in_app_directory_without_the_mark_is_refused(self, tmp_path):
        root = plant_surface(tmp_path)
        (root / "app/src/assets/mark.svg").unlink()
        done = run_gate(root)
        assert done.returncode == 1, done.stdout
        assert "app/src/assets carries no mark.svg" in done.stdout, done.stdout

    def test_a_two_plane_template_is_refused(self, tmp_path):
        root = plant_surface(tmp_path)
        checkerboard(root / "app/src-tauri/icons/tray-mono.png")
        done = run_gate(root)
        assert done.returncode == 1, done.stdout
        assert "visible colour(s) after a 16 px resample, a template carries one" in done.stdout

    def test_an_absent_template_raster_is_refused(self, tmp_path):
        root = plant_surface(tmp_path)
        (root / "app/src-tauri/icons/tray-mono.png").unlink()
        done = run_gate(root)
        assert done.returncode == 1, done.stdout
        assert "tray-mono.png: absent, so the tray has no template image" in done.stdout

    def test_a_silhouette_off_the_optical_axis_is_refused(self, tmp_path):
        root = plant_surface(tmp_path)
        # The bee's micro cut is the generator's to change, so this adds one
        # off-axis mass to it. Naming the head or the blade here would make the
        # test fail the next time the figure is redrawn.
        edit(
            root / "scripts/generate_brand_assets.py",
            "    return moth_body(compact=compact, micro=micro, mono=mono, vector=vector)",
            "    body = moth_body(compact=compact, micro=micro, mono=mono, vector=vector)\n"
            "    if micro:\n"
            "        body += '<path d=\"M320,60 L320,460 L500,460 Z\" fill=\"currentColor\"/>'\n"
            "    return body",
        )
        done = run_gate(root)
        assert done.returncode == 1, done.stdout
        assert "off the optical axis at x=256" in done.stdout, done.stdout
        # Both small bands take the micro cut, so both lean.
        failures = [line for line in done.stdout.splitlines() if line.startswith("asset-check: FAIL")]
        assert any("mark-micro" in line for line in failures), failures

    def test_a_stale_band_in_the_generator_prose_is_refused(self, tmp_path):
        root = plant_surface(tmp_path)
        edit(root / "scripts/generate_brand_assets.py",
             "    The three size cuts live in MARK_CUTS; this docstring states no band.\n",
             "    - compact 24-47 px, - micro <=23 px.\n")
        done = run_gate(root)
        assert done.returncode == 1, done.stdout
        assert "names [24] px, which is no boundary of MARK_CUTS" in done.stdout, done.stdout
        assert "[33, 47, 48, 32, 0]" in done.stdout or "0, 32, 33, 47, 48" in done.stdout, done.stdout

    def test_a_stale_compact_band_in_the_tsx_is_refused(self, tmp_path):
        root = plant_surface(tmp_path)
        edit(root / "app/src/components/shell/EpheMark.tsx",
             "33-47 px (the compact band of MARK_CUTS)", "<= 24 px")
        done = run_gate(root)
        assert done.returncode == 1, done.stdout
        assert "app/src/components/shell/EpheMark.tsx: names [24] px" in done.stdout, done.stdout
