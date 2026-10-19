> English translation of [threshold.md](threshold.md). The Chinese original is kept unchanged as the source of truth.

### ToxinPred3 (Yuecheng)

> Rathore et al., 2024, “ToxinPred3.0: An improved method for predicting the toxicity of peptides,” Computers in Biology and Medicine, 179:108926

**hard filter: candidates with `toxicity_score >= 0.38` are downgraded or eliminated first**

Model 1 is an Extra Trees classifier using AAC + DPC, that is, 20 amino acid composition features + 400 dipeptide composition features;

Model 2 is a hybrid model = Extra Trees + MERCI motif module, which combines the machine learning score and the motif score into a hybrid score.

### HemoPI2 (Yuecheng)

> Rathore et al., 2025, “Prediction of hemolytic peptides and their hemolytic concentration,” Communications Biology

It specifically predicts whether a peptide will lyse mammalian RBCs, and it adds one quantitative task over the older tool: predicting **HC50**

Run a HemoPI2 scan over functional peptides, linker junctions, and fusion construct sliding windows.

**HC50 ≤ 100 μM = hemolytic; HC50 > 100 μM = non-hemolytic**

If **`HC50<=100µM`** is predicted or the **hemolytic score** is high, the candidate should be downgraded directly. CPPs, AMP-like peptides, and hydrophobic/positively charged fragments in particular are easily given high scores by it.

### AlgPred2 (Wenxuan)

> Sharma, N., Patiyal, S., Dhall, A., Pande, A., Arora, C., & Raghava, G. P. S. (2021). AlgPred 2.0: An improved method for predicting allergenic proteins and mapping of IgE epitopes. *Briefings in Bioinformatics*, *22*(4), bbaa294. https://doi.org/10.1093/bib/bbaa294

- **score > 0.3**: more likely allergenic.
- **score <= 0.3**: more likely non-allergenic

### TemStaPro [binary, not score] (Yuecheng)

> Pudžiuvelytė et al., 2024, “TemStaPro: protein thermostability prediction using sequence representations from protein language models,” Bioinformatics, 40(4), btae157

Predicts whether a protein sequence is likely to remain stable above multiple temperature thresholds.

The core index can be understood as:

```
stable_above_40C: yes/no
stable_above_45C: yes/no
...
stable_above_65C: yes/no
highest non-conflicting stable interval
```

If 40°C is judged unstable but 50°C is judged stable, that result is a conflict, and TemStaPro flags a prediction clash. The authors suggest that only conflict-free results are suitable for interpretation as the “highest stable temperature interval”.
