#!/usr/bin/env python3
"""Genera data/equipos.json y extrae fotos incrustadas desde todos los XLSX en datos/.
Solo usa la biblioteca estándar de Python para que funcione en GitHub Actions sin dependencias.
"""
from __future__ import annotations

import json
import posixpath
import re
import shutil
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "datos"
OUTPUT_JSON = ROOT / "data" / "equipos.json"
IMAGE_DIR = ROOT / "assets" / "equipos"

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}

ALIASES = {
    "institucion educacion superior centro de investigacion": "institucion",
    "nombre del equipo": "equipo",
    "tipo de equipo y funcionamiento": "descripcion",
    "numero de serie": "serie",
    "nombre del proyecto que adquirio el equipo": "proyecto",
    "ubicacion del equipo lugar especifico": "ubicacion",
    "funcionamiento": "funcionamiento",
    "equipo apto para brindar servicio a otra institucion": "servicio_externo",
    "foto": "foto_celda",
}


def norm(text: object) -> str:
    s = "" if text is None else str(text)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s).strip().lower()
    return re.sub(r"\s+", " ", s)


def slug(text: str, max_len: int = 70) -> str:
    s = norm(text).replace(" ", "-")
    return (s[:max_len].strip("-") or "item")


def resolve_ooxml(base_file: str, target: str) -> str:
    base_dir = posixpath.dirname(base_file)
    return posixpath.normpath(posixpath.join(base_dir, target))


def read_rels(zf: zipfile.ZipFile, rels_path: str) -> dict[str, str]:
    if rels_path not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(rels_path))
    return {rel.attrib["Id"]: rel.attrib["Target"] for rel in root.findall("rel:Relationship", NS)}


