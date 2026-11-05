# lib — kaloriméteres modellek (3 feladat × 3 koordináta-rendszer)

| feladat | modell | kimenet |
|---|---|---|
| `segmentation` | FractionResUNet3D + hit-kódoló | voxelenkénti A energiafrakció a kombinált A+B eseményben |
| `angle` | AngleCNN3D | részecskénkénti beesési szög θ |
| `energy` | ParticleCNNTransformer + hit-kódoló | részecskénkénti impulzus (GeV) |

## Koordináta-rendszerek (`common/coords.py`)

- `absolute`: x, y, z.
- `trans`: csak eltolás; a zápor kezdőpontja az origóba kerül.
- `local`: eltolás + forgatás; z' a beesési irány mentén fut, ehhez a valódi szög kell.

Mind a 9 (feladat, koordináta) párhoz tartozik lepárlás: szurrogát döntési fa és PySR-képlet
fizikai egységekben (`distill/`). A bemenet 32³-as voxelrács (±3σ ablak a modell saját
koordinátáiban). Ez abszolútban kb. 250 × 250 × 53 mm-es voxel, transzlált és lokális
keretben kb. 45 × 45 × 55 mm-es, ami nagyjából a cellamérettel egyezik meg.

## Architektúra röviden

- **Szélesség és paraméterszám:**
  - szegmentáció: 32/80/160 csatorna; transzlált és lokális keretben részecske-lekérdezéses
    fejjel, 5,90 M paraméter, abszolútban anélkül, 5,66 M;
  - szög: 40/80/160 csatorna, 4,72 M;
  - energia: CNN 56 (BatchNorm, az EMA-súlyokhoz újraszámolt statisztikával), transformer
    d = 288, skálánként 4³ token, 5,02 M.
  A rácsméret a checkpointban tárolódik.
- **Részecske-lekérdezéses fej (szegmentáció, `model.ParticleQueryHead`, transzlált és lokális
  keretben):**
  - két felcserélhető lekérdezés olvassa keresztfigyelemmel a háló két belső, fél és negyed
    felbontású jellemzőtérképét;
  - a skalárszorzatuk a voxelbeágyazással egy kis kapun át adódik a U-Net voxel-logitjához;
  - a voxel sorsáról így a két zápor globális képe alapján dönt (Mask2Former, Slot Attention,
    deep clustering).
- **Időcsatorna (szög):** a részecske első voxeléhez mért idő; a zápor a beesés irányában
  halad, így az idő iránya a szög második hordozója.
- **Hit-kódoló:** `common/layers.py: VoxelHitEncoder`, PointNet/PVCNN-elvű. Voxelenként a
  legnagyobb energiájú hiteket egy közös MLP kódolja, majd átlag- és max-pooling következik.
  A slotok száma abszolútban 16, transzlált és lokális keretben 4. 32³-on egy voxelre
  átlagosan 5,1, illetve 1,4 hit jut; a 99. percentilis 31, illetve 3.
  - szegmentáció: energia, xy-sugár a voxelen belül, z-eltolás;
  - energia: ugyanezek, plusz a zápor első hitjéhez mért idő (software compensation).
- **Szimmetria:** az augmentáció és a TTA a koordináta-rendszer valódi szimmetriáit használja.
  Abszolútban és transzlált keretben ez D4, lokálisban csak az y' tükrözés.
- **Adatút:** az adat a GPU-n van, DataLoader nincs. A foglalt voxelek eseményenként
  CSR-sorokban állnak (`common/voxels.py: SparseVoxels`, szegmentációnál `VoxelTable`). A
  sűrű 32³-as bemenet csak batchenként, a GPU-n épül fel (`LazyBatch`).
- **Magyarázatok:**
  - Grad-CAM;
  - Shap-CAM a szegmentációnál egzakt, a szögmodellnél a foglalt voxeleken fut.
    Az energiamodellnél 4×4×4-es voxelblokkok a játékosok, és egy blokk φ-je a voxelek
    energiája szerint oszlik szét; a φ-k összege így továbbra is p − p_alap.
- **Split:** csoportos, szivárgásmentes (`common/splits.py`); egyetlen forrászápor sem kerülhet
  egyszerre a tanító és a validációs halmazba.
- A döntések háttere: `docs/literature.md`.

## Eredmények (2026-09-24)

