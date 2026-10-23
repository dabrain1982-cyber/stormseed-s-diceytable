#!/usr/bin/env python3
"""Generate the three board and card skins from one authoritative game model."""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


BOARD_W = 2048
BOARD_H = 1280
MAP_BOX = (70, 105, BOARD_W - 70, BOARD_H - 115)
CARD_W = 300
CARD_H = 480
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

STYLES = {
    "klassisch": {
        "board_bg": (224, 211, 178),
        "ocean": (224, 216, 194),
        "ink": (45, 40, 33),
        "line": (76, 67, 54),
        "card_bg": (237, 226, 195),
        "card_edge": (62, 50, 37),
        "accent": (120, 54, 42),
        "font": "DejaVuSerif.ttf",
    },
    "taktisch": {
        "board_bg": (5, 20, 37),
        "ocean": (5, 38, 61),
        "ink": (224, 247, 255),
        "line": (44, 194, 226),
        "card_bg": (8, 31, 50),
        "card_edge": (54, 214, 239),
        "accent": (255, 164, 66),
        "font": "DejaVuSans.ttf",
    },
    "farbenfroh": {
        "board_bg": (239, 245, 247),
        "ocean": (118, 211, 230),
        "ink": (27, 40, 54),
        "line": (255, 255, 255),
        "card_bg": (250, 250, 246),
        "card_edge": (31, 50, 65),
        "accent": (229, 72, 84),
        "font": "DejaVuSans.ttf",
    },
}


