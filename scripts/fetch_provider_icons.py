#!/usr/bin/env python3
"""Descarrega ícones SVG de provedores (Simple Icons MIT, Wikimedia) e normaliza viewBox."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS_ROOT = ROOT / "src" / "rdrive" / "assets" / "providers"
STATIC_PROVIDERS = ROOT / "Static" / "providers"
SOURCES_MD_ASSETS = ASSETS_ROOT / "SOURCES.md"
SOURCES_MD_STATIC = STATIC_PROVIDERS / "SOURCES.md"

VIEWBOX_SIZE = 48
PADDING = 4
CONTENT_SIZE = VIEWBOX_SIZE - 2 * PADDING

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

SIMPLE_ICONS_RAW = (
    "https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/{slug}.svg"
)
WIKIMEDIA_FILE = "https://commons.wikimedia.org/wiki/Special:FilePath/{file}"

# Cores de marca (hex) para ícones Simple Icons monocromáticos.
BRAND_FILL: dict[str, str] = {
    "drive": "#4285F4",
    "dropbox": "#0061FF",
    "box": "#0061D5",
    "mega": "#D9272E",
    "b2": "#E21E29",
    "gcs": "#4285F4",
    "hdfs": "#66CCFF",
    "ftp": "#BF0000",
}


@dataclass(frozen=True)
class IconSource:
    label: str
    license: str
    url: str


@dataclass(frozen=True)
class IconSpec:
    stem: str
    category: str
    sources: tuple[IconSource, ...]
    brand_fill: str | None = None
    skip_fetch: bool = False


def _si(slug: str) -> IconSource:
    return IconSource(
        f"Simple Icons ({slug})",
        "MIT — https://github.com/simple-icons/simple-icons",
        SIMPLE_ICONS_RAW.format(slug=slug),
    )


def _wiki(file_name: str, license_note: str) -> IconSource:
    encoded = urllib.parse.quote(file_name, safe="")
    return IconSource(
        f"Wikimedia Commons ({file_name})",
        license_note,
        WIKIMEDIA_FILE.format(file=encoded),
    )


# Ícones canónicos (stems únicos de provider_icons._ICON_STEMS).
ICON_SPECS: tuple[IconSpec, ...] = (
    IconSpec("drive", "cloud", (_si("googledrive"),), brand_fill=BRAND_FILL["drive"]),
    IconSpec("dropbox", "cloud", (_si("dropbox"),), brand_fill=BRAND_FILL["dropbox"]),
    IconSpec(
        "onedrive",
        "cloud",
        (
            _wiki(
                "Microsoft_Office_OneDrive_(2019–present).svg",
                "Public domain / Microsoft trademark — uso descritivo",
            ),
        ),
        brand_fill="#0078D4",
    ),
    IconSpec(
        "sharepoint",
        "cloud",
        (
            _wiki(
                "Microsoft_Office_SharePoint_(2019–present).svg",
                "Public domain / Microsoft trademark — uso descritivo",
            ),
        ),
    ),
    IconSpec(
        "s3",
        "storage",
        (
            _wiki(
                "Amazon_Web_Services_Logo.svg",
                "AWS trademark — logo oficial via Commons",
            ),
        ),
    ),
    IconSpec("box", "cloud", (_si("box"),), brand_fill=BRAND_FILL["box"]),
    IconSpec("mega", "cloud", (_si("mega"),), brand_fill=BRAND_FILL["mega"]),
    IconSpec("pcloud", "cloud", (), skip_fetch=True),
    IconSpec("b2", "storage", (_si("backblaze"),), brand_fill=BRAND_FILL["b2"]),
    IconSpec(
        "gcs",
        "storage",
        (_si("googlecloudstorage"), _si("googlecloud")),
        brand_fill=BRAND_FILL["gcs"],
    ),
    IconSpec(
        "azureblob",
        "storage",
        (
            _wiki(
                "Microsoft_Azure_Logo.svg",
                "Microsoft trademark — logo via Commons",
            ),
        ),
        brand_fill="#0078D4",
    ),
    IconSpec("webdav", "protocol", (), skip_fetch=True),
    IconSpec("sftp", "protocol", (), skip_fetch=True),
    IconSpec("ftp", "protocol", (_si("filezilla"),), brand_fill=BRAND_FILL["ftp"]),
    IconSpec("hdfs", "protocol", (_si("apachehadoop"),), brand_fill=BRAND_FILL["hdfs"]),
    IconSpec("smb", "protocol", (), skip_fetch=True),
    IconSpec("local", "local", (), skip_fetch=True),
    IconSpec("terabox", "cloud", (), skip_fetch=True),
)

TERABOX_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" role="img">
  <rect fill="#2563EB" x="9" y="9" width="30" height="30" rx="8"/>
  <path fill="#fff" d="M24 15v18M17 24h14" stroke="#fff" stroke-width="3.5" stroke-linecap="round"/>
</svg>
"""