Beállítás:
- 32³-as bemenet, 8 epoch, egy H200 GPU;
- csoportos, szivárgásmentes validáció: 4 065 kombinált esemény, azaz 8 130 részecske;
- a részletes táblák és ábrák: `scripts/vizualizations/summary.md` és `evaluation/`.

### Pontosság (validáció)

| modell | paraméter | fő metrika | TTA-val | további |
|---|---|---|---|---|
| segmentation_absolute | 5 661 932 | E-súlyozott MAE 0,1263 | 0,1273 | átfedés-mag MAE 0,248 |
| segmentation_trans | 5 900 429 | E-súlyozott MAE 0,2135 | 0,2120 | átfedés-mag MAE 0,233 |
| segmentation_local | 5 900 429 | E-súlyozott MAE 0,2277 | 0,2288 | átfedés-mag MAE 0,233 |
| angle_absolute | 4 722 922 | MAE 1,96 mrad | 1,93 mrad | RMSE 6,8 mrad, bias −0,1 mrad |
| angle_trans | 4 722 922 | MAE 63,6 mrad | 62,7 mrad | RMSE 92,5 mrad, bias +11,9 mrad |
| angle_local | 4 722 922 | MAE 16,7 mrad | 16,3 mrad | RMSE 34,1 mrad, bias +0,6 mrad |
| energy_absolute | 5 022 743 | MAE 1,177 GeV | 1,145 GeV | RMSE 2,02 GeV, R² 0,879 |
| energy_trans | 5 022 743 | MAE 1,130 GeV | 1,113 GeV | RMSE 2,11 GeV, R² 0,867 |
| energy_local | 5 022 743 | MAE 1,074 GeV | 1,065 GeV | RMSE 1,89 GeV, R² 0,893 |

### Hitszintű validáció átfedési binenként

| modell | összes | 0 % | 10 % | 20 % | 30 % | 40–100 % |
|---|---|---|---|---|---|---|
| segmentation_absolute (E-MAE) | 0,127 | 0,014 | 0,101 | 0,285 | 0,213 | 0,163 |
| segmentation_trans (E-MAE) | 0,214 | 0,154 | 0,222 | 0,275 | 0,252 | 0,207 |
| segmentation_local (E-MAE) | 0,229 | 0,197 | 0,227 | 0,278 | 0,238 | 0,183 |
| angle_absolute (mrad) | 1,93 | 2,28 | 1,98 | 1,35 | 1,91 | 2,40 |
| angle_trans (mrad) | 63,2 | 63,7 | 65,1 | 50,9 | 64,6 | 118,9 |
| angle_local (mrad) | 16,0 | 18,5 | 13,2 | 8,1 | 29,9 | 52,6 |
| energy_absolute (GeV) | 1,18 | 1,21 | 1,03 | 1,18 | 1,61 | 1,74 |
| energy_trans (GeV) | 1,14 | 1,12 | 0,94 | 1,08 | 1,87 | 2,37 |
| energy_local (GeV) | 1,08 | 1,09 | 0,93 | 1,05 | 1,63 | 1,74 |
| események | 4 065 | 1 297 | 1 384 | 1 002 | 204 | 167 |

### Lepárlás (szurrogát fa, mélység 4, és PySR)

A fa R²-ét a validációs eseményeken mérjük a háló saját predikcióihoz. A „fa az igazságra”
ugyanez a fa közvetlenül a valódi értékre illesztve, ez a fa kapacitásának korlátja.

| modell | fa R² a hálóhoz | fa R² az igazságra | legfontosabb jellemzők | PySR-képlet (fizikai egységben) | PySR R² |
|---|---|---|---|---|---|
| segmentation_absolute | 0,161 | 0,213 | r a súlyponttól, voxelszám, z | 0,047·√voxelszám | ≈ 0 |
| segmentation_trans | 0,078 | 0,741 | szórás, szomszéd-E, mélység | (nem ad érdemi képletet) | < 0 |
| segmentation_local | 0,092 | 0,415 | z, E-hányad, szomszédok | (nem ad érdemi képletet) | 0,08 |
| angle_absolute | 0,991 | 0,990 | súlypont θ | θ ≈ 1,008 · θ_súlypont | 0,996 |
| angle_trans | 0,303 | 0,171 | rms_z, rms_r, súlypont θ | — | 0,06 |
| angle_local | 0,133 | 0,122 | rms_z, első réteg, rms_r | — | ≈ 0 |
| energy_absolute | 0,902 | 0,821 | E_sum, hitszám, súlypont r | p ≈ 29,5 · E_sum + 0,0024 · r | 0,81 |
| energy_trans | 0,832 | 0,730 | E_sum, hitszám, rms_r | p ≈ 26,1 · √E_sum | 0,80 |
| energy_local | 0,814 | 0,728 | E_sum, hitszám, rms_z | p ≈ 26,2 · √E_sum | 0,77 |

