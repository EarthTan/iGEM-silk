# Guide to `top10.csv`: Source Data, round7_score, and the Construct Workflow

This note explains the two columns in `top10.csv` that carry the most meaning — `source_database` / `source_accession` and `round7_score` — and sets out how the fusion constructs listed in that table were built. It is written to be read on its own, without reference to the pipeline source code, so that it can be reused in the Parts description, the project video, and the wiki.

## What the table is

The file `output4/final/top10.csv` is the final deliverable of the computational design pipeline. The pipeline began with a pool of 19,890,021 short peptide sequences drawn from two public databases and ended with 250 complete fusion-protein constructs. Those 250 constructs were split into two channels: a **Top channel** of 150 constructs carrying peptides with the highest predicted antioxidant activity, and a **Bottom channel** of 100 constructs carrying peptides with the lowest predicted antioxidant activity, retained as a negative control so that any later wet-lab result can be compared against a matched background.

`top10.csv` lists the ten best-ranked constructs **within the Top channel**, ordered by `channel_rank`. The companion file `bottom10.csv` lists the ten best-ranked constructs within the Bottom channel on the identical principle. Both files carry the same ten columns.

One point needs stating before any of the numbers are read, because it is visible in the very first data row and would otherwise look like an error. The column `global_rank` does not run 1 to 10. It runs 9, 13, 17, 19, 37, 39, 47, 49, 50, 57. Global rank is assigned across all 250 constructs by `round7_score`, and the eight constructs occupying global ranks 1 through 8 all belong to the Bottom channel. The reason is set out in the section on `round7_score` below: that score measures structural quality only, and the Bottom channel — having been filtered through the same safety vetoes and the same structure-based ranking — holds peptides that are, on those structural grounds alone, indistinguishable from or slightly better than the Top channel. The two columns `global_rank` and `channel_rank` answer different questions. `channel_rank` answers "which construct is best within its channel", which is the question relevant to picking a candidate from a given channel; `global_rank` answers "which construct scores highest overall", which mixes two channels whose defining difference — predicted antioxidant activity — the score deliberately ignores.

## Reproduced table

| global_rank | channel_rank | construct_id | position | linker | peptide_seq | source_database | source_accession | round7_score |
|---|---|---|---|---|---|---|---|---|
| 9 | 1 | con_0418 | C | Flex_GGGGSx2 | MNRPWITGHHHHHHHRRRRRRRRRR | mgy | MGYP003726304477 | 0.7076 |
| 13 | 2 | con_0417 | C | Flex_GGGGSx1 | MNRPWITGHHHHHHHRRRRRRRRRR | mgy | MGYP003726304477 | 0.6993 |
| 17 | 3 | con_0317 | Both | Flex_GGGGSx1 | MARKKPKGYGYVHVKYKQRKRP | mgy | MGYP000135496939 | 0.6918 |
| 19 | 4 | con_0850 | C | Flex_GGGGSx2 | MLDRRGGGRGEGGAPPPPPHPHNKKKEK | mgy | MGYP001801765991 | 0.6893 |
| 37 | 5 | con_0558 | Both | Flex_GGGGSx2 | GERSGGVVRGGHPPHAPRRARGGEAAH | mgy | MGYP000036905120 | 0.6723 |
| 39 | 6 | con_0561 | C | Flex_GGGGSx1 | MEKGKTEWDYRYPKQHWYKK | mgy | MGYP003318721764 | 0.6711 |
| 47 | 7 | con_0660 | Both | Flex_GGGGSx2 | MERRRAVCGGEGPPGPGRRGPGAPAKG | mgy | MGYP001324525516 | 0.6676 |
| 49 | 8 | con_0521 | Both | Flex_GGGGSx1 | MGVGVGDGERVHAHMHTHMHTHMHAHHVPI | mgy | MGYP000246342658 | 0.6671 |
| 50 | 9 | con_0768 | Both | Flex_GGGGSx2 | MKNPLQEVTPAGHPHKRKFPSKKR | uniprot | A0A5K0UWX3 | 0.6671 |
| 57 | 10 | con_0322 | C | Flex_GGGGSx2 | MDVRTTVILKTNRHPPPKKKKQKKKNKKK | mgy | MGYP000714941843 | 0.6642 |

