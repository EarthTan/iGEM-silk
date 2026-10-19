> English translation of [README.md](README.md). The Chinese original is kept unchanged as the source of truth.

# Round 3: Heavy-Service Scoring — 50K Dual Channel (TemStaPro pre-screen version)

**Time**: 2026-05-17 20:34:37
**Duration**: 3891 seconds
**Input**: 50,000 peptides (top25K + bottom25K)
**Output directory**: output2/

## Scoring Services (7)

| Service | Weight | Direction |
|------|------|------|
| anoxpepred | 0.45 | positive |\n| toxinpred3 | 0.13 | negative |\n| algpred2 | 0.09 | negative |\n| hemopi2 | 0.09 | negative |\n| mhcflurry | 0.05 | negative |\n| bepipred3 | 0.10 | negative |\n| temstapro | 0.09 | positive |\n

**TemStaPro**: used (pre-screen + BepiPred3 candidate reduction)

## TemStaPro Pre-screen

To improve efficiency, TemStaPro first ran on all 50K, then the top 30% of TemStaPro scores were taken within each channel:
- Top channel: 25,000 → top 30% by TemStaPro → 7,500 sent to BepiPred3
- Bottom channel: 25,000 → top 30% by TemStaPro → 7,500 sent to BepiPred3
- Total BepiPred3 candidates: 15,000

## Dual-Channel Design

| Channel | TemStaPro pre-screen source | Final screening logic | Output |
|------|--------------------|-------------|------|
| Top | top25K → top 30% by TemStaPro (7,500) | sort by the 7-service composite score and take the top 80 | top80.csv |
| Bottom | bottom25K → top 30% by TemStaPro (7,500) | safety dimensions normal -> sort by anoxpepred ascending and take 10 | bottom10.csv |

Bottom channel safety thresholds:
- ToxinPred3 < 0.60
- AlgPred2 < 0.50
- HemoPI2 < 0.70
- MHCflurry < 0.50
- BepiPred3 < 0.60

## Score Distributions

