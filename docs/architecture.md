# Arkitektur

Datum: 2026-03-03

## Malsattning

Forsta releasen ska vara en desktop-app som batch-korrigerar fisheye-bilder tagna fran samma vinkel. Stitching kommer senare, men samma domanmodell ska kunna ateranvandas da.

## Varfor Python + Qt

Valet just nu ar `Python + PySide6` eftersom det ger:

- snabbast vag till fungerande Linux-desktop-app
- bra Windows-port utan separat UI-stack
- enkel integration med `LibRaw`, `Lensfun`, `OpenCV` och senare valfri `libvips`
- lag utvecklingsfriktion i tidigt skede

Detta ar ett medvetet pragmatiskt val for fas 1. Den CPU-tunga geometrikarnan kan senare flyttas till Rust eller C++ om behov uppstar.

## Stegbaserat UI

Appen byggs runt fyra tydliga steg:

1. `Import`
2. `Adjust`
3. `Preview`
4. `Export`

Varje steg motsvarar ett eget UI-omrade och en egen liten domanmodell:

- `Import`: lasa in filer, metadata, kamera, lins, gemensamma serier
- `Adjust`: pitch, roll, yaw, projektion, zoom, vertical shift
- `Preview`: rendera vald bild med aktuell preset
- `Export`: batchjobb, format, filnamnssuffix, metadata-policy

## Kodskelett

Kodbasen ar uppdelad sa har:

- `src/panostitch/domain`
  - rena datamodeller for kamera, lins, preset, export och jobb
- `src/panostitch/core`
  - fisheye-matematik, batchplanering, presetlagring
- `src/panostitch/io`
  - inbyggda profiler och senare metadata/exif/raw-adaptrar
- `src/panostitch/ui`
  - PySide6-fonster, temning, stegvis layout

## Lokal lagring

For att undvika att fylla OS-partitionen ska lokal utvecklingsmiljo och tunga temporara filer ligga utanfor projektmappen nar mojligt.

Standardrot om den finns:

- `/run/media/stolpee/localprog/panostitch`

Dar laggs:

- `venvs/default`
- `pip-cache`
- `tmp`
- `wheels`

## Bildpipeline for fas 1

Fas 1 ar medvetet smal:

1. lasa in en bild eller en serie bilder
2. tilldela en linsprofil
3. satta pitch/roll/yaw och output-projektion
4. forhandsgranska en bild
5. batch-exportera samma preset over flera bilder

Sjalva bildmatematiken ar uppbyggd runt:

- en virtuell kamerariktning
- en vald output-projektion
- en fisheye-till-kallbild-mappning

Det gor att samma modell senare kan anvandas for panorama-preview och warp-steg i stitching.

## Projektioner i fas 1

Forsta implementationen bor fokusera pa:

- `cylindrical`
- `rectilinear`

`Cylindrical` ar sannolikt bast som forstahandsval for breda fisheye-korrigeringar nar man vill raka upp nederkant/horisont utan att straffa bildkanterna for hardt.

## Exportpolicy

Rasterformat kan normalt bevaras:

- `JPEG -> JPEG`
- `TIFF -> TIFF`
- `PNG -> PNG`

RAW ar annorlunda:

- `ARW`, `CR3`, `NEF`, `RAF` och liknande ar sensorformat
- efter geometrisk manipulation ar bilden inte langre samma ra-signal

Darfor ska fas 1 exportera RAW-ingang till:

- `linear DNG`
- `TIFF`
- `JPEG`

## Stitching senare

Nar fisheye-korrigeringen fungerar stabilt kan nasta lager byggas pa:

- feature matching
- kontrollpunkter
- global optimering
- multi-image preview
- batchstitching

Det ar avsiktligt senarelagt tills grundproblemet med linsgeometri och batchflode fungerar bra.