## `source_database` and `source_accession`

These two columns together answer a single question: where did this functional peptide come from before the pipeline touched it. Every candidate sequence in the pool carries the database it was drawn from and that database's own identifier for the sequence, and those two fields are carried unchanged through all nine rounds of filtering. Because the identifier is preserved end to end, any construct in the table can be traced back to the exact original entry and its original annotation.

The two possible values of `source_database` are `mgy` and `uniprot`, corresponding to **MGnify** and **UniProt**.

**UniProt** is the reference proteome database. Its entries are full-length, manually curated or automatically annotated proteins, each carrying a stable accession of the form `A0A5K0UWX3` or `P12345`. UniProt was contributed to this project because it is the best available record of protein function: an entry that already carries a functional annotation is the strongest starting point for a peptide that is meant to perform a known task.

**MGnify** is the metagenomic sequence database of the European Nucleotide Archive. Its entries are predicted protein sequences assembled directly from environmental DNA — seawater, soil, sediment, gut contents, and similar samples — with no culturing step and often no organism assignment. Each entry receives an accession of the form `MGYP` followed by twelve digits, such as `MGYP003726304477`. The header of an MGnify entry may also carry a flag such as `FL=1`, indicating a full-length sequence.

The accession prefixes in the table make the split immediately visible. Of the ten constructs in `top10.csv`, nine carry `MGYP…` accessions and one (`con_0768`) carries a UniProt accession in the `A0A5K0UWX3` form. Across all 250 final constructs the ratio is 244 MGnify to 6 UniProt.

That imbalance is not a design choice but a consequence of the length filter applied before anything else. All the prediction models used in this project accept peptides of 3 to 30 residues, and no longer, so the first preprocessing step discarded every sequence outside that window. UniProt is overwhelmingly a catalogue of full-length proteins, the great majority of which run from one hundred to several hundred residues; almost none of them survive a filter that keeps only sequences of thirty residues or fewer. MGnify is a catalogue of predicted small proteins and short open reading frames, exactly the size range the filter keeps. In the unfiltered pool the two databases contributed 733,573 UniProt sequences and 19,156,448 MGnify sequences; after the length and residue-type filters the ratio was never meaningfully altered, because the sequences being discarded for length were almost entirely UniProt's.

The practical consequence for interpretation is worth stating plainly. An MGnify accession means the peptide's sequence is real and its fold is computationally predicted, but it carries no functional annotation — nobody has ever measured what this peptide does. A UniProt accession is the stronger provenance, and it is the only one of the two that arrives with prior biological evidence attached. Against a pool in which 96.3 percent of the surviving candidates are unannotated metagenomic fragments, the annotated minority is disproportionately valuable per candidate, which is why `con_0768` remains in the Top 10 despite being sourced from the far smaller UniProt contribution.

## `round7_score`

`round7_score` is the single number that produced the ordering in the table. It is a weighted sum of three structural quantities measured on the predicted three-dimensional structure of the complete fusion construct, all normalised to a common 0-to-1 scale so that they can be added:

```
round7_score = 0.40 × SASA  +  0.40 × (1 − Aggrescan3D)  +  0.20 × pLDDT_norm
```

The three terms are described below in the order they appear in the formula.

**SASA** is the solvent-accessible surface area of the functional peptide within the folded construct. Surface area is computed with FreeSASA, which rolls a spherical probe of radius 1.4 Å over the structure and counts how much of each residue's surface the probe can reach — the standard Lee–Richards algorithm. Each residue's raw accessible area is then divided by the maximum area that residue type can ever expose, using the reference values of Tien and colleagues, giving a *relative* accessibility between 0 and 1. The score reported here is the mean relative accessibility across the peptide region only, not across the whole protein. The reasoning behind the metric is functional rather than structural: a peptide buried inside the core of the scaffold cannot make contact with the reactive species it is meant to act on, whereas a peptide sitting on the surface can. Higher is better, and the Top 10 constructs score between 0.6506 and 0.8228 on this term.

