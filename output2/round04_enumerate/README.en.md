> English translation of [README.md](README.md). The Chinese original is kept unchanged as the source of truth.

# Round 4: Enumeration + Construct-Level Scoring — Report

**Time**: 2026-05-17 20:51:06
**Duration**: 434 seconds

## Scoring Weights

| Dimension | Weight | Description |
|------|------|------|
| Peptide composite score (Round 3) | 0.4 | 7-service weighted composite score |
| SoDoPE solubility | 0.25 | full-length construct-level scoring |
| **Construct AnOxPePred** | 0.2 | **new**: antioxidant score of the full-length fusion protein |
| **Construct BepiPred3** | 0.1 | **new**: B-cell epitope of the full-length fusion protein |
| TemStaPro thermal stability | 0.05 | — |

## Dual-Channel Enumeration

| Channel | Peptides | Linker | Positions | Constructs | Output count |
|------|------|--------|------|-------------|--------|
| Top | 40 | 2 | 3 | 240 | 90 |
| Bottom | 10 | 2 | 3 | 60 | 60 |

## Activity Change Ratio

AnOxPePred activity drop warnings (change ratio < 0.8): 230

Change ratio > 1.0 = activity increased after fusion | ≈ 1.0 = unaffected by the scaffold | < 0.8 = significant drop

## Top Group Summary

| Rank | Peptide | Linker | N/C/Both scores | Best score in group |
|------|------|--------|-------------|----------|
|  1 | pep_977590   | Flex_GGGGSx2              | Both=0.5940 | C=0.5765 | N=0.5912 | 0.5940 |
|  2 | pep_977590   | Flex_GGGGSx1              | Both=0.5928 | C=0.5788 | N=0.5902 | 0.5928 |
|  3 | pep_238278   | Flex_GGGGSx2              | Both=0.5916 | C=0.5671 | N=0.5829 | 0.5916 |
|  4 | pep_033299   | Flex_GGGGSx2              | Both=0.5914 | C=0.5585 | N=0.5791 | 0.5914 |
|  5 | pep_954776   | Flex_GGGGSx2              | Both=0.5905 | C=0.5749 | N=0.5847 | 0.5905 |
|  6 | pep_954776   | Flex_GGGGSx1              | Both=0.5873 | C=0.5762 | N=0.5838 | 0.5873 |
|  7 | pep_238278   | Flex_GGGGSx1              | Both=0.5869 | C=0.5685 | N=0.5788 | 0.5869 |
|  8 | pep_033299   | Flex_GGGGSx1              | Both=0.5858 | C=0.5590 | N=0.5769 | 0.5858 |
|  9 | pep_648372   | Flex_GGGGSx2              | Both=0.5853 | C=0.5670 | N=0.5766 | 0.5853 |
| 10 | pep_648372   | Flex_GGGGSx1              | Both=0.5831 | C=0.5681 | N=0.5762 | 0.5831 |
| 11 | pep_355822   | Flex_GGGGSx2              | Both=0.5817 | C=0.5639 | N=0.5760 | 0.5817 |
| 12 | pep_679714   | Flex_GGGGSx1              | Both=0.5810 | C=0.5777 | N=0.5804 | 0.5810 |
| 13 | pep_648371   | Flex_GGGGSx2              | Both=0.5810 | C=0.5678 | N=0.5716 | 0.5810 |
| 14 | pep_679714   | Flex_GGGGSx2              | Both=0.5778 | C=0.5759 | N=0.5738 | 0.5778 |
| 15 | pep_432652   | Flex_GGGGSx2              | Both=0.5773 | C=0.5645 | N=0.5709 | 0.5773 |
| 16 | pep_648371   | Flex_GGGGSx1              | Both=0.5765 | C=0.5683 | N=0.5677 | 0.5765 |
| 17 | pep_164493   | Flex_GGGGSx1              | Both=0.5742 | C=0.5598 | N=0.5718 | 0.5742 |
| 18 | pep_355822   | Flex_GGGGSx1              | Both=0.5734 | C=0.5648 | N=0.5676 | 0.5734 |
| 19 | pep_020977   | Flex_GGGGSx2              | Both=0.5728 | C=0.5715 | N=0.5667 | 0.5728 |
| 20 | pep_432652   | Flex_GGGGSx1              | Both=0.5727 | C=0.5639 | N=0.5690 | 0.5727 |
| 21 | pep_020977   | Flex_GGGGSx1              | Both=0.5668 | C=0.5727 | N=0.5606 | 0.5727 |
| 22 | pep_142399   | Flex_GGGGSx1              | Both=0.5657 | C=0.5721 | N=0.5610 | 0.5721 |
| 23 | pep_164493   | Flex_GGGGSx2              | Both=0.5710 | C=0.5595 | N=0.5676 | 0.5710 |
| 24 | pep_142399   | Flex_GGGGSx2              | Both=0.5689 | C=0.5706 | N=0.5644 | 0.5706 |
| 25 | pep_252920   | Flex_GGGGSx1              | Both=0.5704 | C=0.5602 | N=0.5675 | 0.5704 |
| 26 | pep_299544   | Flex_GGGGSx1              | Both=0.5620 | C=0.5595 | N=0.5701 | 0.5701 |
| 27 | pep_252920   | Flex_GGGGSx2              | Both=0.5698 | C=0.5591 | N=0.5658 | 0.5698 |
| 28 | pep_233907   | Flex_GGGGSx2              | Both=0.5671 | C=0.5515 | N=0.5645 | 0.5671 |
| 29 | pep_216524   | Flex_GGGGSx2              | Both=0.5670 | C=0.5663 | N=0.5622 | 0.5670 |
| 30 | pep_216524   | Flex_GGGGSx1              | Both=0.5615 | C=0.5667 | N=0.5567 | 0.5667 |

## Score Distributions

- **Composite score**: n=300, mean=0.5362, max=0.5940
- **SoDoPE**: n=300, mean=0.6731
- **Construct AnOxPePred**: n=300, mean=0.3096

## Output

- `final/constructs_top.csv` — Top 90 constructs
- `final/constructs_bottom.csv` — Bottom 60 constructs
- `final/all_constructs.fasta` — 150 entries → Round 5 3D prediction
- `final/context_effect.csv` — change in activity, free peptide vs fused