### Sebesség (H200, csak a háló előre-futása, vegyes pontosság, TTA nélkül)

| modell | feldolgozás |
|---|---|
| szegmentáció | ~1 050 kombinált esemény/s (a lekérdezés-fej ~3 %-ot lassít) |
| szög | ~980 részecske/s |
| energia | ~6 800 részecske/s |

A TTA ezt abszolút és transzlált keretben 8-cal, lokálisban 2-vel osztja. A Grad-CAM és a Shap-CAM
lassabb: a szegmentáció ~30, a szög ~20–40, az energia ~30 esemény/s-mal fut egyedül a GPU-n.

### Értelmezés és korlátok

- **Bemenet:** csak a szegmentáció kapja a kombinált (A+B) eseményt. A szög- és az
  energiamodell részecskénként külön kapja a hiteket, a valódi címke (`particle_origin`) szerint
  szétválasztva; a mindkét részecske által eltalált cellák energiáját a forrásfájl alapján
  bontjuk A- és B-részre (`common/shared_hits.py`). A bemenetükben tehát nincs átfedés: a
  pontosságuk tökéletes szegmentációt feltételez, egy szegmentáció → szög/energia láncban a
  szegmentáció hibája ehhez hozzáadódna. Az átfedési binek közti eltérésük a binek
  összetételéből jön.
- **Energia:** a 30 %-os és a 40–100 %-os átfedési binben
  a részecskék kis impulzusúak (átlag 3,3 GeV), és szinte semmit nem raknak le (~8 MeV). A nagyobb
  hiba itt információhiány, nem modellhiba.
- **Szög:**
  - Abszolút keretben 1,9 mrad. A háló lényegében a súlypont polárszögét finomítja (a
    PySR-képlet szerint θ ≈ 1,008 · θ_súlypont).
  - A lokális keret a valódi beesési szöggel forgat, ezért a ~16 mrad nem valódi mérési
    pontosság: a szög a rétegek dőléséből kiolvasható.
  - A transzlált keret ~63 mrad: a becsapódási pont nélkül csak a zápor alakjára és idejére
    támaszkodhat, ez fizikai korlát.
- **Szegmentáció:**
  - A háló bizonytalankodik. Az energiasúlyozott |2f − 1| a predikcióban 0,69 / 0,74 / 0,74
    (abszolút / transzlált / lokális), az igazságban 0,86 / 0,95 / 0,94. A 0,3–0,7 közti sávba a
    háló az energia 31 / 19 / 18 %-át teszi, az igazság csak 11 / 4 / 4 %-át.
  - A transzlált és a lokális keret részecskénként definiált, vagyis a szegmentálandó címkét
    használja. Ezért a nem átfedő eseményeken is 0,15–0,20 a hiba. Javaslat: eseményszintű keret
    (lásd `docs/literature.md`, „Feltárt gondok”).
- **Lepárlás:** a szög (abszolút) és az energia döntéseit néhány fizikai mennyiség jól leírja (fa
  R² 0,81–0,99); a szegmentáció voxelenkénti döntéseit nem (R² 0,08–0,16).

## Új részecske-adathalmazok és eredmények

Az elektron- és pion-adathalmazokat a generátor új, explicit
`source_event_A/source_event_B` oszlopaival újrageneráltuk. Mindhárom részecskéhez
20 000 kombinált esemény, mindhárom koordinátarendszer és mind a 9 modell elkészült.
Az eredmények csoportos, szivárgásmentes validációból származnak (4 000 validációs
kombinált esemény), a lepárlás pedig mélység-4 döntési fával és PySR szimbolikus
regresszióval futott.

| részecske | kombinált CSV sor | modell-output CSV | checkpointok |
|---|---:|---|---:|
| müon | 2 000 000 körül | `regression-muon/muon_hits_with_model_outputs.csv` | 9 |
| elektron | 5 440 515 | `regression-electron/electron_hits_with_model_outputs.csv` | 9 |
| pion | 21 278 865 | `regression-pion/pion_hits_with_model_outputs.csv` | 9 |