**Aggrescan3D** estimates how strongly a protein tends to aggregate. The original tool computes, for every residue, a contribution to aggregation propensity based on that residue's burial depth, its side-chain hydrophobicity relative to its neighbours, and the pairwise interaction energy between contacting residues; hot spots on the surface drive aggregation. The value recorded in the construct record is a rescaled risk index between 0 and 1, built from three summaries of those per-residue values: the fraction of residues with a positive contribution, their mean positive contribution, and the single largest hot-spot value. Because a high index means a greater tendency to clump together and aggregate — which lowers expression yield and complicates purification — the formula subtracts it from one. Lower raw Aggrescan3D therefore becomes higher contribution to `round7_score`.

**pLDDT** is the per-residue confidence score produced by OmegaFold, running between 0 and 1, where values above 0.90 indicate a well-resolved core region and values below 0.50 indicate a segment the model considers essentially disordered. The value recorded for a construct is the mean pLDDT over the whole chain. Because the quantity is only meaningful relative to the other constructs being compared, it is min–max normalised across the 250 constructs before use, which is what the `norm` suffix denotes: within this dataset pLDDT ranged from 0.3742 to 0.4950, and that narrow band is stretched to fill the full 0-to-1 interval.

The weights are 0.40, 0.40, and 0.20. Surface exposure and aggregation propensity carry equal weight because they are the two properties that bear directly on whether the expressed protein behaves as a designed construct at all — a peptide that cannot be reached does nothing, and a protein that aggregates does not get expressed. Structural confidence enters at half the weight of either, on the reasoning that it should temper the other two rather than drive them: a predicted structure is evidence about a construct, not the construct itself. These weights were carried over unchanged from an earlier version of the pipeline where they were found to produce a usable separation between constructs, and that verification is recorded in the pipeline review.

Across the 250 constructs `round7_score` spans 0.4800 to 0.7579, with a mean of 0.6327. Among the Top 10 the values run from 0.7076 down to 0.6642, a spread of only 0.043 — worth keeping in mind, because it means the top of this table is a set of near-equivalent candidates rather than one clear winner.

The single most important property of this score is what it leaves out. `round7_score` contains no term for antioxidant activity, and contains no term for any other functional property. This is deliberate. Antioxidant prediction was used exactly once in the pipeline, to assign candidates to the Top and Bottom channels in the first round; once a candidate's channel was fixed, the antioxidant signal was excluded from all downstream ranking, on the reasoning that a functional score and a quality score should not be blended into a single number. `round7_score` is therefore purely a statement about physical quality — will this construct fold, will it stay soluble, will the functional peptide be reachable. It does not claim that any of these peptides is a strong antioxidant, and no statement about antioxidant strength should be inferred from a `round7_score` value or from a position in either table.

That design choice is what produces the counterintuitive ordering noted at the top of this note. The Bottom channel peptides, having passed the same safety vetoes and the same structure-based ranking, tend to score at least as well structurally as the Top channel peptides — a difference that is statistically robust across the final set, with the Bottom channel ahead on pLDDT, solubility, thermal stability, and composite score. The eight highest-scoring constructs in the entire run are all Bottom-channel constructs, and the best of them, `con_5489` at 0.7579, outscores the best Top-channel construct, `con_0418`, at 0.7076. This is a structural artefact, not a design error, and it is why wet-lab work on this pipeline should draw candidates from both channels rather than from `top10.csv` alone.

## How the constructs were built

Every construct in the table is the same three-part assembly: a silk fibroin scaffold, a flexible linker, and the functional peptide, followed by a single purification tag. The variables are where the peptide goes, which linker joins it, and which peptide is used.

**The scaffold** is a recombinant silk protein, `FibLNT8-10xRep-FibHCT`, 372 residues as synthesised: the N-terminal domain of *B. mori* fibroin, ten glycine-rich repeats characteristic of the silk C-terminal region, and a C-terminal His-tag-bearing segment. The native C-terminal tag was removed during construct assembly so that it would not duplicate the tag added at the end, leaving a 364-residue scaffold used in all 250 constructs.

