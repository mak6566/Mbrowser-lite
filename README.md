# Mbrowser Lite

Mbrowser Lite je extrémne rýchly a pamäťovo efektívny webový prehliadač poháňaný špecializovaným jadrom m-engine V1 [cite: 1]. Jeho primárnym cieľom je poskytnúť špičkový výkon, vysokú odozvu a stabilitu s minimálnymi hardvérovými nárokmi [cite: 1].

## Systémové požiadavky a Ciele (KPI)
* **Hardvérové minimum:** Plynulý beh vyžaduje zariadenie s aspoň 500 MB RAM [cite: 1].
* **Spotreba po štarte (Cold Start):** Prehliadač je optimalizovaný tak, aby pri štarte zaberal len 25 MB RAM [cite: 1].
* **Bežné prezeranie:** Priemerná spotreba pamäte pri vykresľovaní bežných webových stránok nepresahuje 50 MB RAM [cite: 1].
* **Cieľové platformy:** Embedded zariadenia, staršie mobilné čipsety a limitované prostredia ako Termux [cite: 1].

## Architektúra a Technológie
Jadro prehliadača je kompletne vyvíjané v jazyku Rust, čo zabezpečuje absolútnu pamäťovú bezpečnosť a eliminuje potrebu použitia Garbage Collectora, čím sa šetria systémové zdroje [cite: 1].

* **JavaScript Runtime:** Implementuje odľahčený QuickJS (bez JIT kompilátora), ktorý spotrebúva minimum pamäte (~1 MB RAM), pričom API volania sú riešené priamo cez natívne Rust bindings [cite: 1].
* **Grafická vrstva:** Hardvérová akcelerácia je postavená na knižnici wgpu s viacfázovým spracovaním (Render Graph, Tile Caching) pre priamu integráciu s Vulkan, Metal a DirectX 12 [cite: 1].
* **CSS a Layout:** Extrémnu rýchlosť parsovania štýlov zabezpečuje lightningcss a pre výpočet komplexnej geometrie (Flexbox, Grid) slúži vysoko optimalizovaný layout engine Taffy [cite: 1].
* **Textový subsystém:** Integrácia knižnice cosmic-text pre moderný text shaping, font fallback a priame vykresľovanie na GPU [cite: 1].
* **Dátový model DOM:** Využíva inovatívny Compact Flat Arena DOM založený na princípe Structure of Arrays (SoA), kde sú 64-bitové pointery nahradené 32-bitovými indexmi [cite: 1].

## Kľúčové optimalizácie
* **Adaptívny chod:** Pri štarte systém automaticky deteguje dostupné hardvérové prostriedky a alokuje jeden zo štyroch profilov (od Embedded po High) pre optimálne prispôsobenie výkonu a cache mechanizmov [cite: 1].
* **Tiered Allocator System:** Mbrowser Lite obchádza štandardné systémové alokátory. Využíva tri dedikované úrovne (Slab, Arena, Direct mmap), vďaka čomu minimalizuje volania `malloc` a `free` v renderovacej slučke a úplne odstraňuje pamäťovú fragmentáciu [cite: 1].
* **Multi-level CSS Matching:** Rýchle spracovanie kaskády využíva štruktúru Selector Trie spolu s inline Bloom filtrami, ktoré umožňujú validáciu prítomnosti tried v čase O(1) [cite: 1].
* **Asynchrónne dekódovanie médií (Inline Resizing):** Pri dekódovaní obrázkov sa vykonáva streamovaný downscaling pomocou SIMD inštrukcií, takže obrázok sa načíta do RAM priamo v cieľovom rozlíšení, čím sa redukuje spotreba pamäte z desiatok megabajtov na zlomok tejto hodnoty [cite: 1].

## Filozofia projektu
Cieľom Mbrowser Lite nie je súťažiť s masívnymi jadrami v hrubom výpočtovom výkone na najdrahšom hardvéri, ale dosiahnuť bezkonkurenčnú pamäťovú a energetickú efektivitu [cite: 1]. Výsledkom je najlepší a najrýchlejší prehliadač pre nasadenie tam, kde tradičné riešenia zlyhávajú na nedostatok zdrojov.
