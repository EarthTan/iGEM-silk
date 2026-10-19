> English translation of [biological_background.md](biological_background.md). The Chinese original is kept unchanged as the source of truth.

# Biological Background of Peptide Toxicity

## General Characteristics of Toxic Peptides

### Structural Characteristics

| Feature | Description | Typical example |
|-----|------|---------|
| **Short chain** | Usually 5-50 amino acids | Melittin (26aa) |
| **Cationicity** | High proportion of K, R residues | Antimicrobial peptides |
| **Amphiphilicity** | Segregated hydrophilic/hydrophobic regions | Pore-forming peptides |
| **Amidated C-terminus** | C-terminal amidation enhances activity | Various toxic peptides |

### Amino Acid Composition Characteristics

- **Cationic amino acids** (K, R, H): promote interaction with the negative charges of the cell membrane
- **Hydrophobic amino acids** (A, V, I, L, F): mediate membrane insertion
- **Aromatic amino acids** (W, Y, F): affect receptor binding and toxicity

## Biological Basis of Toxicity Prediction

### Mechanism of Action

1. **Membrane action mechanism**
   - Cationic peptides interact with the negative charges of the bacterial cell membrane
   - Hydrophobic regions insert into the membrane interior
   - Pores form and cause cell lysis

2. **MERCI Motif**
   - Matching based on known toxin sequence patterns
   - High specificity for known toxin types
   - Fast screening of large numbers of sequences

### Prediction Challenges

| Challenge | Description |
|------|------|
| **False positive risk** | Some therapeutic antimicrobial peptides may be misjudged as toxic |
| **Species specificity** | Toxins from different species may have different characteristics |
| **Concentration effects** | May be non-toxic at low concentration and toxic at high concentration |
| **Novel toxins** | Only known toxin motifs can be detected; novel toxins may be missed |

## Biological Significance of AAC/DPC Features

### AAC (Amino Acid Composition)

Reflects the overall amino acid distribution of the sequence:
- High proportion of cationic amino acids → may have antibacterial activity, but may also be toxic
- High proportion of hydrophobic amino acids → affects the ability to penetrate cell membranes
- Aromatic amino acids → may affect receptor binding

### DPC (Dipeptide Composition)

Reflects interactions between adjacent amino acids:
- Certain dipeptide motifs are characteristic markers of toxins
- Reflects the local structural preferences of the sequence
- Can capture interactions between amino acids

## Considerations in Fusion Peptide Design

Toxicity assessment of fusion peptides requires particular attention to:

1. **Linker regions**: may introduce new toxic motifs
2. **Proportions of components**: the degree of exposure of each component after fusion
3. **Overall physicochemical properties**: net charge, changes in hydrophobicity
4. **Concentration effects**: toxicity at the actual working concentration

## References

- Rathore AS, et al. (2024) ToxinPred3.0. Computers in Biology and Medicine
- Sharma N, et al. (2022) ToxinPred2. Briefings in Bioinformatics