**The tag** is the eight-residue sequence `LEHHHHHH` appended to the C-terminus of every construct. It serves as a purification handle for affinity chromatography and as the spacer that keeps the terminal `HHHHHH` motif away from the body of the protein. Exactly one copy is present in every construct.

**The linker** is a flexible glycine-serine chain bridging scaffold and peptide. Ten linker designs were evaluated for the library; two were carried into construct assembly. `Flex_GGGGSx1` is the five-residue `GGGGS`, the shortest and least structurally disruptive option. `Flex_GGGGSx2` is `GGGGSGGGGS`, a ten-residue version offering more freedom of motion and a higher chance of pushing the peptide clear of the scaffold surface. Glycine and serine are used because glycine has no side chain and is the most conformationally flexible residue, while serine is small and polar and keeps the chain soluble; the repeating `GGGGS` pattern is the standard flexible-linker motif first described in the recombinant protein literature.

**The position** determines where the functional peptide is fused, and three positions were enumerated for every peptide: `N` places the peptide before the scaffold, `C` places it after the scaffold, and `Both` places a copy at each end. Each fusion is a direct in-frame join — the peptide is appended to the sequence with no additional spacer beyond the linker.

The assembly logic, with `LEHHHHHH` denoting the purification tag:

```
position N    peptide + linker + scaffold + LEHHHHHH
position C    scaffold + linker + peptide + LEHHHHHH
position Both peptide + linker + scaffold + linker + peptide + LEHHHHHH
```

`con_0418`, the highest-ranked construct in the Top channel, follows the `C` pattern with the longer linker: its 364-residue scaffold, then `GGGGSGGGGS`, then its 25-residue peptide `MNRPWITGHHHHHHHRRRRRRRRRR`, then the tag, giving a 407-residue product. `con_0317` follows the `Both` pattern with the shorter linker: peptide on each side of the scaffold, giving a 426-residue product. In the Top 10, five constructs use the `C` position and five use `Both`; the `N` position does not appear. That is consistent with the larger Phase 1 set, where `Both` was the most common survivor, because a doubled peptide contributes more mass to the solubility and thermal-stability predictions that Phase 1 ranked on.

## The filter that produced them

The peptide sequences in the table were not chosen by the pipeline designer; they are the survivors of a nine-round funnel that began with 19,890,021 sequences and ended with 250 constructs, an overall rejection rate of 99.9987 percent. The rounds run from heaviest to lightest in alternating fashion, and each one applies a single criterion rather than blending criteria.

**Preprocessing** cut the pool to sequences of 3 to 30 residues composed only of the twenty standard amino acids. The upper bound is set by the prediction models themselves; several of them, including the cell-penetration predictors, cannot accept a longer sequence.

**Round 1** scored all remaining candidates for predicted antioxidant activity and for allergenicity, then divided them into channels. Candidates predicted allergenic at or above a score of 0.30 were removed outright. The remainder were sorted by antioxidant score alone, with the top ten percent assigned to the Top channel and the bottom one percent to the Bottom channel. This is the only point at which antioxidant prediction influences anything downstream.

**Round 2** applied the safety veto. Three independent checks ran on every candidate, each with its own threshold and each able to eliminate a candidate on its own: predicted toxicity below 0.38, predicted haemolytic activity below 0.55, and predicted MHC-I binding below 0.50. A candidate failing any one of the three was discarded. This design replaced an earlier approach in which safety scores were mixed into a weighted average with a small coefficient, an approach that allowed a peptide with strong antioxidant predictions and poor safety predictions to survive on the strength of its antioxidant score. Safety in this pipeline is a veto, not a term that can be compensated.