```
anoxpepred distribution (n=50000):
  mean:   0.3450
  median: 0.3388
  std dev: 0.1081
  min: 0.1576
  max: 0.6046
  P5: 0.2254  |  P25: 0.2406  |  P75: 0.4461  |  P95: 0.4803

  distribution histogram:
  0.1576-0.2135: ░░░░░░░░░░░░░░  (525 seqs, 1.1%) 
  0.2135-0.2693: ███████░░░░░░░  (24,475 seqs, 48.9%) 
  0.2693-0.3252: ░░░░░░░░░░░░░░  (0 seqs, 0.0%) 
  0.3252-0.3811: ░░░░░░░░░░░░░░  (0 seqs, 0.0%) ← mean
  0.3811-0.4370: ██░░░░░░░░░░░░  (6,717 seqs, 13.4%) 
  0.4370-0.4929: █████░░░░░░░░░  (17,014 seqs, 34.0%) 
  0.4929-0.5487: ░░░░░░░░░░░░░░  (1,220 seqs, 2.4%) 
  0.5487-0.6046: ░░░░░░░░░░░░░░  (48 seqs, 0.1%) 

toxinpred3 distribution (n=50000):
  mean:   0.2673
  median: 0.2350
  std dev: 0.1384
  min: 0.0000
  max: 1.0000
  P5: 0.1050  |  P25: 0.1700  |  P75: 0.3300  |  P95: 0.5500

  distribution histogram:
  0.0000-0.1250: █░░░░░░░░░░░░░  (4,782 seqs, 9.6%) 
  0.1250-0.2500: ██████░░░░░░░░  (22,175 seqs, 44.4%) 
  0.2500-0.3750: ████░░░░░░░░░░  (13,768 seqs, 27.5%) ← mean
  0.3750-0.5000: ██░░░░░░░░░░░░  (5,547 seqs, 11.1%) 
  0.5000-0.6250: █░░░░░░░░░░░░░  (2,397 seqs, 4.8%) 
  0.6250-0.7500: ░░░░░░░░░░░░░░  (991 seqs, 2.0%) 
  0.7500-0.8750: ░░░░░░░░░░░░░░  (272 seqs, 0.5%) 
  0.8750-1.0000: ░░░░░░░░░░░░░░  (62 seqs, 0.1%) 

algpred2 distribution (n=50000):
  mean:   0.3591
  median: 0.3530
  std dev: 0.0639
  min: 0.1250
  max: 0.8160
  P5: 0.2670  |  P25: 0.3150  |  P75: 0.3960  |  P95: 0.4720

  distribution histogram:
  0.1250-0.2114: ░░░░░░░░░░░░░░  (155 seqs, 0.3%) 
  0.2114-0.2977: ██░░░░░░░░░░░░  (7,395 seqs, 14.8%) 
  0.2977-0.3841: ████████░░░░░░  (27,128 seqs, 54.3%) ← mean
  0.3841-0.4705: ████░░░░░░░░░░  (12,741 seqs, 25.5%) 
  0.4705-0.5569: █░░░░░░░░░░░░░  (2,181 seqs, 4.4%) 
  0.5569-0.6432: ░░░░░░░░░░░░░░  (344 seqs, 0.7%) 
  0.6432-0.7296: ░░░░░░░░░░░░░░  (50 seqs, 0.1%) 
  0.7296-0.8160: ░░░░░░░░░░░░░░  (5 seqs, 0.0%) 

hemopi2 distribution (n=50000):
  mean:   0.2199
  median: 0.1964
  std dev: 0.0639
  min: 0.1685
  max: 0.7674
  P5: 0.1768  |  P25: 0.1849  |  P75: 0.2238  |  P95: 0.3609

  distribution histogram:
  0.1685-0.2434: ███████████░░░  (41,013 seqs, 82.0%) ← mean
  0.2434-0.3182: █░░░░░░░░░░░░░  (5,100 seqs, 10.2%) 
  0.3182-0.3931: █░░░░░░░░░░░░░  (2,092 seqs, 4.2%) 
  0.3931-0.4680: ░░░░░░░░░░░░░░  (1,104 seqs, 2.2%) 
  0.4680-0.5428: ░░░░░░░░░░░░░░  (463 seqs, 0.9%) 
  0.5428-0.6177: ░░░░░░░░░░░░░░  (178 seqs, 0.4%) 
  0.6177-0.6925: ░░░░░░░░░░░░░░  (40 seqs, 0.1%) 
  0.6925-0.7674: ░░░░░░░░░░░░░░  (9 seqs, 0.0%) 

mhcflurry distribution (n=50000):
  mean:   0.0049
  median: 0.0000
  std dev: 0.0462
  min: 0.0000
  max: 0.9002
  P5: 0.0000  |  P25: 0.0000  |  P75: 0.0000  |  P95: 0.0000

  distribution histogram:
  0.0000-0.1125: ██████████████  (49,314 seqs, 98.6%) ← mean
  0.1125-0.2250: ░░░░░░░░░░░░░░  (421 seqs, 0.8%) 
  0.2250-0.3376: ░░░░░░░░░░░░░░  (40 seqs, 0.1%) 
  0.3376-0.4501: ░░░░░░░░░░░░░░  (49 seqs, 0.1%) 
  0.4501-0.5626: ░░░░░░░░░░░░░░  (60 seqs, 0.1%) 
  0.5626-0.6751: ░░░░░░░░░░░░░░  (27 seqs, 0.1%) 
  0.6751-0.7877: ░░░░░░░░░░░░░░  (36 seqs, 0.1%) 
  0.7877-0.9002: ░░░░░░░░░░░░░░  (52 seqs, 0.1%) 

bepipred3 distribution (n=15000):
  mean:   0.2718
  median: 0.2747
  std dev: 0.0328
  min: 0.0480
  max: 0.3575
  P5: 0.2193  |  P25: 0.2538  |  P75: 0.2941  |  P95: 0.3176

  distribution histogram:
  0.0480-0.0867: ░░░░░░░░░░░░░░  (12 seqs, 0.1%) 
  0.0867-0.1254: ░░░░░░░░░░░░░░  (73 seqs, 0.5%) 
  0.1254-0.1641: ░░░░░░░░░░░░░░  (70 seqs, 0.5%) 
  0.1641-0.2028: ░░░░░░░░░░░░░░  (224 seqs, 1.5%) 
  0.2028-0.2414: ██░░░░░░░░░░░░  (1,793 seqs, 12.0%) 
  0.2414-0.2801: ██████░░░░░░░░  (6,416 seqs, 42.8%) ← mean
  0.2801-0.3188: █████░░░░░░░░░  (5,744 seqs, 38.3%) 
  0.3188-0.3575: █░░░░░░░░░░░░░  (667 seqs, 4.4%) 

temstapro distribution (n=50000):
  mean:   0.3549
  median: 0.3443
  std dev: 0.1216
  min: 0.0107
  max: 0.9117
  P5: 0.1741  |  P25: 0.2687  |  P75: 0.4292  |  P95: 0.5713

  distribution histogram:
  0.0107-0.1233: ░░░░░░░░░░░░░░  (578 seqs, 1.2%) 
  0.1233-0.2359: ██░░░░░░░░░░░░  (7,525 seqs, 15.0%) 
  0.2359-0.3486: █████░░░░░░░░░  (17,598 seqs, 35.2%) 
  0.3486-0.4612: ████░░░░░░░░░░  (15,165 seqs, 30.3%) ← mean
  0.4612-0.5738: ██░░░░░░░░░░░░  (6,718 seqs, 13.4%) 
  0.5738-0.6865: █░░░░░░░░░░░░░  (1,921 seqs, 3.8%) 
  0.6865-0.7991: ░░░░░░░░░░░░░░  (425 seqs, 0.9%) 
  0.7991-0.9117: ░░░░░░░░░░░░░░  (69 seqs, 0.1%) 

r3_weighted_score distribution (n=50000):
  mean:   0.5173
  median: 0.5152
  std dev: 0.0563
  min: 0.3294
  max: 0.6739
  P5: 0.4350  |  P25: 0.4678  |  P75: 0.5664  |  P95: 0.6030

  distribution histogram:
  0.3294-0.3725: ░░░░░░░░░░░░░░  (28 seqs, 0.1%) 
  0.3725-0.4155: ░░░░░░░░░░░░░░  (876 seqs, 1.8%) 
  0.4155-0.4586: ██░░░░░░░░░░░░  (7,750 seqs, 15.5%) 
  0.4586-0.5017: ████░░░░░░░░░░  (13,222 seqs, 26.4%) 
  0.5017-0.5447: ██░░░░░░░░░░░░  (8,755 seqs, 17.5%) ← mean
  0.5447-0.5878: ████░░░░░░░░░░  (13,574 seqs, 27.1%) 
  0.5878-0.6308: ██░░░░░░░░░░░░  (5,573 seqs, 11.1%) 
  0.6308-0.6739: ░░░░░░░░░░░░░░  (221 seqs, 0.4%) 

```