TERABOX_SOURCE = IconSource(
    "RDrive (geométrico, cores marca TeraBox)",
    "Original — não é logótipo oficial; substituir se obtiver asset licenciado",
    "(embedded)",
)

LOCAL_SOURCES: dict[str, tuple[str, str]] = {
    "pcloud": ("RDrive / existente", "Arte simplificada — sem slug Simple Icons"),
    "webdav": ("RDrive / existente", "Ícone protocolo (original)"),
    "sftp": ("RDrive / existente", "Ícone protocolo (original)"),
    "smb": ("RDrive / existente", "Ícone protocolo (original)"),
    "local": ("RDrive / existente", "Ícone pasta local (original)"),
}


def _http_get(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "RDrive-fetch-provider-icons/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_viewbox(root: ET.Element) -> tuple[float, float, float, float]:
    vb = root.get("viewBox") or root.get("viewbox")
    if vb:
        parts = [float(x) for x in re.split(r"[\s,]+", vb.strip()) if x]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    def _num(attr: str, default: float) -> float:
        raw = root.get(attr) or ""
        m = re.match(r"([\d.]+)", raw)
        return float(m.group(1)) if m else default

    w = _num("width", 24.0)
    h = _num("height", 24.0)
    return 0.0, 0.0, w, h


def _strip_noise(root: ET.Element) -> None:
    for child in list(root):
        name = _local_name(child.tag)
        if name in {"title", "desc", "metadata", "defs", "sodipodi:namedview", "namedview"}:
            root.remove(child)


def _apply_brand_fill(root: ET.Element, fill: str | None) -> None:
    if not fill:
        return
    for el in root.iter():
        if _local_name(el.tag) != "path":
            continue
        if "fill" not in el.attrib and "style" not in el.attrib:
            el.set("fill", fill)
        elif el.get("fill", "").lower() in ("#000", "#000000", "black", "currentcolor"):
            el.set("fill", fill)


def normalize_svg(svg_bytes: bytes, *, brand_fill: str | None = None) -> bytes:
    """Reencaixa o gráfico em viewBox 0 0 48 48 com margem uniforme."""
    svg_bytes = _clean_svg_bytes(svg_bytes)
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return svg_bytes

    if _local_name(root.tag) != "svg":
        return svg_bytes

    _strip_noise(root)
    xmin, ymin, vw, vh = _parse_viewbox(root)
    if vw <= 0 or vh <= 0:
        return svg_bytes

    children = list(root)
    if (
        root.get("viewBox") == f"0 0 {VIEWBOX_SIZE} {VIEWBOX_SIZE}"
        and len(children) == 1
        and _local_name(children[0].tag) == "g"
        and children[0].get("transform")
    ):
        for key in list(root.attrib):
            if key == "xmlns" or key.endswith("xmlns"):
                del root.attrib[key]
        root.set("xmlns", SVG_NS)
        root.set("role", "img")
        return _clean_svg_bytes(
            ET.tostring(root, encoding="utf-8", xml_declaration=False)
        )

    scale = CONTENT_SIZE / max(vw, vh)
    scaled_w = vw * scale
    scaled_h = vh * scale
    tx = PADDING + (CONTENT_SIZE - scaled_w) / 2.0 - xmin * scale
    ty = PADDING + (CONTENT_SIZE - scaled_h) / 2.0 - ymin * scale

    children = list(root)
    for child in children:
        root.remove(child)

    wrapper = ET.SubElement(
        root,
        f"{{{SVG_NS}}}g",
        transform=f"translate({tx:.4f},{ty:.4f}) scale({scale:.6f})",
    )
    for child in children:
        wrapper.append(child)

    root.set("viewBox", f"0 0 {VIEWBOX_SIZE} {VIEWBOX_SIZE}")
    for key in list(root.attrib):
        if key == "xmlns" or key.endswith("xmlns"):
            del root.attrib[key]
    root.set("xmlns", SVG_NS)
    root.set("role", "img")
    for attr in ("width", "height", "version", "id"):
        root.attrib.pop(attr, None)

    _apply_brand_fill(root, brand_fill)

    out = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    return _clean_svg_bytes(out)


def _clean_svg_bytes(data: bytes) -> bytes:
    text = data.decode("utf-8")
    # Resíduo de xmlns duplicado removido de forma incompleta (atributo órfão).
    text = re.sub(
        r'(\s)http://www\.w3\.org/2000/svg(?=["\s/>])',
        r"\1",
        text,
    )
    text = re.sub(r'role="img"\s+"', 'role="img"', text)
    text = re.sub(r'role="img"\s+>', "role=\"img\">", text)
    while text.count('xmlns="') > 1:
        second = text.find('xmlns="', text.find('xmlns="') + 1)
        if second == -1:
            break
        value_start = second + len('xmlns="')
        end = text.find('"', value_start) + 1
        text = text[:second] + text[end:]
    return text.encode("utf-8")


def _is_low_quality(path: Path) -> bool:
    if not path.is_file():
        return True
    data = path.read_bytes()
    if len(data) < 80:
        return True
    text = data.decode("utf-8", errors="ignore")
    if "viewBox" not in text:
        return True
    if re.search(r'viewBox="0 0 48 48"', text) and len(data) < 120:
        return True
    return False


def fetch_icon_bytes(spec: IconSpec) -> tuple[bytes | None, IconSource | None]:
    if spec.stem == "terabox":
        return TERABOX_SVG.encode("utf-8"), TERABOX_SOURCE

    for source in spec.sources:
        try:
            data = _http_get(source.url)
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeEncodeError):
            continue
        if data.strip().startswith((b"<svg", b"<?xml", b"<SVG")):
            return data, source
    return None, None