**Round 3** scored the surviving peptides for four functional and physicochemical properties — B-cell epitope propensity, thermal stability, solubility, and cell-penetration propensity — and combined them into a composite score. The weights were not set by hand. Each property received a weight proportional to its standard deviation across the dataset, computed after trimming the extreme one percent of values, so that a property which actually separates candidates in this dataset carries more weight than one that does not. This is the only weighted average in the pipeline, and it is the mechanism that determines which peptides are carried forward into construct assembly.

**Round 4** built the constructs. The top 4,324 ranked peptides — 116 from the Top channel, 4,208 from the Bottom — were each assembled in all six combinations of position and linker, giving 25,944 constructs. Each was scored for solubility and thermal stability as a complete full-length protein rather than as a free peptide, and the top ten percent of that combined score, 2,594 constructs, advanced. A further pass added B-cell epitope prediction at the full-construct level. This stage is the reason the pipeline scores assembled constructs and not only peptides: a peptide that is stable and soluble on its own may behave quite differently once fused to a 364-residue scaffold.

**Rounds 5 and 6** predicted the three-dimensional structure of every surviving construct with OmegaFold, then measured surface exposure and aggregation propensity on the resulting structure. One hundred percent of the 250 constructs produced usable structures.

**Round 7** combined those measurements into `round7_score` and produced the two ranked tables.

**Round 8** re-predicted the top ten constructs from each channel with AlphaFold3, a more recent and more accurate structure predictor, as an independent check on the OmegaFold-based ranking. Mean confidence across the twenty constructs was 0.52, spanning 0.50 to 0.56, with the Top-channel construct `con_0850` the single highest at 0.56.

## Two qualifications worth carrying into any external description

The first is that the OmegaFold confidence values in this dataset are low across the board, averaging 0.42 and never exceeding 0.50 on a scale where 0.50 marks the boundary of meaningful confidence. This is not a failure of the constructs; it is a property of silk fibroin. The scaffold is built from glycine-alanine repeats that adopt a disordered, partially amorphous fold, and AlphaFold3 independently returned the same picture at a mean of 0.52. The consequence is that the three-dimensional structures underpinning `round7_score` are low-confidence models, and the score is best understood as a consistent way to rank imperfectly-modelled structures rather than as a precise physical measurement. This is the expected behaviour for a silk-based platform and it is worth stating plainly in any external text rather than leaving unexplained.

The second concerns the top two rows of the table. The peptide `MNRPWITGHHHHHHHRRRRRRRRRR`, carried by both `con_0418` and `con_0417`, is twenty-five residues long and consists of a short serine-rich leader followed by six histidines and a run of nine arginines. That composition is characteristic of a purification or cloning handle rather than of a bioactive peptide predicted to be an antioxidant. It entered the candidate pool because the preprocessing step filters by length and residue type only, and this sequence passes both filters while carrying no predicted function. It survived Round 1 because the antioxidant predictor assigned it a middling-to-high score, and it rose to the top of the Top 10 because structural ranking never examines what a peptide does. `con_0417` and `con_0418` are the same peptide at the same position, differing only in linker length, which is why they sit at channel ranks 1 and 2 with near-identical scores. Any external description quoting `top10.csv` therefore carries an obligation to flag this entry explicitly, or to quote it with the qualification attached; presenting it as the project's lead candidate without that context would misdescribe what it is.

## Field reference

`global_rank` — position of the construct among all 250, by `round7_score`, descending. `channel` — `top` or `bottom`, the channel the construct belongs to. `channel_rank` — position within its own channel, by `round7_score`, descending. `construct_id` — construct identifier in the form `con_XXXX`, matching the per-construct records holding full sequences, all scores, and the predicted structure. `position` — fusion site of the peptide: `N`, `C`, or `Both`. `linker` — linker variant joining peptide and scaffold: `Flex_GGGGSx1` or `Flex_GGGGSx2`. `peptide_seq` — one-letter amino-acid sequence of the functional peptide. `source_database` — `mgy` for MGnify or `uniprot` for UniProt. `source_accession` — that database's accession for the original sequence. `round7_score` — final structural quality score, 0.40 × SASA + 0.40 × (1 − Aggrescan3D) + 0.20 × pLDDT_norm.