Az alábbi táblákban a validációs főmetrika és a döntési fa hálópredikcióhoz mért
fidelity R²-e szerepel. A szegmentáció metrikája energiasúlyozott MAE, a szögé
mrad, az energiáé GeV.

| részecske | modell | abszolút | transzlált | lokális |
|---|---|---:|---:|---:|
| müon | segmentation (MAE / tree R²) | 0,1086 / 0,6315 | 0,1212 / 0,4716 | 0,1047 / 0,6643 |
| müon | angle (MAE mrad / R²; tree R²) | 0,458 / 1,0000; 0,9953 | 9,667 / 0,9840; 0,9723 | 1,851 / 0,9953; 0,7070 |
| müon | energy (MAE GeV / R²; tree R²) | 4,621 / 0,0176; 0,7292 | 4,599 / 0,0276; 0,6235 | 3,511 / 0,3390; 0,2183 |
| elektron | segmentation (MAE / tree R²) | 0,1026 / 0,4778 | 0,0855 / 0,3707 | 0,0893 / 0,3693 |
| elektron | angle (MAE mrad / R²; tree R²) | 0,421 / 1,0000; 0,9957 | 21,617 / 0,9585; 0,7665 | 0,892 / 0,9988; 0,3716 |
| elektron | energy (MAE GeV / R²; tree R²) | 0,754 / 0,9354; 0,9247 | 0,671 / 0,9422; 0,9159 | 0,680 / 0,9454; 0,9176 |
| pion | segmentation (MAE / tree R²) | 0,1397 / 0,1730 | 0,1970 / 0,0701 | 0,2266 / 0,0788 |
| pion | angle (MAE mrad / R²; tree R²) | 1,888 / 0,9966; 0,9931 | 52,995 / 0,6969; 0,3836 | 14,078 / 0,9583; 0,1336 |
| pion | energy (MAE GeV / R²; tree R²) | 1,382 / 0,8265; 0,8709 | 1,358 / 0,8240; 0,7855 | 1,299 / 0,8303; 0,7790 |

### Hitszintű és részecskeszintű validáció átfedési binenként

Az értékek sorrendje: összes, 0%, 10%, 20%, 30%, 40--100% overlap bin.
Az alábbi szegmentációs sorok **hitszintű**, eseményenkénti energiával súlyozott
MAE-k. A szög- és energiasorok **részecske/zápor szintű** MAE-k: egy részecske
egy értéket kap, ezért ugyanazt a predikciót nem számoljuk bele külön minden
hitnél. Ez a helyes összehasonlítási egység a három feladat eltérő célja miatt.