def font(style: dict, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    base = style["font"]
    if bold:
        base = base.replace(".ttf", "-Bold.ttf")
        if not (FONT_DIR / base).exists():
            base = "DejaVuSans-Bold.ttf"
    return ImageFont.truetype(str(FONT_DIR / base), size)


def project(lon: float, lat: float) -> tuple[int, int]:
    left, top, right, bottom = MAP_BOX
    x = left + (lon + 180.0) / 360.0 * (right - left)
    y = top + (85.0 - lat) / 145.0 * (bottom - top)
    return round(x), round(y)


def iter_polygons(geometry: dict):
    if geometry["type"] == "Polygon":
        yield geometry["coordinates"]
    elif geometry["type"] == "MultiPolygon":
        yield from geometry["coordinates"]


def ring_points(ring):
    points = [project(float(lon), float(lat)) for lon, lat in ring]
    if not points:
        return []
    # Natural Earth already splits most antimeridian shapes. Ignore the rare
    # ring that would otherwise draw a line across the whole board.
    if any(abs(points[i][0] - points[i - 1][0]) > BOARD_W * 0.7 for i in range(1, len(points))):
        return []
    return points


def draw_feature_mask(draw: ImageDraw.ImageDraw, feature: dict, fill: int):
    for polygon in iter_polygons(feature["geometry"]):
        outer = ring_points(polygon[0])
        if len(outer) >= 3:
            draw.polygon(outer, fill=fill)
        for hole in polygon[1:]:
            points = ring_points(hole)
            if len(points) >= 3:
                draw.polygon(points, fill=0)


def build_geometry(world: dict, geojson: dict):
    # Work at quarter resolution and scale the finished assignment map up with
    # nearest-neighbour sampling. This keeps the generated borders crisp and
    # avoids native numerical dependencies in the reproducible asset builder.
    scale = 4
    small_w, small_h = BOARD_W // scale, BOARD_H // scale

    def small_points(ring):
        points = ring_points(ring)
        return [(x // scale, y // scale) for x, y in points]

    groups = {
        "nordamerika": {"North America"},
        "suedamerika": {"South America"},
        "afrika": {"Africa"},
        "australien": {"Oceania"},
        "eurasien": {"Europe", "Asia"},
    }
    masks = {}
    for group, continents in groups.items():
        image = Image.new("L", (small_w, small_h), 0)
        draw = ImageDraw.Draw(image)
        for feature in geojson["features"]:
            if feature["properties"].get("CONTINENT") in continents:
                for polygon in iter_polygons(feature["geometry"]):
                    outer = small_points(polygon[0])
                    if len(outer) >= 3:
                        draw.polygon(outer, fill=255)
                    for hole in polygon[1:]:
                        points = small_points(hole)
                        if len(points) >= 3:
                            draw.polygon(points, fill=0)
        masks[group] = image

    territory_group = {}
    for territory in world["territories"]:
        continent = territory["continent"]
        territory_group[territory["id"]] = "eurasien" if continent in {"europa", "asien"} else continent

    assignment_data = bytearray([255]) * (small_w * small_h)
    for group, land_mask in masks.items():
        candidates = [
            (index, territory)
            for index, territory in enumerate(world["territories"])
            if territory_group[territory["id"]] == group
        ]
        centers = []
        for global_index, territory in candidates:
            cx, cy = project(*territory["label"])
            centers.append((global_index, cx / scale, cy / scale))
        land = land_mask.load()
        for y in range(small_h):
            offset = y * small_w
            for x in range(small_w):
                if not land[x, y]:
                    continue
                winner = min(
                    centers,
                    key=lambda item: ((x - item[1]) * 0.78) ** 2 + ((y - item[2]) * 1.12) ** 2,
                )
                assignment_data[offset + x] = winner[0]

    assignment_small = Image.frombytes("L", (small_w, small_h), bytes(assignment_data))
    assignment = assignment_small.resize((BOARD_W, BOARD_H), Image.Resampling.NEAREST)
    land = assignment.point(lambda value: 0 if value == 255 else 255, mode="L")
    return assignment, land, assignment_small


def hex_rgb(value: str):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def mix(color, other, amount):
    return tuple(round(color[i] * (1 - amount) + other[i] * amount) for i in range(3))


def dotted_line(draw, points, fill, width=3, dash=10):
    (x1, y1), (x2, y2) = points
    length = math.hypot(x2 - x1, y2 - y1)
    if not length:
        return
    for start in range(0, math.ceil(length), dash * 2):
        end = min(start + dash, length)
        a = start / length
        b = end / length
        draw.line((x1 + (x2 - x1) * a, y1 + (y2 - y1) * a, x1 + (x2 - x1) * b, y1 + (y2 - y1) * b), fill=fill, width=width)


def make_board(style_name: str, style: dict, world: dict, geojson: dict, assignment, land, assignment_small, output: Path):
    image = Image.new("RGB", (BOARD_W, BOARD_H), style["board_bg"])
    ocean_layer = Image.new("RGB", image.size, style["ocean"])
    noise = Image.effect_noise(image.size, 18).convert("L")
    noise_rgb = Image.merge("RGB", (noise, noise, noise))
    image = Image.blend(ocean_layer, noise_rgb, 0.055)

    continent_colors = {c["id"]: hex_rgb(c["color"]) for c in world["continents"]}
    for index, territory in enumerate(world["territories"]):
        base = continent_colors[territory["continent"]]
        if style_name == "taktisch":
            base = mix(base, (20, 120, 145), 0.28)
        elif style_name == "farbenfroh":
            base = mix(base, (255, 255, 255), 0.13)
        shade = 0.08 if index % 2 else -0.05
        target = (255, 255, 255) if shade > 0 else (0, 0, 0)
        color = mix(base, target, abs(shade))
        mask = assignment.point(lambda value, wanted=index: 255 if value == wanted else 0, mode="L")
        image.paste(Image.new("RGB", image.size, color), mask=mask)
    draw = ImageDraw.Draw(image)

    # Faint actual national borders underneath the 42 game-country borders.
    country_color = mix(style["line"], style["ocean"], 0.45)
    for feature in geojson["features"]:
        for polygon in iter_polygons(feature["geometry"]):
            points = ring_points(polygon[0])
            if len(points) >= 3:
                draw.line(points + [points[0]], fill=country_color, width=1)

    # Strong borders between game countries.
    small_w, small_h = assignment_small.size
    source = assignment_small.load()
    boundary_data = bytearray(small_w * small_h)
    for y in range(1, small_h):
        for x in range(1, small_w):
            value = source[x, y]
            if value != 255 and (source[x - 1, y] != value or source[x, y - 1] != value):
                boundary_data[y * small_w + x] = 255
    boundary_image = Image.frombytes("L", assignment_small.size, bytes(boundary_data)).resize(image.size, Image.Resampling.NEAREST).filter(ImageFilter.MaxFilter(5))
    border_layer = Image.new("RGB", image.size, style["line"])
    image.paste(border_layer, mask=boundary_image)
    draw = ImageDraw.Draw(image)

    territory_by_id = {t["id"]: t for t in world["territories"]}
    drawn = set()
    for territory in world["territories"]:
        p1 = project(*territory["label"])
        for neighbor_id in territory["neighbors"]:
            key = tuple(sorted((territory["id"], neighbor_id)))
            if key in drawn:
                continue
            drawn.add(key)
            neighbor = territory_by_id[neighbor_id]
            p2 = project(*neighbor["label"])
            distance = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            if distance > 240:
                # Route the Alaska/Kamchatka connection at both map edges.
                if key == ("alaska", "kamtschatka"):
                    dotted_line(draw, (p1, (MAP_BOX[0], p1[1])), style["line"], 3)
                    dotted_line(draw, ((MAP_BOX[2], p2[1]), p2), style["line"], 3)
                else:
                    dotted_line(draw, (p1, p2), style["line"], 3)

    title_font = font(style, 43, True)
    draw.text((BOARD_W // 2, 30), "STORMSEED’S CONQUEST", font=title_font, fill=style["ink"], anchor="ma")
    subtitle_font = font(style, 19)
    draw.text((BOARD_W // 2, 78), "42 Länder · 6 Kontinente", font=subtitle_font, fill=style["ink"], anchor="ma")

    for territory in world["territories"]:
        x, y = project(*territory["label"])
        size = 17 if len(territory["name"]) < 12 else 13
        label_font = font(style, size, style_name != "klassisch")
        draw.text((x, y), territory["name"], font=label_font, fill=style["ink"], anchor="mm", stroke_width=2, stroke_fill=style["ocean"])

    legend_x = 78
    legend_y = BOARD_H - 84
    for continent in world["continents"]:
        color = hex_rgb(continent["color"])
        draw.rounded_rectangle((legend_x, legend_y, legend_x + 27, legend_y + 27), radius=6, fill=color, outline=style["ink"], width=1)
        text = f'{continent["name"]} +{continent["bonus"]}'
        draw.text((legend_x + 36, legend_y + 14), text, font=font(style, 15, True), fill=style["ink"], anchor="lm")
        legend_x += 36 + draw.textlength(text, font=font(style, 15, True)) + 24

    if style_name == "klassisch":
        image = ImageEnhance.Color(image).enhance(0.86)
        image = image.filter(ImageFilter.GaussianBlur(0.18))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "WEBP", quality=93, method=6)


def wrap_text(draw, text, text_font, max_width):
    words = text.split()
    lines = []
    line = ""
    for word in words:
        probe = word if not line else f"{line} {word}"
        if draw.textlength(probe, font=text_font) <= max_width:
            line = probe
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def draw_unit_icon(draw, center, kind, color):
    x, y = center
    if kind == "infanterie":
        draw.ellipse((x - 11, y - 35, x + 11, y - 13), fill=color)
        draw.rounded_rectangle((x - 16, y - 11, x + 16, y + 27), radius=7, fill=color)
        draw.line((x - 9, y + 25, x - 16, y + 43), fill=color, width=7)
        draw.line((x + 9, y + 25, x + 16, y + 43), fill=color, width=7)
    elif kind == "reiter":
        draw.ellipse((x - 27, y - 7, x + 20, y + 22), fill=color)
        draw.polygon([(x + 10, y - 7), (x + 27, y - 23), (x + 22, y + 4)], fill=color)
        draw.ellipse((x - 4, y - 32, x + 10, y - 18), fill=color)
        draw.line((x - 20, y + 18, x - 25, y + 40), fill=color, width=6)
        draw.line((x + 10, y + 18, x + 18, y + 40), fill=color, width=6)
    else:
        draw.ellipse((x - 27, y + 10, x - 3, y + 34), outline=color, width=7)
        draw.ellipse((x + 8, y + 10, x + 32, y + 34), outline=color, width=7)
        draw.line((x - 10, y + 10, x + 19, y + 10), fill=color, width=10)
        draw.line((x + 5, y + 4, x + 30, y - 28), fill=color, width=8)


def territory_mask_image(index: int, assignment):
    mask = assignment.point(lambda value: 255 if value == index else 0, mode="L")
    bbox = mask.getbbox()
    if not bbox:
        return Image.new("L", (10, 10), 0)
    return mask.crop(bbox)


def make_territory_card(style_name, style, territory, continent, unit_type, mask, output):
    image = Image.new("RGB", (CARD_W, CARD_H), style["card_bg"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((6, 6, CARD_W - 7, CARD_H - 7), radius=22, outline=style["card_edge"], width=7)
    continent_color = hex_rgb(continent["color"])
    draw.rounded_rectangle((17, 17, CARD_W - 18, 76), radius=14, fill=continent_color)
    name_font = font(style, 24 if len(territory["name"]) < 15 else 19, True)
    draw.text((CARD_W // 2, 47), territory["name"], font=name_font, fill=(255, 255, 255), anchor="mm", stroke_width=1, stroke_fill=(30, 30, 30))

    panel = (34, 102, CARD_W - 34, 292)
    draw.rounded_rectangle(panel, radius=18, fill=mix(style["card_bg"], style["ocean"], 0.35), outline=style["card_edge"], width=2)
    silhouette = Image.new("RGBA", mask.size, (*continent_color, 255))
    silhouette.putalpha(mask)
    silhouette.thumbnail((190, 150), Image.Resampling.LANCZOS)
    image.paste(silhouette, ((CARD_W - silhouette.width) // 2, 120 + (150 - silhouette.height) // 2), silhouette)

    draw.text((CARD_W // 2, 316), continent["name"], font=font(style, 18, True), fill=style["ink"], anchor="mm")
    draw_unit_icon(draw, (CARD_W // 2, 386), unit_type, style["accent"])
    draw.text((CARD_W // 2, 455), unit_type.capitalize(), font=font(style, 15, True), fill=style["ink"], anchor="mm")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "WEBP", quality=92, method=6)


def make_mission_card(style_name, style, mission, output):
    image = Image.new("RGB", (CARD_W, CARD_H), style["card_bg"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((6, 6, CARD_W - 7, CARD_H - 7), radius=22, outline=style["card_edge"], width=7)
    draw.text((CARD_W // 2, 70), "MISSION", font=font(style, 32, True), fill=style["accent"], anchor="mm")
    draw.line((48, 103, CARD_W - 48, 103), fill=style["card_edge"], width=3)
    body_size = 18 if len(mission["text"]) > 95 else 22
    body_font = font(style, body_size, False)
    lines = wrap_text(draw, mission["text"], body_font, CARD_W - 72)
    line_h = body_size + 9
    top = 225 - (len(lines) - 1) * line_h // 2
    for i, line in enumerate(lines):
        draw.text((CARD_W // 2, top + i * line_h), line, font=body_font, fill=style["ink"], anchor="mm")
    # Original neutral compass emblem, not a copied game logo.
    cx, cy = CARD_W // 2, 405
    draw.ellipse((cx - 25, cy - 25, cx + 25, cy + 25), outline=style["accent"], width=3)
    draw.polygon([(cx, cy - 34), (cx + 8, cy), (cx, cy + 34), (cx - 8, cy)], fill=style["accent"])
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "WEBP", quality=92, method=6)


def make_back(style, label, output):
    image = Image.new("RGB", (CARD_W, CARD_H), style["card_edge"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((10, 10, CARD_W - 11, CARD_H - 11), radius=22, outline=style["accent"], width=8)
    draw.rounded_rectangle((28, 28, CARD_W - 29, CARD_H - 29), radius=17, outline=style["card_bg"], width=3)
    cx, cy = CARD_W // 2, CARD_H // 2 - 15
    draw.ellipse((cx - 62, cy - 62, cx + 62, cy + 62), outline=style["accent"], width=6)
    draw.polygon([(cx, cy - 82), (cx + 17, cy), (cx, cy + 82), (cx - 17, cy)], fill=style["accent"])
    draw.polygon([(cx - 82, cy), (cx, cy - 17), (cx + 82, cy), (cx, cy + 17)], fill=style["card_bg"])
    draw.text((CARD_W // 2, 380), label, font=font(style, 22, True), fill=style["card_bg"], anchor="mm")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "WEBP", quality=92, method=6)


def make_sheet(paths, columns, rows, output):
    sheet = Image.new("RGB", (columns * CARD_W, rows * CARD_H), (0, 0, 0))
    for index, path in enumerate(paths):
        card = Image.open(path).convert("RGB")
        sheet.paste(card, ((index % columns) * CARD_W, (index // columns) * CARD_H))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "WEBP", quality=91, method=6)


def make_store_media(board_path: Path, root: Path):
    board = Image.open(board_path).convert("RGB")
    media = root / "media"
    media.mkdir(parents=True, exist_ok=True)

    # DiceyTable gallery format: 1280 × 720, already cropped at authoring time.
    screenshot = Image.new("RGB", (1280, 720), STYLES["taktisch"]["board_bg"])
    fitted = board.copy()
    fitted.thumbnail((1280, 720), Image.Resampling.LANCZOS)
    screenshot.paste(fitted, ((1280 - fitted.width) // 2, (720 - fitted.height) // 2))
    screenshot.save(media / "screenshot-1.webp", "WEBP", quality=88, method=6)

    # Square cover with a self-contained title rather than a crop that would
    # discard half the world map.
    cover = Image.new("RGB", (512, 512), STYLES["taktisch"]["board_bg"])
    preview = board.copy()
    preview.thumbnail((486, 304), Image.Resampling.LANCZOS)
    cover.paste(preview, ((512 - preview.width) // 2, 142))
    draw = ImageDraw.Draw(cover)
    draw.text((256, 45), "STORMSEED’S", font=font(STYLES["taktisch"], 38, True), fill=(229, 247, 255), anchor="ma")
    draw.text((256, 91), "CONQUEST", font=font(STYLES["taktisch"], 48, True), fill=(54, 214, 239), anchor="ma")
    draw.text((256, 476), "42 LÄNDER · 6 KONTINENTE", font=font(STYLES["taktisch"], 17, True), fill=(229, 247, 255), anchor="mm")
    cover.save(media / "cover.webp", "WEBP", quality=90, method=6)
    cover.resize((256, 256), Image.Resampling.LANCZOS).save(media / "cover-thumb.webp", "WEBP", quality=88, method=6)


def write_deck(output, deck_id, name, sheet_path, back_path, cards, card_fields):
    definition = {
        "schemaVersion": 1,
        "id": deck_id,
        "name": name,
        "face": {
            "texturePath": sheet_path,
            "columns": 7 if len(cards) == 42 else 4,
            "rows": 6 if len(cards) == 42 else 3,
            "cardCount": len(cards),
            "cardWidthPx": CARD_W,
            "cardHeightPx": CARD_H,
        },
        "uniqueBacks": False,
        "back": {"kind": "single", "texturePath": back_path},
        "sideways": False,
        "backIsHidden": True,
        "cardFields": card_fields,
        "deckFields": [],
        "data": {},
        "cards": cards,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(definition, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--geojson", required=True, type=Path)
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1], type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    world = json.loads((root / "data/world.json").read_text())
    geojson = json.loads(args.geojson.read_text())
    assignment, land, assignment_small = build_geometry(world, geojson)
    continents = {c["id"]: c for c in world["continents"]}

    declared_assets = ["data/world.json"]
    unit_types = ["infanterie", "reiter", "geschütz"]
    for style_name, style in STYLES.items():
        board_rel = f"assets/boards/welt-{style_name}.webp"
        make_board(style_name, style, world, geojson, assignment, land, assignment_small, root / board_rel)
        declared_assets.append(board_rel)

        territory_paths = []
        territory_cards = []
        territory_slug = f"laender-{style_name}"
        for index, territory in enumerate(world["territories"]):
            rel = f"assets/decks/{territory_slug}/cards/{index:03d}-{territory['id']}.webp"
            make_territory_card(
                style_name,
                style,
                territory,
                continents[territory["continent"]],
                unit_types[index % 3],
                territory_mask_image(index, assignment),
                root / rel,
            )
            territory_paths.append(root / rel)
            territory_cards.append({
                "cardId": territory["id"],
                "label": territory["name"],
                "faceIndex": index,
                "count": 1,
                "data": {
                    "territory": territory["id"],
                    "continent": territory["continent"],
                    "unitType": unit_types[index % 3],
                },
            })
        territory_sheet = f"assets/textures/decks/{territory_slug}/sheet-1.webp"
        territory_back = f"assets/textures/decks/{territory_slug}/back.webp"
        territory_def = f"assets/decks/{territory_slug}.deck.json"
        make_sheet(territory_paths, 7, 6, root / territory_sheet)
        make_back(style, "LÄNDER", root / territory_back)
        write_deck(
            root / territory_def,
            territory_slug,
            f"Länderkarten – {style_name.capitalize()}",
            territory_sheet,
            territory_back,
            territory_cards,
            [
                {"key":"territory","label":"Land","type":"text"},
                {"key":"continent","label":"Kontinent","type":"text"},
                {"key":"unitType","label":"Einheit","type":"select","options":unit_types},
            ],
        )
        declared_assets.extend([territory_sheet, territory_back, territory_def])

        mission_paths = []
        mission_cards = []
        mission_slug = f"missionen-{style_name}"
        for index, mission in enumerate(world["missions"]):
            rel = f"assets/decks/{mission_slug}/cards/{index:03d}-{mission['id']}.webp"
            make_mission_card(style_name, style, mission, root / rel)
            mission_paths.append(root / rel)
            mission_cards.append({
                "cardId": mission["id"],
                "label": f"Mission {index + 1}",
                "faceIndex": index,
                "count": 1,
                "data": {"missionText": mission["text"]},
            })
        mission_sheet = f"assets/textures/decks/{mission_slug}/sheet-1.webp"
        mission_back = f"assets/textures/decks/{mission_slug}/back.webp"
        mission_def = f"assets/decks/{mission_slug}.deck.json"
        make_sheet(mission_paths, 4, 3, root / mission_sheet)
        make_back(style, "MISSION", root / mission_back)
        write_deck(
            root / mission_def,
            mission_slug,
            f"Missionskarten – {style_name.capitalize()}",
            mission_sheet,
            mission_back,
            mission_cards,
            [{"key":"missionText","label":"Auftrag","type":"text"}],
        )
        declared_assets.extend([mission_sheet, mission_back, mission_def])

    make_store_media(root / "assets/boards/welt-taktisch.webp", root)

    manifest_path = root / "diceytable.mod.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["assets"] = sorted(set(manifest.get("assets", [])) | set(declared_assets))
    manifest["summary"] = "Ein eigenständig gestaltetes Welt-Eroberungsspiel mit 42 Ländern und frei kombinierbaren Darstellungsstilen."
    manifest["description"] = "Stormseed’s Conquest enthält 42 Länderkarten, 12 Missionskarten und drei eigenständige Brett- und Kartenstile. Alle Grafiken wurden für dieses Projekt neu erzeugt; Markenlogos und fremde Spielgrafiken werden nicht verwendet."
    manifest["coverImage"] = "media/cover.webp"
    manifest["screenshots"] = [
        {
            "path": "media/screenshot-1.webp",
            "title": "Taktisches Weltbrett",
            "alt": "Weltspielbrett mit 42 beschrifteten Ländern in sechs farbigen Kontinenten.",
            "kind": "component",
        }
    ]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