## Safety Flags

| Level | All 50K | Share |
|------|----------|------|
| Safe | 47,034 | 94.1% |
| Caution | 2,770 | 5.5% |
| Danger | 201 | 0.4% |
| Missing | 35,000 | 70.0% |

## Top 10 (Top channel by composite score)

| ID | Sequence | Length | Composite score | Safety |
|----|------|------|--------|------|
| pep_491709 | KNMVIGGYYPYPPVPETFS       | 19 | 0.6739 | safe |
| pep_448117 | ITAVMPFYPYAR              | 12 | 0.6605 | safe |
| pep_123291 | DFHHHHFPDME               | 11 | 0.6602 | safe |
| pep_451916 | IVAVDPDEPIHGPPFDFSLE      | 20 | 0.6595 | safe |
| pep_969618 | VLYLEPHHPEGLER            | 14 | 0.6591 | safe |
| pep_885860 | TIFATHYHELTELSR           | 15 | 0.6587 | safe |
| pep_928193 | VALGHAYHPEEF              | 12 | 0.6583 | safe |
| pep_303061 | GAAVGFPTHLYPGVYPAMR       | 19 | 0.6572 | safe |
| pep_934844 | VDLLVFNPPYVVTPPQE         | 17 | 0.6562 | safe |
| pep_648372 | NGNPNGEGLPHWPLFDQEEQY     | 21 | 0.6553 | safe |

## Bottom 10 (safe but with the worst antioxidant capacity)