| részecske/modell | összes | 0% | 10% | 20% | 30% | 40--100% |
|---|---:|---:|---:|---:|---:|---:|
| müon segmentation absolute | 0,1088 | 0,2374 | 0,1756 | 0,1216 | 0,1155 | 0,1048 |
| müon segmentation trans | 0,1215 | 0,1003 | 0,1433 | 0,1385 | 0,1255 | 0,1211 |
| müon segmentation local | 0,1050 | 0,1616 | 0,1276 | 0,1104 | 0,0857 | 0,1038 |
| müon angle absolute | 0,456 | 0,626 | 0,825 | 0,526 | 0,506 | 0,444 |
| müon angle trans | 9,675 | 15,579 | 22,028 | 14,899 | 9,832 | 9,235 |
| müon angle local | 1,848 | 2,448 | 3,193 | 1,556 | 1,478 | 1,825 |
| müon energy absolute | 4,619 | 4,656 | 4,943 | 4,926 | 4,723 | 4,605 |
| müon energy trans | 4,597 | 4,553 | 4,831 | 4,797 | 4,769 | 4,586 |
| müon energy local | 3,508 | 3,324 | 3,181 | 2,620 | 3,592 | 3,532 |
| elektron segmentation absolute | 0,1024 | 0,2203 | 0,1323 | 0,1126 | 0,1036 | 0,1002 |
| elektron segmentation trans | 0,0856 | 0,0928 | 0,1231 | 0,0857 | 0,0505 | 0,0854 |
| elektron segmentation local | 0,0895 | 0,1903 | 0,1202 | 0,0840 | 0,0822 | 0,0878 |
| elektron angle absolute | 0,420 | 0,609 | 0,766 | 0,481 | 0,497 | 0,410 |
| elektron angle trans | 21,625 | 29,995 | 41,277 | 28,079 | 25,715 | 21,079 |
| elektron angle local | 0,889 | 1,446 | 9,495 | 0,957 | 0,879 | 0,756 |
| elektron energy absolute | 0,750 | 0,745 | 0,829 | 0,670 | 0,639 | 0,751 |
| elektron energy trans | 0,668 | 0,706 | 1,045 | 0,590 | 0,596 | 0,664 |
| elektron energy local | 0,684 | 0,657 | 0,885 | 0,550 | 0,618 | 0,684 |
| pion segmentation absolute | 0,1402 | 0,0220 | 0,1322 | 0,2756 | 0,2096 | 0,1640 |
| pion segmentation trans | 0,1974 | 0,1343 | 0,1909 | 0,2525 | 0,2715 | 0,2582 |
| pion segmentation local | 0,2271 | 0,1861 | 0,2189 | 0,2718 | 0,2711 | 0,2518 |
| pion angle absolute | 1,887 | 2,488 | 1,668 | 1,208 | 2,046 | 2,872 |
| pion angle trans | 53,048 | 55,373 | 56,837 | 49,178 | 43,994 | 47,107 |
| pion angle local | 14,008 | 15,970 | 12,556 | 8,628 | 20,723 | 31,713 |
| pion energy absolute | 1,376 | 1,292 | 0,984 | 1,101 | 2,621 | 4,816 |
| pion energy trans | 1,352 | 1,297 | 0,942 | 1,048 | 2,625 | 4,838 |
| pion energy local | 1,293 | 1,227 | 0,895 | 0,997 | 2,511 | 4,883 |

Így a többi részecskére is szerepel a protonoshoz hasonló, valódi hitszintű
overlap-bontás a szegmentációhoz; a szög- és energiafeladatnál a fizikailag
értelmes részecskeszintű bontás szerepel.

### PySR-képletek

Ezek a PySR által választott, fizikai egységű képletek. A PySR R² a képlet
hűsége a háló saját validációs predikciójához; alacsony értéknél nem szabad
fizikai törvényként értelmezni. A szegmentáció képletei standardizált
voxeljellemzőket használnak.

| részecske | modell | képlet | R² |
|---|---|---|---:|
| müon | segmentation absolute | `0,6973 exp(-2,4411 n_hits²/(n_hits(0,8762-277,6767 E_voxel)+1,9046 n_neighbours+14,4939 r_to_centroid)²)` | 0,590 |
| müon | segmentation trans | `1,274 n_hits exp(-0,5659 n_hits)` | 0,329 |
| müon | segmentation local | `0,847/n_hits` | 0,422 |
| müon | angle absolute | `centroid_theta` | 1,000 |
| müon | angle trans | `0,008772 rms_z(0,3466 sqrt(centroid_theta)-0,2848)+0,599` | 0,954 |
| müon | angle local | `log(exp(1,0252 n_voxels/(n_hits(0,04746 n_hits+3,0133)^(1/4))))²` | 0,661 |
| müon | energy absolute | `61,67 sqrt(E_sum max_hit_frac)+7,114` | 0,653 |
| müon | energy trans | `48,84 E_sum+8,299` | 0,385 |
| müon | energy local | `48,84 E_sum-0,1586 rms_r+11,78` | 0,104 |
| elektron | segmentation absolute | `0,4749 max_hit_frac` | 0,245 |
| elektron | segmentation trans | `0,8134/n_hits` | 0,188 |
| elektron | segmentation local | `0,3453 sqrt(0,6322 n_neighbours+4,138)/n_hits` | 0,264 |
| elektron | angle absolute | `centroid_theta` | 1,000 |
| elektron | angle trans | `exp(-0,0389953 centroid_z/(0,0502829 centroid_r+2,3149))` | 0,689 |
| elektron | angle local | `1,156 sqrt(max_hit_frac)` | 0,141 |
| elektron | energy absolute | `25,97 E_sum+17,19 max_hit_frac` | 0,904 |
| elektron | energy trans | `25,74 E_sum+17,19 max_hit_frac` | 0,893 |
| elektron | energy local | `28,0 E_sum+11,16 centroid_theta` | 0,892 |
| pion | segmentation absolute | `exp(-1,9418/(0,8910 depth_from_first+0,01193 event_n_voxels+6,1700 r_to_centroid²))` | 0,126 |
| pion | segmentation trans | `sqrt((0,7209 exp(17,0997 neighbour_E_frac)-0,3786) exp(-17,0997 neighbour_E_frac-3,1614 sqrt(spread)))` | 0,059 |
| pion | segmentation local | `0,541(147,7 E_voxel_frac+1,616 dist_to_centroid/exp(1,3442 r_to_centroid)^0,5)^0,25` | 0,044 |
| pion | angle absolute | `1,006 centroid_theta` | 0,997 |
| pion | angle trans | `0,25 log(5,3424 centroid_theta+3,1745 early_frac+2,5294)` | 0,235 |
| pion | angle local | `0,6033-0,0009209 rms_z` | −0,024 |
| pion | energy absolute | `25,2 E_sum+6,713e-7 centroid_r²+1,947` | 0,770 |
| pion | energy trans | `23,66 sqrt(E_sum)` | 0,693 |
| pion | energy local | `23,99 sqrt(E_sum)` | 0,686 |

