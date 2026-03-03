# PTGui och Linux-landskapet

Researchdatum: 2026-03-03

Kallor:

- PTGui: https://www.ptgui.com/
- PTGui features: https://www.ptgui.com/features.html
- PTGui what's new: https://www.ptgui.com/whatsnew.html
- Hugin: https://hugin.sourceforge.io/
- Xpano: https://www.xpano.com/
- OpenPano: https://github.com/ppwwyyxx/OpenPano

Obs:
Flera slutsatser nedan ar inferenser utifran respektive produkts offentliga funktionsbeskrivning och positionering, inte interna tekniska specifikationer.

## PTGui: funktioner att granska

Baserat pa PTGuis startsida, features-sida och deras uppdateringshistorik ser produktkarnan ut att vara:

### 1. Automatisk stitchning med manuell kontroll

PTGui verkar kombinera automatisk bildalignering med verktyg for att sjalv justera kontrollpunkter, geometri, horisont och beskarning. Det ar centralt: inte bara "auto stitch", utan en arbetsyta for att radda svara bildserier.

Implikation for PanoStitch:

- automatisk feature matching maste kunna overridas
- UI:t behover en tydlig "advanced correction"-vy

### 2. Lins- och kameramodellering

PTGui positionerar sig som starkt pa vidvinkel, fisheye och komplexa linsfall. Det antyder robust optimering av projektionsmodell, distortion och viewpoint-relaterade fel.

Implikation for PanoStitch:

- stark metadatahantering ar inte tillrackligt i sig
- losaren behover fungera aven nar EXIF ar ofullstandig eller fel

### 3. Projektioner och panoramaformat

PTGui ar byggt for flera panoramaformat, inte bara ett plant slutresultat. Equirectangular, cylindrisk och andra projektioner ar en del av verktygets identitet.

Implikation for PanoStitch:

- projektionsval maste vara ett forstaklassigt koncept
- preview bor kunna vaxla mellan projektionslagen snabbt

### 4. Maskning, patching och lokal korrigering

PTGui har lagt tydlig vikt vid maskning och senare patch-baserade korrektioner. Det flyttar produkten fran ren stitchmotor till verkligt produktionsverktyg.

Implikation for PanoStitch:

- maskning bor in i MVP eller mycket tidigt efter MVP
- patching kan skjutas till fas 2 men ar strategiskt viktigt

### 5. HDR, exposure fusion och blending

PTGui verkar inte se stitching som bara geometri; tonmappning och blandning ar en del av helheten. Det gor att anvandaren kan ga fran bildserie till leverans utan separat kedja av verktyg.

Implikation for PanoStitch:

- blending-kvalitet ar en produktfraga, inte bara en implementationdetalj
- HDR/exposure fusion ar sannolikt en viktig fas-2-funktion

### 6. Batch och templates

PTGui marknadsfor automation och batcharbete, vilket ar viktigt for professionella jobb och aterkommande arbetsfloden.

Implikation for PanoStitch:

- en ko-baserad exportmodell bor planeras tidigt
- projektmallar ar ett tydligt differentieringsomrade mot enklare Linux-verktyg

### 7. Stora panoramor och professionell output

PTGui verkar optimera for stora jobb, hog upplosning och fler leveransformat. Det gor produkten attraktiv for 360, print och virtuella turer.

Implikation for PanoStitch:

- minnesmodell och bakgrundsrendering maste tas pa allvar
- tile/gigapixel-export ar inte MVP men bor finnas i arkitekturen

## Prioriterad funktionslista for PanoStitch

Om malet ar "PTGui-liknande, men Linux-forst", ser prioritetsordningen ut sa har:

### MVP

- import, projekt och bildgruppering
- automatisk matchning och initial stitch
- manuell kontrollpunktseditor
- projektionsval och live preview
- crop, horisont och enkel maskning
- batchexport

### Direkt efter MVP

- HDR/exposure fusion
- template-batchjobb
- viewpoint correction och svarare linsfall
- 360/equirectangular preview

### Senare

- patch tool
- gigapixel/tiled export
- virtuella turer eller viewer-paket

## Liknande Linux-projekt

### Hugin

Webb: https://hugin.sourceforge.io/

Position:
Det tydligaste fria Linux-alternativet och den mest direkta referenspunkten.

Styrkor:

- mogen och valkand panoramapipeline
- stark manuell kontroll
- byggt kring panoramabegrepp som kontrollpunkter, optimering och projektioner
- narliggande verktygskedja med Enblend/Enfuse

Svagheter:

- upplevs ofta som mer tekniskt och mindre modernt i UX
- har en brantare inlarningstroskel for nya anvandare
- batch- och preview-upplevelsen ar inte det tydligaste saljargumentet

PanoStitch-lardeom:

- konkurrera inte med Hugin pa "fler dialogrutor"
- konkurrera pa tydlighet, iterationstid och arbetsflode

### Xpano

Webb: https://www.xpano.com/

Position:
Ett enklare, mer produktifierat panoramaalternativ som ocksa riktar sig mot Linux.

Styrkor:

- mer konsument-/desktoppolerad positionering
- tydligt fokus pa snabb stitching och bildforbattring
- lagre troskel an Hugin

Svagheter:

- ser ut att ligga narmare "easy workflow" an "PTGui power-user workflow"
- mindre tydligt ekosystem kring avancerad manuell korrektion

PanoStitch-lardeom:

- enkel onboarding ar viktig
- men produkten bor ha djup nog for att inte fastna som "bara enklare Hugin"

### OpenPano

Webb: https://github.com/ppwwyyxx/OpenPano

Position:
Ett oppet, automatiskt panoramastitchningsprojekt snarare an ett fullstandigt desktopverktyg.

Styrkor:

- visar att det finns oppna byggblock for automatisk stitching
- intressant som referens for pipeline och algoritmstruktur

Svagheter:

- inte en full PTGui-konkurrent pa produktniva
- begransad som slutanvandarapp
- verkar mer forsknings-/ingenjorsnara an produktifierad

PanoStitch-lardeom:

- den verkliga utmaningen ar inte bara stitchingalgoritmen
- det ar produktlagret: preview, korrektion, batch, export och tillit

## Marknadsgap pa Linux

Den tydligaste luckan verkar vara:

- mer kraftfullt och modernt an Xpano-liknande "snabbverktyg"
- enklare och mer sammanhallet an Hugin
- mer produktorienterat an utvecklarprojekt som OpenPano

Kort sagt:

Linux verkar redan ha verktyg for "fri och kraftfull", och verktyg for "enklare stitching", men mindre tydligt ett verktyg som kombinerar:

- premiumkansla
- snabb preview
- robust manuell korrektion
- professionell batch och export

Det ar den mest intressanta nischen for `PanoStitch`.
