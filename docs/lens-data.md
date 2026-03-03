# Linsdata och kalibrering

Datum: 2026-03-03

## Utgangspunkt

Appen ska helst kunna fylla i kamera- och linsdata automatiskt. Men for fisheye-korrigering ar det viktigt att inte bygga hela fas 1 pa att tredjepartsprofiler redan finns.

## Datakallor

Planerad ordning for linsdata:

1. EXIF / metadata ur filen
2. Lensfun-profil om den finns
3. inbyggd PanoStitch-profil for kanda kombinationer
4. manuell anvandarprofil / preset

## Din lins

Relevant kombination just nu:

- kamera: Sony A7R III
- objektiv: Sigma 15mm F1.4 DG DN Diagonal Fisheye | Art, Sony E

Officiell Sigma-produktinformation visar detta som en fullformatslins for Sony E. Samtidigt visar Lensfuns offentliga linslista genererad 2026-02-28 inte denna modell, utan bland annat den aldre `Sigma 15mm f/2.8 EX DG Diagonal Fisheye`.

Det betyder:

- Lensfun ar nyttigt, men inte tillrackligt for denna forsta implementation
- vi ska skeppa med en manuell startprofil for just denna lins
- anvandaren ska kunna fintrimma preset och batcha utan att vanta pa extern databassupport

## Forsta strategi for Sigma 15mm

Vi utgar fran:

- sensorformat: fullformat
- linstyp: diagonal fisheye
- brannvidd: 15mm
- output-projektion: `cylindrical` som startlage

Det som inte ska hardkodas som "sanningen":

- exakt fisheye-mappning utan kalibrering
- exakta distortionskoefficienter
- slutlig crop/zoom-niva

Istallet far vi:

- ett rimligt startvarde
- en justerbar preset
- lokal lagring av anvandarens egen kalibrering

## Profilformat

PanoStitch ska lagra linsprofiler och presets som JSON. Det gor att:

- samma korrigering kan batchas over flera bilder
- profiler kan versionshanteras
- egna profiler kan delas utan proprietart format

## Senare forbattringar

Nar fas 1 fungerar kan vi lagga till:

- automatisk sokning mot Lensfun
- import av egna kalibreringsprofiler
- enkel intern kalibreringsguide med testbild och raklinjer
- objektivspecificerade defaults for fler tillverkare