def write_sources_md(records: list[tuple[str, str, str]]) -> None:
    lines = [
        "# Fontes dos ícones de provedor",
        "",
        "Um ícone por linha. Prioridade: [Simple Icons](https://simpleicons.org/) (MIT), "
        "depois Wikimedia Commons. Ícones de protocolo sem marca usam arte RDrive.",
        "",
    ]
    for stem, source, license_note in sorted(records, key=lambda r: r[0]):
        lines.append(f"- `{stem}.svg` — {source} — {license_note}")
    lines.append("")
    text = "\n".join(lines)
    SOURCES_MD_ASSETS.parent.mkdir(parents=True, exist_ok=True)
    SOURCES_MD_ASSETS.write_text(text, encoding="utf-8")
    STATIC_PROVIDERS.mkdir(parents=True, exist_ok=True)
    SOURCES_MD_STATIC.write_text(text, encoding="utf-8")


def process_spec(
    spec: IconSpec,
    *,
    force: bool,
    dry_run: bool,
    normalize_only: bool,
) -> tuple[str, str, str] | None:
    dest = ASSETS_ROOT / spec.category / f"{spec.stem}.svg"
    dest.parent.mkdir(parents=True, exist_ok=True)

    source_used: IconSource | None = None
    raw: bytes | None = None

    should_download = not normalize_only and (
        spec.stem == "terabox"
        or (
            not spec.skip_fetch
            and (force or not dest.is_file() or _is_low_quality(dest))
        )
    )

    if should_download:
        raw, source_used = fetch_icon_bytes(spec)
        if raw is None and dest.is_file():
            raw = dest.read_bytes()
            source_used = IconSource("existente (fetch falhou)", "—", "(local)")
        elif raw is None:
            print(f"[skip] {spec.stem}: sem fonte remota", file=sys.stderr)
            return None
    elif dest.is_file():
        raw = dest.read_bytes()
        if spec.stem == "terabox":
            source_used = TERABOX_SOURCE
        elif spec.stem in LOCAL_SOURCES:
            label, lic = LOCAL_SOURCES[spec.stem]
            source_used = IconSource(label, lic, "(local)")
        else:
            source_used = IconSource("existente (normalização)", "—", "(local)")
    else:
        print(f"[skip] {spec.stem}: ficheiro em falta", file=sys.stderr)
        return None

    normalized = normalize_svg(raw, brand_fill=spec.brand_fill)
    if not dry_run:
        dest.write_bytes(normalized)

    if source_used:
        return (spec.stem, source_used.label, source_used.license)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-descarregar mesmo que o SVG já exista",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Não gravar ficheiros",
    )
    parser.add_argument(
        "--normalize-only",
        action="store_true",
        help="Apenas normalizar SVGs locais (sem HTTP)",
    )
    args = parser.parse_args()

    updated = 0
    records: list[tuple[str, str, str]] = []

    for spec in ICON_SPECS:
        before = (ASSETS_ROOT / spec.category / f"{spec.stem}.svg").read_bytes() if (
            ASSETS_ROOT / spec.category / f"{spec.stem}.svg"
        ).is_file() else None
        rec = process_spec(
            spec,
            force=args.force,
            dry_run=args.dry_run,
            normalize_only=args.normalize_only,
        )
        after_path = ASSETS_ROOT / spec.category / f"{spec.stem}.svg"
        if rec:
            records.append(rec)
        if after_path.is_file():
            after = after_path.read_bytes()
            if before != after and not args.dry_run:
                updated += 1
                print(f"[ok] {spec.stem} -> {after_path.relative_to(ROOT)}")

    # Fallback genérico — só normalizar
    fallback = ASSETS_ROOT / "_fallback" / "generic.svg"
    if fallback.is_file():
        norm = normalize_svg(fallback.read_bytes())
        if not args.dry_run:
            fallback.write_bytes(norm)
        records.append(("generic", "RDrive / existente", "Original"))

    if not args.dry_run:
        write_sources_md(records)

    print(f"[RDrive] {updated} ícone(s) atualizado(s) em {ASSETS_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