### Szögbecslés: képlet és neurális háló abszolút hibája

Az alábbi MAE-k a valódi beesési szöghöz viszonyított validációs hibák,
mrad-ban. A képlet MAE-je közvetlenül a PySR-képlet és az igaz szög között
mért hiba; a háló MAE-je a neurális háló és az igaz szög közötti hiba.

| részecske | koordinátarendszer | PySR-képlet MAE | neurális háló MAE |
|---|---|---:|---:|
| müon | abszolút | 0,87 mrad | 0,46 mrad |
| müon | transzlált | 24,25 mrad | 9,67 mrad |
| müon | lokális | 74,06 mrad | 1,85 mrad |
| elektron | abszolút | 0,61 mrad | 0,42 mrad |
| elektron | transzlált | 67,84 mrad | 21,62 mrad |
| elektron | lokális | 113,50 mrad | 0,89 mrad |
| pion | abszolút | 5,07 mrad | 1,89 mrad |
| pion | transzlált | 110,50 mrad | 53,00 mrad |
| pion | lokális | 120,99 mrad | 14,08 mrad |

Ez alapján az abszolút koordinátás PySR-képletek a leghasználhatóbbak; a
transzlált és lokális rendszerekben a neurális háló lényegesen pontosabb a
képletnél.

Megjegyzés: az elektron energiaképletei a leghasználhatóbbak (R²=0,892--0,904),
az abszolút szögképletek mindhárom részecskénél erősek. A müon energiája valódi
értékre gyenge (háló R²=0,018 abszolútban), ezért a képlet csak a háló
viselkedésének közelítése. A pion magas overlap binjeiben az energiahiba
2,5--4,9 GeV-re nő.

### Abszolút koordinátás impulzus-hiba 5, 10 és 15 GeV körül

Az alábbi értékek a teljes exportált modell-outputból, részecskénként és
eseményenként egyszer számolva készültek. Az „5 GeV” például a 4--6 GeV
közötti igaz értékeket jelenti; a hiba MAE, a zárójelben a mintaelemszám és
az átlagos előjelzett hiba szerepel. Ez nem csak a validációs subset.

| részecske | 5 GeV MAE | 10 GeV MAE | 15 GeV MAE |
|---|---:|---:|---:|
| müon | 5,525 GeV (n=11 758; bias +5,525) | 1,084 GeV (n=12 132; bias +0,702) | 4,220 GeV (n=12 458; bias −4,220) |
| elektron | 0,596 GeV (n=11 267; bias +0,418) | 0,702 GeV (n=28 901; bias +0,193) | 0,834 GeV (n=36 926; bias +0,081) |
| pion | 1,170 GeV (n=53 113; bias +0,813) | 1,278 GeV (n=83 307; bias +0,442) | 1,384 GeV (n=117 239; bias −0,142) |

### Lepárlási képletek és fő jellemzők

A PySR szimbolikus regresszió mindhárom új részecskére lefutott. A fenti
képlettábla a PySR-formulákat és a hálóhoz mért R²-t tartalmazza; az alábbi
tábla a protonos README-hez hasonlóan a mélység-4 fa R²-ét, a hálóhoz és az
igazsághoz mért hibáját, valamint a legfontosabb jellemzőket adja meg. A fa és
a képlet a háló viselkedésének magyarázata, nem önálló fizikai törvény.

