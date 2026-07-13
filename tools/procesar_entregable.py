#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
procesar_entregable.py — Pipeline DAMS: entregable crudo → capas web para el Visor.

Toma los archivos tal como se entregan al cliente (ortomosaico TIFF, MDS/MDT TIFF,
curvas DXF/DWG-exportado-a-DXF) y genera:

  data/c/<token>/
    tiles/orto_<fecha>/{z}/{x}/{y}.png      teselas XYZ del ortomosaico
    tiles/mdt_<fecha>/{z}/{x}/{y}.png       teselas XYZ del sombreado del MDT
    curvas_<fecha>.geojson                  curvas de nivel (WGS84)
    <nombre>.geojson                        cada DXF convertido (WGS84)
    config.json                             actualizado con las capas nuevas

REQUISITOS: GDAL ≥ 3.4 en el PATH. En Windows usar la consola "OSGeo4W Shell"
(viene con QGIS) donde gdal_translate, gdaldem, gdal2tiles y ogr2ogr ya funcionan.

USO TÍPICO (faja 2 = San Juan):
  python procesar_entregable.py --out ../data/c/fron7era-sx --faja 2 --fecha 2026-04 ^
      --orto "FRONTERA SA - San Expedito-orthomosaic.tiff" ^
      --mdt  "FRONTERA SA - San Expedito-dsm.tiff" ^
      --dxf  "DAMS - LA FRONTERA SA - Curvas de Nivel 5m.dxf" ^
      --cliente "FRONTERA SA" --proyecto "San Expedito"

Para una campaña nueva del mismo cliente, correr de nuevo con otra --fecha:
las capas se AGREGAN al config.json existente (y habilita el comparador de fechas).