| # | ID | Sequence | AnOxPePred | ToxinPred3 | HemoPI2 | AlgPred2 |
|---|-----|------|-----------|------------|---------|----------|
| 1 | pep_002974 | AACEQLHQQQQQQQEETAAA | 0.1594 | 0.245 | 0.42849889397621155 | 0.43 |
| 2 | pep_895244 | TLQLLNQQEQEKEESSSEEE | 0.1645 | 0.245 | 0.24800509214401245 | 0.366 |
| 3 | pep_889620 | TKQQQQQQQQSNSSSGVANN | 0.1715 | 0.14 | 0.24537663161754608 | 0.295 |
| 4 | pep_206019 | EGCNILCLLKRKVKAVKNVV | 0.1822 | 0.545 | 0.5389243960380554 | 0.366 |
| 5 | pep_608130 | LVQQQEEEQQKQQSASSIVA | 0.1826 | 0.17 | 0.19996806979179382 | 0.369 |
| 6 | pep_1043856 | YQQQQQQQKQAAAAAAAAAA | 0.1861 | 0.16 | 0.345275342464447 | 0.434 |
| 7 | pep_140158 | DKKVEKVTISN          | 0.1883 | 0.165 | 0.18515358865261078 | 0.313 |
| 8 | pep_078551 | ATYKVKDSSVGK         | 0.1888 | 0.36 | 0.18827182054519653 | 0.351 |
| 9 | pep_988471 | VTAEDKGTGNKNKITITNDQ | 0.1903 | 0.12 | 0.2423596978187561 | 0.309 |
| 10 | pep_217694 | EKKVVKITSE           | 0.1925 | 0.225 | 0.19052106142044067 | 0.346 |

## Top 10 Rank Gains (R1 -> R3)

| Peptide | Rank change | R3 composite score |
|----|----------|-----------|
| pep_226619 | R1:5960 -> R2:6441 -> R3:44 | 0.6451 |
| pep_1007757 | R1:6926 -> R2:6186 -> R3:58 | 0.6424 |
| pep_118788 | R1:7333 -> R2:3454 -> R3:71 | 0.6402 |
| pep_233907 | R1:7470 -> R2:7615 -> R3:38 | 0.6459 |
| pep_146503 | R1:8203 -> R2:8355 -> R3:14 | 0.6528 |
| pep_467634 | R1:9537 -> R2:10428 -> R3:54 | 0.6431 |
| pep_221657 | R1:10210 -> R2:13188 -> R3:59 | 0.6424 |
| pep_448117 | R1:19324 -> R2:24163 -> R3:2 | 0.6605 |
| pep_448118 | R1:20796 -> R2:21123 -> R3:33 | 0.6464 |
| pep_239481 | R1:25148 -> R2:21644 -> R3:72 | 0.6402 |

## Top 10 Rank Drops (R1 -> R3)

| Peptide | Rank change | R3 composite score |
|----|----------|-----------|
| pep_410405 | R1:25 -> R2:71 -> R3:66 | 0.6411 |
| pep_277272 | R1:53 -> R2:191 -> R3:77 | 0.6393 |
| pep_676330 | R1:27 -> R2:72 -> R3:47 | 0.6442 |
| pep_966988 | R1:74 -> R2:37 -> R3:78 | 0.6391 |
| pep_977590 | R1:23 -> R2:16 -> R3:13 | 0.6540 |
| pep_679714 | R1:31 -> R2:144 -> R3:16 | 0.6509 |
| pep_491709 | R1:47 -> R2:32 -> R3:1 | 0.6739 |
| pep_969618 | R1:58 -> R2:112 -> R3:5 | 0.6591 |
| pep_123291 | R1:57 -> R2:63 -> R3:3 | 0.6602 |
| pep_238278 | R1:93 -> R2:285 -> R3:36 | 0.6460 |

## Output Files

| File | Description | Rows |
|------|------|------|
| final/all_scored.csv | scoring details for all 50K (BepiPred3 has values for only 15,000) | 50000 |
| final/top80.csv | top 80 of the Top channel (from the TemStaPro top 30% candidate pool) | 80 |
| final/bottom10.csv | 10 negative controls of the Bottom channel (from the TemStaPro top 30% candidate pool) | 10 |
| final/danger_list.csv | list of high-risk peptides | 201 |
| final/trajectory.csv | cross-round ranking trajectory (R1->R2->R3) | 80 |