| modell | részecske | fa R² a hálóhoz | fa MAE a hálóhoz | háló MAE az igazsághoz | fa MAE az igazsághoz | legfontosabb jellemzők |
|---|---|---:|---:|---:|---:|---|
| segmentation_absolute | müon | 0,632 | 0,1357 | 0,1955 | 0,1309 | n_hits, n_neighbours, r_to_centroid |
| segmentation_trans | müon | 0,472 | 0,2139 | 0,2129 | 0,1086 | n_hits, E_voxel, depth_from_first |
| segmentation_local | müon | 0,664 | 0,1338 | 0,1297 | 0,0247 | max_hit_frac, E_voxel, r_to_centroid |
| angle_absolute | müon | 0,995 | 0,0086 | 0,00046 | 0,0087 | centroid_theta |
| angle_trans | müon | 0,972 | 0,0179 | 0,00967 | 0,0207 | centroid_theta, rms_z |
| angle_local | müon | 0,707 | 0,0555 | 0,00185 | 0,0553 | n_hits, n_voxels, rms_z |
| energy_absolute | müon | 0,729 | 0,4316 | 4,6214 | 4,5868 | E_sum, max_hit_frac |
| energy_trans | müon | 0,624 | 0,6200 | 4,5990 | 4,5965 | E_sum, n_voxels, max_hit_frac |
| energy_local | müon | 0,218 | 2,5311 | 3,5115 | 4,3881 | E_sum, centroid_r, rms_r |
| segmentation_absolute | elektron | 0,478 | 0,1369 | 0,4046 | 0,1145 | max_hit_frac, E_voxel_frac, depth_from_first |
| segmentation_trans | elektron | 0,371 | 0,1905 | 0,2022 | 0,0026 | spread, n_neighbours, r_to_centroid |
| segmentation_local | elektron | 0,369 | 0,1961 | 0,2177 | 0,0109 | max_hit_frac, n_neighbours, dist_to_centroid |
| angle_absolute | elektron | 0,996 | 0,0081 | 0,00042 | 0,0081 | centroid_theta |
| angle_trans | elektron | 0,766 | 0,0519 | 0,0216 | 0,0565 | centroid_theta, rms_z, rms_r |
| angle_local | elektron | 0,372 | 0,0920 | 0,00089 | 0,0921 | z_first, early_frac, rms_z |
| energy_absolute | elektron | 0,925 | 0,7864 | 0,7539 | 1,1033 | E_sum, rms_z, centroid_z |
| energy_trans | elektron | 0,916 | 0,8579 | 0,6708 | 1,1033 | E_sum, rms_z, centroid_z |
| energy_local | elektron | 0,918 | 0,8651 | 0,6803 | 1,0854 | E_sum, rms_z |
| segmentation_absolute | pion | 0,173 | 0,2315 | 0,2498 | 0,0598 | r_to_centroid, event_n_voxels, neighbour_E_frac |
| segmentation_trans | pion | 0,070 | 0,2599 | 0,3483 | 0,0101 | neighbour_E_frac, spread, r_to_centroid |
| segmentation_local | pion | 0,079 | 0,2524 | 0,4062 | 0,0200 | z, E_voxel_frac, r_to_centroid |
| angle_absolute | pion | 0,993 | 0,0097 | 0,00189 | 0,0102 | centroid_theta |
| angle_trans | pion | 0,384 | 0,0797 | 0,0530 | 0,0965 | rms_z, centroid_theta, rms_r |
| angle_local | pion | 0,134 | 0,1104 | 0,0141 | 0,1125 | rms_z, z_first, centroid_x |
| energy_absolute | pion | 0,871 | 1,3696 | 1,3822 | 1,9148 | E_sum, centroid_r, n_hits |
| energy_trans | pion | 0,786 | 1,8722 | 1,3579 | 2,4177 | E_sum, n_hits, rms_r |
| energy_local | pion | 0,779 | 1,9095 | 1,2994 | 2,3611 | E_sum, rms_z, centroid_x |

Az `E_sum` a zápor összes detektált energiája, a `max_hit_frac` a legnagyobb
hit relatív részesedése; a többi jellemző jelentése a részecskénkénti
`distill/surrogate.json` és `evaluation/surrogates.md` fájlokban szerepel.

### TTA, magyarázatok és sebesség