NOTA DWG: GDAL no lee DWG. Exportar a DXF desde AutoCAD/Civil3D (SAVEAS → DXF 2013)
o con el ODA File Converter (gratuito).
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd):
    print("  $", " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd])
    if r.returncode != 0:
        sys.exit(f"ERROR: falló {cmd[0]} (código {r.returncode})")


def which_or_die(exe):
    # gdal2tiles puede ser .py, .bat o binario según instalación
    for cand in (exe, exe + ".exe", exe + ".bat", exe + ".py"):
        if shutil.which(cand):
            return shutil.which(cand)
    sys.exit(f"ERROR: no encuentro '{exe}' en el PATH. Abrí la consola OSGeo4W Shell (QGIS).")


def epsg_de_faja(faja: int) -> int:
    # POSGAR 2007 / Argentina 1..7 = EPSG:5343..5349
    if not 1 <= faja <= 7:
        sys.exit("ERROR: --faja debe ser 1..7")
    return 5342 + faja


def tilear_orto(orto: Path, out: Path, fecha: str, zooms: str):
    """Ortomosaico → teselas XYZ PNG (con JPEG interno para pesar menos)."""
    print(f"\n[1/4] Ortomosaico → teselas ({orto.name})")
    gdal2tiles = which_or_die("gdal2tiles")
    destino = out / "tiles" / f"orto_{fecha}"
    destino.mkdir(parents=True, exist_ok=True)
    # --xyz: esquema XYZ (el que usa MapLibre), -w none: sin visor html propio
    run([sys.executable, gdal2tiles, "--xyz", "-z", zooms, "-w", "none",
         "--processes", "4", str(orto), str(destino)]
        if gdal2tiles.endswith(".py") else
        [gdal2tiles, "--xyz", "-z", zooms, "-w", "none",
         "--processes", "4", str(orto), str(destino)])
    return {
        "id": f"orto-{fecha}",
        "nombre": f"Ortomosaico {fecha}",
        "tipo": "xyz",
        "fecha": fecha,
        "url": f"tiles/orto_{fecha}/{{z}}/{{x}}/{{y}}.png",
        "maxzoom": int(zooms.split("-")[-1]),
        "visible": True,
        "opacidad": 1,
    }


def tilear_mdt(mdt: Path, out: Path, fecha: str, zooms: str):
    """MDT/MDS → sombreado de relieve → teselas XYZ."""
    print(f"\n[2/4] MDT → sombreado + teselas ({mdt.name})")
    gdaldem = which_or_die("gdaldem")
    gdal2tiles = which_or_die("gdal2tiles")
    sombra = out / f"_hillshade_{fecha}.tif"
    run([gdaldem, "hillshade", "-compute_edges", "-z", "1.3",
         str(mdt), str(sombra), "-co", "COMPRESS=DEFLATE"])
    destino = out / "tiles" / f"mdt_{fecha}"
    destino.mkdir(parents=True, exist_ok=True)
    cmd = [gdal2tiles, "--xyz", "-z", zooms, "-w", "none", "--processes", "4",
           str(sombra), str(destino)]
    if gdal2tiles.endswith(".py"):
        cmd.insert(0, sys.executable)
    run(cmd)
    sombra.unlink(missing_ok=True)
    return {
        "id": f"mdt-{fecha}",
        "nombre": f"MDT — Sombreado {fecha}",
        "tipo": "xyz",
        "fecha": fecha,
        "url": f"tiles/mdt_{fecha}/{{z}}/{{x}}/{{y}}.png",
        "maxzoom": int(zooms.split("-")[-1]),
        "visible": False,
        "opacidad": 0.7,
    }


def curvas_desde_mdt(mdt: Path, out: Path, fecha: str, intervalo: float, epsg: int):
    """Genera curvas de nivel del MDT (opcional, si no vienen en DXF)."""
    print(f"\n[3/4] Curvas de nivel cada {intervalo} m")
    gdal_contour = which_or_die("gdal_contour")
    ogr2ogr = which_or_die("ogr2ogr")
    tmp = out / f"_curvas_{fecha}.gpkg"
    run([gdal_contour, "-a", "cota", "-i", str(intervalo), str(mdt), str(tmp)])
    salida = out / f"curvas_{fecha}.geojson"
    run([ogr2ogr, "-f", "GeoJSON", "-t_srs", "EPSG:4326",
         "-simplify", "0.5",  # metros: aliviana el archivo
         str(salida), str(tmp)])
    tmp.unlink(missing_ok=True)
    return {
        "id": f"curvas-{fecha}",
        "nombre": f"Curvas de nivel ({intervalo} m) {fecha}",
        "tipo": "geojson",
        "fecha": fecha,
        "url": salida.name,
        "color": "#F3C323",
        "grosor": 1.0,
        "visible": False,
    }


def convertir_dxf(dxf: Path, out: Path, epsg: int):
    """DXF (en POSGAR GK) → GeoJSON WGS84."""
    print(f"\n[4/4] DXF → GeoJSON ({dxf.name})")
    ogr2ogr = which_or_die("ogr2ogr")
    salida = out / (dxf.stem.replace(" ", "_") + ".geojson")
    run([ogr2ogr, "-f", "GeoJSON",
         "-s_srs", f"EPSG:{epsg}", "-t_srs", "EPSG:4326",
         str(salida), str(dxf)])
    return {
        "id": "cad-" + dxf.stem.replace(" ", "-").lower()[:40],
        "nombre": dxf.stem,
        "tipo": "geojson",
        "origen": "DXF",
        "url": salida.name,
        "visible": True,
    }


def actualizar_config(out: Path, capas_nuevas, cliente, proyecto, faja):
    cfg_path = out / "config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    else:
        cfg = {
            "cliente": cliente or out.name.upper(),
            "proyecto": proyecto or "",
            "crs": epsg_de_faja(faja),
            "centro": [-69.0, -31.0],
            "zoom": 12,
            "capas": [],
        }
    existentes = {c["id"] for c in cfg["capas"]}
    for c in capas_nuevas:
        if c["id"] in existentes:
            cfg["capas"] = [x if x["id"] != c["id"] else c for x in cfg["capas"]]
        else:
            cfg["capas"].append(c)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nconfig.json actualizado: {cfg_path}")
    print("Recordá ajustar 'centro'/'zoom' o agregar 'bounds' la primera vez.")


def main():
    ap = argparse.ArgumentParser(description="Entregable DAMS → capas web del Visor")
    ap.add_argument("--out", required=True, help="carpeta destino data/c/<token>")
    ap.add_argument("--faja", type=int, default=2, help="faja POSGAR 2007 (San Juan = 2)")
    ap.add_argument("--fecha", required=True, help="fecha de la campaña, ej. 2026-04")
    ap.add_argument("--orto", help="GeoTIFF del ortomosaico")
    ap.add_argument("--mdt", help="GeoTIFF del MDT/MDS")
    ap.add_argument("--dxf", nargs="*", default=[], help="DXF a convertir (curvas, plantas)")
    ap.add_argument("--curvas-cada", type=float, default=0,
                    help="genera curvas del MDT con este intervalo en m (0 = no)")
    ap.add_argument("--zooms", default="10-19", help="rango de zoom de teselas (def. 10-19)")
    ap.add_argument("--zooms-mdt", default="10-16", help="rango de zoom del MDT (def. 10-16)")
    ap.add_argument("--cliente", help="nombre del cliente (solo primera vez)")
    ap.add_argument("--proyecto", help="nombre del proyecto (solo primera vez)")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    epsg = epsg_de_faja(a.faja)
    capas = []

    if a.orto:
        capas.append(tilear_orto(Path(a.orto), out, a.fecha, a.zooms))
    if a.mdt:
        capas.append(tilear_mdt(Path(a.mdt), out, a.fecha, a.zooms_mdt))
        if a.curvas_cada > 0:
            capas.append(curvas_desde_mdt(Path(a.mdt), out, a.fecha, a.curvas_cada, epsg))
    for d in a.dxf:
        capas.append(convertir_dxf(Path(d), out, epsg))

    if not capas:
        sys.exit("Nada para procesar: pasá al menos --orto, --mdt o --dxf.")
    actualizar_config(out, capas, a.cliente, a.proyecto, a.faja)
    print("\nListo. Probá local con:  python -m http.server  →  http://localhost:8000/?c=" + out.name)


if __name__ == "__main__":
    main()