def shared_strings(zf: zipfile.ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in zf.namelist():
        return []
    root = ET.fromstring(zf.read(path))
    values = []
    for si in root.findall("main:si", NS):
        values.append("".join(t.text or "" for t in si.findall(".//main:t", NS)))
    return values


def column_index(cell_ref: str) -> int:
    m = re.match(r"([A-Z]+)", cell_ref)
    if not m:
        return 0
    n = 0
    for c in m.group(1):
        n = n * 26 + (ord(c) - 64)
    return n


def parse_sheet(zf: zipfile.ZipFile, sheet_path: str, strings: list[str]) -> tuple[dict[int, dict[int, object]], int]:
    root = ET.fromstring(zf.read(sheet_path))
    rows: dict[int, dict[int, object]] = {}
    max_row = 0
    for row in root.findall(".//main:sheetData/main:row", NS):
        rnum = int(row.attrib.get("r", "0"))
        max_row = max(max_row, rnum)
        cells: dict[int, object] = {}
        for cell in row.findall("main:c", NS):
            ref = cell.attrib.get("r", "A1")
            col = column_index(ref)
            ctype = cell.attrib.get("t")
            if ctype == "inlineStr":
                value = "".join(t.text or "" for t in cell.findall(".//main:t", NS))
            else:
                ve = cell.find("main:v", NS)
                raw = ve.text if ve is not None else None
                if raw is None:
                    value = ""
                elif ctype == "s":
                    try: value = strings[int(raw)]
                    except Exception: value = raw
                elif ctype == "b":
                    value = "Sí" if raw == "1" else "No"
                else:
                    value = raw
            cells[col] = value
        rows[rnum] = cells
    return rows, max_row


def sheet_images(zf: zipfile.ZipFile, sheet_path: str) -> dict[int, list[tuple[str, bytes]]]:
    """Devuelve {fila_excel: [(ext, bytes), ...]} para imágenes ancladas en la hoja."""
    rels_path = str(PurePosixPath(sheet_path).parent / "_rels" / (PurePosixPath(sheet_path).name + ".rels"))
    sheet_rels = read_rels(zf, rels_path)
    root = ET.fromstring(zf.read(sheet_path))
    drawing_ids = [d.attrib.get(f"{{{NS['r']}}}id") for d in root.findall("main:drawing", NS)]
    found: dict[int, list[tuple[str, bytes]]] = {}
    for rid in drawing_ids:
        if not rid or rid not in sheet_rels:
            continue
        drawing_path = resolve_ooxml(sheet_path, sheet_rels[rid])
        if drawing_path not in zf.namelist():
            continue
        drawing_rels_path = str(PurePosixPath(drawing_path).parent / "_rels" / (PurePosixPath(drawing_path).name + ".rels"))
        drawing_rels = read_rels(zf, drawing_rels_path)
        droot = ET.fromstring(zf.read(drawing_path))
        anchors = list(droot.findall("xdr:twoCellAnchor", NS)) + list(droot.findall("xdr:oneCellAnchor", NS))
        for anchor in anchors:
            row_el = anchor.find("xdr:from/xdr:row", NS)
            if row_el is None or row_el.text is None:
                continue
            excel_row = int(row_el.text) + 1
            blip = anchor.find(".//a:blip", NS)
            if blip is None:
                continue
            embed = blip.attrib.get(f"{{{NS['r']}}}embed")
            if not embed or embed not in drawing_rels:
                continue
            media_path = resolve_ooxml(drawing_path, drawing_rels[embed])
            if media_path not in zf.namelist():
                continue
            ext = Path(media_path).suffix.lower() or ".png"
            found.setdefault(excel_row, []).append((ext, zf.read(media_path)))
    return found


def find_header(rows: dict[int, dict[int, object]], max_scan: int = 40) -> tuple[int, dict[int, str]]:
    for rnum in sorted(rows)[:max_scan]:
        mapping: dict[int, str] = {}
        for col, value in rows[rnum].items():
            key = norm(value)
            if key in ALIASES:
                mapping[col] = ALIASES[key]
        if "equipo" in mapping.values() and "proyecto" in mapping.values():
            return rnum, mapping
    raise ValueError("No se encontró una fila de encabezados reconocible")


def project_code(rows: dict[int, dict[int, object]], header_row: int) -> str:
    text = " ".join(str(v) for r in range(1, header_row) for v in rows.get(r, {}).values() if v)
    matches = re.findall(r"\bcod(?:igo)?\.?\s*([A-Za-z0-9][A-Za-z0-9-]{4,})", text, flags=re.I)
    return matches[-1] if matches else ""


def clean(value: object) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if re.fullmatch(r"-?\d+\.0", s):
        s = s[:-2]
    return s


def process_xlsx(path: Path) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    warnings: list[str] = []
    with zipfile.ZipFile(path) as zf:
        strings = shared_strings(zf)
        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        wb_rels = read_rels(zf, "xl/_rels/workbook.xml.rels")
        for sheet in wb_root.findall("main:sheets/main:sheet", NS):
            sheet_name = sheet.attrib.get("name", "Hoja")
            rid = sheet.attrib.get(f"{{{NS['r']}}}id")
            if not rid or rid not in wb_rels:
                continue
            target = wb_rels[rid]
            sheet_path = posixpath.normpath(posixpath.join("xl", target))
            if sheet_path not in zf.namelist():
                continue
            rows, max_row = parse_sheet(zf, sheet_path, strings)
            try:
                header_row, col_map = find_header(rows)
            except ValueError:
                warnings.append(f"{path.name} / {sheet_name}: hoja omitida, no se reconocieron encabezados")
                continue
            code = project_code(rows, header_row)
            images_by_row = sheet_images(zf, sheet_path)
            data_started = False
            blank_streak = 0
            last_project = ""
            last_institution = ""
            for rnum in range(header_row + 1, max_row + 1):
                row = rows.get(rnum, {})
                item = {field: clean(row.get(col, "")) for col, field in col_map.items()}
                meaningful = [item.get(k, "") for k in ("institucion", "equipo", "descripcion", "serie", "proyecto", "ubicacion", "funcionamiento", "servicio_externo")]
                if not any(meaningful):
                    blank_streak += 1
                    if data_started and blank_streak >= 5:
                        break
                    continue
                blank_streak = 0
                if not item.get("equipo"):
                    continue
                data_started = True
                if item.get("proyecto"):
                    last_project = item["proyecto"]
                elif last_project:
                    item["proyecto"] = last_project
                if item.get("institucion"):
                    last_institution = item["institucion"]
                elif last_institution:
                    item["institucion"] = last_institution
                if not item.get("proyecto"):
                    continue
                item_id = f"{slug(path.stem,35)}-{slug(sheet_name,18)}-{rnum}"
                item.update({
                    "id": item_id,
                    "codigo_proyecto": code,
                    "fuente": path.name,
                    "hoja": sheet_name,
                    "fila_excel": rnum,
                    "foto": "",
                })
                # Preferir imagen incrustada en la fila.
                embedded = images_by_row.get(rnum, [])
                if embedded:
                    ext, content = embedded[0]
                    filename = f"{item_id}{ext}"
                    (IMAGE_DIR / filename).write_bytes(content)
                    item["foto"] = f"assets/equipos/{filename}"
                else:
                    cell_photo = item.get("foto_celda", "")
                    if re.match(r"^https?://", cell_photo, flags=re.I):
                        item["foto"] = cell_photo
                    elif cell_photo and norm(cell_photo) not in {"no aplica", "n a", "na"}:
                        candidate = path.parent / cell_photo
                        if candidate.is_file():
                            ext = candidate.suffix.lower() or ".jpg"
                            filename = f"{item_id}{ext}"
                            shutil.copyfile(candidate, IMAGE_DIR / filename)
                            item["foto"] = f"assets/equipos/{filename}"
                item.pop("foto_celda", None)
                items.append(item)
    return items, warnings


def main() -> None:
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for old in IMAGE_DIR.iterdir():
        if old.is_file(): old.unlink()
    xlsx_files = sorted(p for p in INPUT_DIR.rglob("*.xlsx") if not p.name.startswith("~$"))
    if not xlsx_files:
        raise SystemExit("No hay archivos .xlsx en la carpeta datos/")
    all_items: list[dict] = []
    warnings: list[str] = []
    for xlsx in xlsx_files:
        try:
            items, file_warnings = process_xlsx(xlsx)
            all_items.extend(items)
            warnings.extend(file_warnings)
        except Exception as exc:
            warnings.append(f"{xlsx.name}: ERROR {exc}")
    all_items.sort(key=lambda x: (norm(x.get("proyecto")), norm(x.get("equipo")), x.get("fila_excel", 0)))
    payload = {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "fuentes": [p.name for p in xlsx_files],
        "total": len(all_items),
        "advertencias": warnings,
        "equipos": all_items,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Catálogo generado: {len(all_items)} equipos desde {len(xlsx_files)} Excel.")
    print(f"Fotografías extraídas: {sum(1 for x in all_items if x.get('foto'))}.")
    for warning in warnings:
        print("AVISO:", warning)

if __name__ == "__main__":
    main()