A részecske-modellekhez ugyanaz a TTA-stratégia tartozik, mint a protonhoz:
abszolút és transzlált rendszerben a D4-szimmetria 8 transzformációja, lokális
rendszerben az y' tükrözés. A TTA a mentett validációs eredményekben külön
szerepel; a fő táblázat az egyszeri előre-futás eredményeit mutatja. A
Grad-CAM, Shap-CAM, koordinátarendszer-ábrák, overlap-ábrák és a modell-output
CSV mindhárom új részecskéhez elkészült.

Az új részecskékre külön H200 sebességmérés nem készült, ezért a protonos
sebességtáblázat számai nem másolhatók rájuk. A hálóarchitektúra, voxelrács,
TTA-szorzó és magyarázó eljárások azonban azonosak; az effektív sebességet a
hit- és voxel-sűrűség részecskénként befolyásolja.

### Értelmezés és korlátok részecskénként

- **Müon:** az abszolút szögmodell kiváló (0,458 mrad), de az energia
  visszaállítása gyenge (abszolút R²=0,018); a 5 és 15 GeV körüli nagy hibák
  a középtartomány felé húzó becslést mutatják. A szegmentáció fa-fidelityje
  0,472--0,664.
- **Elektron:** mindhárom energia-koordinátarendszer erős (R²=0,935--0,945),
  az abszolút szögmodell 0,421 mrad. A transzlált szög 21,6 mrad-ra romlik,
  mert az abszolút becsapódási hely nem áll rendelkezésre.
- **Pion:** az abszolút szög 1,888 mrad, az energia R²-e 0,824--0,830.
  A 30--100%-os overlap binekben az energia MAE 2,5--4,9 GeV-re nő, a
  szegmentáció pedig a transzlált és lokális rendszerben nehéz (fa-fidelity
  R²=0,070 és 0,079).
- **Közös pipeline-korlát:** a szög- és energiamodellek a tényleges
  `particle_origin` szerinti, már szétválasztott részecske-hiteket kapják.
  Ezért ezek a pontosságok tökéletes szegmentációt feltételeznek; éles
  szegmentációs hibák esetén a láncolt végső teljesítmény rosszabb lesz.
- **Közös validáció:** a split forrásrészecske-csoportos és szivárgásmentes;
  mindegyik részecskénél 4 000 kombinált esemény validációs, a binbontásban
  pedig a táblázatban megadott eseményszámok szerepelnek.

Részletes metrikák, ábrák, `summary.json`, kiértékelés és lepárlási fájlok a
`scripts/vizualizations_muon/`, `scripts/vizualizations_electron/` és
`scripts/vizualizations_pion/` könyvtárakban találhatók.

## Szerkezet

```
registry.py        a 9 modell katalógusa (kulcs → checkpoint, kimeneti mappa, CSV-előtag)
runner.py          modellek építése, tanítás/betöltés, lépések, CSV-export, folytatás
evaluation.py      validáció átfedési binenként, lepárlás-összefoglaló
common/            koordináták, adathalmazok, split, A+B-szétválasztás, rétegek, batch-ek, ábrák
models/<feladat>/  config, data, model, loss, training, metrics, explain, plots, pipeline
distill/           szurrogát fák és PySR, fizikai jellemzők
ui/                UI-szerződés: manifest.json, admin-alapértelmezések (lásd ui/README.md)
docs/              irodalom
scripts/           run_models.ipynb, run_all.py, smoke_test.py, ablations.py,
                   build_combined_coords.py; kimenetek: csv/ (CSV + manifest), vizualizations/
checkpoints/       <kulcs>.pth, a tanítás során jön létre (a kimenethez nem szükséges)
```

## Parancsok (a `scripts/` mappából)

```
python build_combined_coords.py        # a koordinátás 20k kombinált adathalmaz (egyszer kell)
python smoke_test.py                   # gyors végpontok közti teszt, 1 epoch, a valódi súlyok nem változnak
python run_all.py --train --surrogate --pysr --visualize --csv    # minden modell (8 epoch, 32³)
python run_all.py --models segmentation_trans --explain --csv     # egy modell kimenetei
python run_all.py --export-from ../cache/columns                  # félretett oszlopokból: CSV, kiértékelés, manifest
python ablations.py segmentation_no_hit_encoder segmentation_narrow   # kimenet: vizualizations/ablations/
python -m lib.ui.settings show         # admin-alapértelmezések (a tamas/models mappából)
```
