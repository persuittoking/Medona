# Data sources

All patient data in OnaRadar is **synthetic** (`backend/ml/generate_synthetic.py`, `backend/app/seed.py`).
Names, PINFL, phone numbers and home points do not belong to real people.

## Mahalla boundaries (`backend/seed/mahallas/*.geojson`)

Built by `backend/seed/fetch_mahallas.py` (re-runnable):

1. First it queries OpenStreetMap (Overpass API) for `boundary=administrative` relations at
   admin_level 9–11 around each demo neighbourhood. On 2026-11-17 **Farg'ona shahri has real mahalla
   boundaries in OSM (admin_level 10)** — we use one as-is. **Nukus and Chilonzor had none.**
2. Where no official boundary exists, it builds a **demo boundary that follows real streets**: it downloads the OSM road network
   (primary … residential) around a real neighbourhood, cuts it into street blocks (shapely `polygonize`)
   and merges the blocks closest to the neighbourhood centre into one polygon (~0.55 km²).

| File | Mahalla (demo name) | City / district | Status | Source |
|---|---|---|---|---|
| `nukus.geojson` | Navbahor MFY | Nukus shahri | **demo chegara** | OSM street blocks (road data © OpenStreetMap contributors, ODbL) |
| `chilonzor.geojson` | Qatortol MFY | Chilonzor tumani, Toshkent | **demo chegara** | OSM street blocks incl. service roads near Qatortol / Bunyodkor streets (road data © OpenStreetMap contributors, ODbL) |
| `fargona.geojson` | **Maʻrifat mahallasi** | Farg'ona shahri | **real boundary** | OpenStreetMap relation 20577024 (admin_level 10), © OpenStreetMap contributors, ODbL |
| `samarqand_registon.geojson` | Registon MFY | Samarqand shahri | **demo chegara** | OSM street blocks (adjacent partition of Samarqand road network, © OpenStreetMap contributors, ODbL) |
| `samarqand_siyob.geojson` | Siyob MFY | Samarqand shahri | **demo chegara** | OSM street blocks (adjacent partition of Samarqand road network, © OpenStreetMap contributors, ODbL) |
| `samarqand_bogishamol.geojson` | Bog'ishamol MFY | Samarqand shahri | **demo chegara** | OSM street blocks (adjacent partition of Samarqand road network, © OpenStreetMap contributors, ODbL) |

"demo chegara" = the outline follows real streets but is **not** the official mahalla boundary, and the
mahalla names (Navbahor MFY, Qatortol MFY) are illustrative. Raw OSM street downloads are cached in
`backend/seed/osm_cache/` so the boundaries rebuild offline. Replace with official boundaries (Kadastr / hokimiyat) before real use.

## Map tiles
- Satellite: Esri World Imagery — "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community".
- Streets: © OpenStreetMap contributors.

## Region / district coordinates
`backend/app/geo.py`: approximate district centre points (for circles on the admin map). No region or district
boundary polygons are used.
