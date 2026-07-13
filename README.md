# VISOR DAMS — Entregables geoespaciales para clientes

Visor de mapas web (archivo único, sin build, marca DAMS) para que los clientes
vean **ortomosaicos, modelos digitales de terreno, curvas de nivel y planos CAD**
sin instalar nada. El visor se publica gratis en **GitHub Pages** y **lee los
datos directo desde Google Drive** — los archivos quedan donde ya están, en la
carpeta CLIENTES de info@dams.com.ar.

```
https://<usuario>.github.io/visor/?c=<código-de-proyecto>
```

Cada cliente recibe un **código de acceso** (token no adivinable) que carga solo
sus capas: el de Los Azules ve Los Azules, el de Loma Negra ve Loma Negra.

---

## Cómo funciona (sin pipeline)

```
index.html                   ← visor (MapLibre GL + geotiff.js, único archivo)
data/visor.json              ← clave de API de Google Drive (global)
data/c/<token>/config.json   ← manifiesto de UN cliente (IDs de Drive)
tools/serve.js               ← server local de desarrollo (con Range requests)
tools/procesar_entregable.py ← plan B opcional (ver abajo)
```

1. El config del cliente apunta a **carpetas o archivos de Drive** (sus IDs).
2. El visor lista la carpeta por la API de Drive y clasifica solo:
   - `*.tif/tiff` → ortomosaico (o MDT si el nombre contiene dsm/dtm/mdt/dem)
   - `*.geojson / *.kml / *.kmz / *.dxf` → vectores superpuestos
   - `*.pdf / *.dwg / *.ecw / *.las` → lista **"Archivos para descarga"** (link a Drive)
3. Los GeoTIFF se leen **por partes** (HTTP Range) con `geotiff.js`: el visor
   baja solo la ventana que estás mirando, a la resolución que necesitás.
   La proyección sale de las geokeys del TIFF (POSGAR 2007, POSGAR 94 y UTM
   se resuelven solos; si no, usa el `crs` del config).
4. El MDT se sombrea en el navegador y habilita **cota real al hacer clic**.

### Requisitos (una sola vez)

1. **Clave de API de Google** (gratis, 5 min): Google Cloud Console → crear
   proyecto → habilitar *Google Drive API* → Credenciales → **Clave de API**.
   Restringirla a la Drive API y al dominio del visor (HTTP referrer).
   Pegarla en `data/visor.json` → `"driveApiKey"`.
2. **Compartir por enlace**: la carpeta del cliente (o la subcarpeta
   `08. ENTREGABLES`) debe estar en "**Cualquier persona con el enlace**" —
   igual que hoy cuando se la comparten al cliente.

### La única condición sobre los TIFF

Para que un ortomosaico de 5 GB se pueda mirar online por partes, el TIFF debe
tener **estructura interna de tiles + pirámides** (overviews). Los exports de
fotogrametría suelen tenerla; si un archivo no la tiene, el visor lo avisa y
solo carga al acercarse. La solución permanente es tildar **"Cloud Optimized
GeoTIFF (COG)"** al exportar desde Metashape/Pix4D — no es un paso extra de
procesamiento, es una opción del export que ya hacés.

> Nota: **ECW y DWG no se pueden leer en el navegador** (formatos cerrados).
> Van a la lista de descargas. El DWG se puede ver si se exporta también un
> DXF o KMZ al entregar (SAVEAS → DXF en AutoCAD/Civil 3D).

## Qué sabe hacer el visor

| Función | Detalle |
|---|---|
| GeoTIFF directo de Drive | ortomosaicos y MDT por ventanas (Range requests), reproyección automática |
| MDT | sombreado en vivo + **cota real al clic** + vista **3D** (terreno global) |
| Vectores | GeoJSON, KML, **KMZ** y **DXF** desde Drive, con etiquetas |
| **Comparar ⇔** | swipe con divisor arrastrable entre dos capas/fechas |
| Superponer archivos | el cliente arrastra un DXF/KML/KMZ/GeoJSON propio y se dibuja al vuelo |
| Coordenadas | POSGAR 2007 (faja configurable) + WGS84 en vivo; popup con E/N y cota |
| Bases | Satélite (Esri) / Topográfico / Calles |
| Descargas | lo no visualizable queda listado con link directo a Drive |

## config.json — esquema

```jsonc
{
  "cliente": "FRONTERA SA",
  "proyecto": "San Expedito",
  "crs": 5344,                    // EPSG POSGAR 2007: 5343=F1 … 5349=F7 (San Juan=5344)
  "centro": [-69.65, -30.25],     // opcional: si no, encuadra al primer ráster
  "zoom": 12,
  "driveApiKey": "",              // opcional: sobreescribe la global
  "carpetasDrive": [              // el visor descubre el contenido solo
    { "id": "1IGII_Wi8-z966D--8l_mcxU5ldrPIYC6", "fecha": "2026-04" }
  ],
  "capas": [                      // y/o capas declaradas a mano
    { "id": "orto-abr", "nombre": "Ortomosaico Abr 2026", "tipo": "geotiff",
      "driveId": "1PGvJCQuBWCFOWkiq2X_b_nPM7BfYwB5U", "fecha": "2026-04" },
    { "id": "mdt-abr", "nombre": "MDS Abr 2026", "tipo": "geotiff-dem",
      "driveId": "1oNThiHZJb56rWeZN4u_c4KKVLQeVSwFW", "fecha": "2026-04" }
  ]
}
```

Tipos: `geotiff` · `geotiff-dem` · `geojson` · `kml` · `kmz` · `dxf` ·
`xyz` (teselas) · `dem` (teselas raster-dem) · `imagen`.
Toda capa acepta `driveId` (Drive) o `url` (relativa al token o absoluta).

**Campaña nueva** = agregar la carpeta nueva a `carpetasDrive` con su `fecha`
(o el par de `driveId` nuevos). El botón **Comparar** permite el antes/después.

### Elegir tokens

Slug + sufijo aleatorio, ej. `fron7era-sx`, `lomanegra-k3p9`:
`python -c "import secrets;print(secrets.token_urlsafe(6).lower())"`

## Demo local

```bat
node tools\serve.js
→ http://localhost:8125/?c=demo
```

El proyecto `demo` incluye dos GeoTIFF chicos reales (orto RGB + MDT float32 en
EPSG:5344) que ejercitan el mismo lector que los archivos de Drive, más un CAD.

## Publicación

Repo GitHub → Settings → Pages → Deploy from branch → `main` / root.
`.nojekyll` ya está. La clave de API queda expuesta en el repo: por eso se
restringe por referrer y solo a la Drive API (solo lectura de lo compartido).

## Hoja de ruta

- **Fase 1 (esto)**: visor con marca DAMS + lectura directa de Drive + tokens.
- **Fase 2 — login real**: Cloudflare Access (gratis ≤50 usuarios) o Worker con
  usuarios/contraseña; los tokens pasan a ser cuentas por cliente.
- **Fase 3**: medición de distancias/áreas, perfiles de elevación, marca de
  agua por cliente.

## Plan B — pipeline de teselas (opcional)

Si algún entregable enorme sin pirámides resulta lento desde Drive,
`tools/procesar_entregable.py` (GDAL/OSGeo4W) lo convierte una vez a teselas
XYZ y GeoJSON para servir desde el repo o Cloudflare R2. No es el camino
principal; queda como alternativa documentada.
