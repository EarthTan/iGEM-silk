> English translation of [DATA_PREP.md](DATA_PREP.md). The Chinese original is kept unchanged as the source of truth.

# Stages3 Data Preprocessing Plan

> Version: v1.0 — 2026-05-15
> Data sources: uniprot_all_2021_04.fa (102G) + mgy_clusters_2022_05.fa (120G)
> Input: ~500 million sequences

---

## 1. In-Depth Analysis of the Data Sources

### UniProt Complete Set (uniprot_all_2021_04.fa)

**Size**: 102G, 225,619,586 sequences
**Format**: standard UniProt FASTA; the header line contains:
```
>sp|ID|ENTRY_NAME Description OS=species OX=id GN=gene
```
**Estimated sequence length distribution**: UniProt is dominated by full-length proteins, and most sequences are between 100 and 500 aa long. This means that after the 3-30 aa short-peptide filter, the vast majority of sequences will be filtered out.

**Why UniProt is valuable**:
- The Swiss-Prot portion (a very small fraction) provides high-quality manually annotated functional peptides
- Small open reading frames (small ORFs / SEPs) in TrEMBL are a hidden treasure trove of peptides
- Some annotated antimicrobial peptides and antioxidant proteins are themselves candidates

### MGnify Clusters (mgy_clusters_2022_05.fa)

**Size**: 120G, ~624,000,000 sequences (estimated from the line count, 1,247,593,728 lines × 50% header density)
**Format**: simplified header lines:
```
>MGYP000000077819
>MGYP000000184299 FL=1
```
**Characteristics**: metagenomic data containing a large number of predicted proteins of unknown function. Some sequences carry the `FL=1` flag (full length).
**Sequence length distribution**: samples show lengths ranging from tens to hundreds of aa, and the proportion of short sequences may be higher than in UniProt.

**Why MGnify is valuable**:
- A metagenomic origin means greater sequence diversity
- Entirely new families of functional peptides may be hidden in uncultured microorganisms
- Short-sequence clusters (those that cannot be mapped to known full-length proteins) may be independent functional domains

---

## 2. CD-HIT Redundancy Removal Strategy

### What CD-HIT Is

CD-HIT is a widely used sequence clustering tool. It works as follows:

1. Sort all sequences by length (from longest to shortest)
2. Take the longest sequence as the representative of the first cluster
3. For each subsequent sequence, compare it against the existing representative sequences
4. If the similarity exceeds the threshold, assign it to that cluster; otherwise create a new cluster
5. Output: the list of cluster representative sequences (the longest one) and the clustering information

### Parameter Choices and Challenges

For deduplicating short peptides (3-30 aa), pay special attention to the following:

| Parameter | Suggested value | Rationale |
|------|--------|------|
| `-c` (similarity threshold) | 0.95 - 1.00 | Short sequences carry little information themselves; a 90% threshold would cluster functionally different short peptides together |
| `-n` (word size) | 5 | Short sequences need shorter words to match |
| `-d` (description length) | 0 | Do not truncate descriptions |
| `-p` (parallel) | 32 threads | Make full use of the multi-core CPU |
| `-M` (memory limit) | 0 (unlimited) | 128G of memory is enough |

**Key issue**: CD-HIT's clustering behavior on short sequences must be validated on real data. We need to:
1. Sample 100k sequences from each of the two databases
2. Compare different `-c` values (0.90, 0.95, 0.98, 1.00)
3. Observe the fraction of representative sequences after clustering and the loss of sequence diversity
4. Determine the optimal parameter combination

If CD-HIT performs poorly on short peptides (over-clustering), the fallback is to do 100% exact deduplication first (remove identical sequences) and then use MMseqs2 for more sensitive clustering.

### Execution Order

```
Raw FASTA
  ↓
Step 1: Extract all 3-30 aa sequences (reduces the CD-HIT input volume)
  ↓
Step 2: CD-HIT clustering for redundancy removal
  ↓
Step 3: Second 3-30 aa filter (representative sequences chosen by CD-HIT may exceed 30 aa)
  ↓
Step 4: Non-standard amino acid filter (keep only the 20 standard amino acids)
  ↓
Output: candidate peptide pool
```

## 3. The 3-30 aa Length Filter

### Why 3-30 aa

This is jointly determined by the machine learning models we use:

| Service | Lower input length bound | Upper input length bound |
|------|------------|------------|
| AnOxPePred | 3 aa | 50 aa |
| BepiPred-3.0 | 5 aa | 50 aa |
| pLM4CPPs | 7 aa | 30 aa |
| GraphCPP | 5 aa | 30 aa |
| ToxinPred3 | 8 aa | 30 aa |
| HemoPI2 | 5 aa | 50 aa |
| MHCflurry | 8 aa | 14 aa |

We use **3-30 aa** as the unified filter range to ensure that every model can handle the input.

### Implementation

```
Iterate over the FASTA file:
  1. Read the header
  2. Read the sequence (may span multiple lines)
  3. Concatenate all lines, strip whitespace and newline characters
  4. Check the length:
     - len(sequence) < 3 → discard
     - len(sequence) > 30 → discard (longer sequences may contain valuable short fragments; for now filter strictly by length)
     - meets the criteria → write to the output file
```

### Estimated Pass Rate

This is the key uncertainty. Based on the known protein length distribution in UniProt:
- Full-length proteins make up the vast majority (>100 aa)
- Short open reading frames (sORFs) and peptides of 3-30 aa account for a very small fraction (estimated <1-5%)

Conservative estimate:
- UniProt pass rate: ~1-3% (~2-6 million)
- MGnify pass rate: ~10-20% (metagenomes contain more short sequences)
- Total passing: **~30 million - 100 million**

### Parallelization Strategy

A 220G FASTA file cannot be loaded into memory and must be processed as a stream:

| Method | Pros | Cons |
|------|------|------|
| Single-threaded sequential scan | Minimal memory footprint | Slow (~1-2 hours for a 220G scan) |
| Split by file offset (`parallel --pipe`) | Fast, no I/O bottleneck | Split points may fall in the middle of a sequence |
| Block reads + multi-threaded processing | Good controllability | Must handle sequence boundaries across blocks |

Recommended approach: use `parallel --pipe --block-size 1G` together with a line-safe sequence reader to split the 220G file into 200+ 1G blocks and process them in parallel.

---

## 4. Intermediate Storage Formats

### Step 1: Raw Filter Output (FASTA Format)

The preprocessed candidate peptide pool stays in FASTA format, but the headers are standardized:

```
>uniprot|sp|P48347-2|14310_ARATH|sequence|MENEREKQVYLAK
>mgy|MGYP000000077819|sequence|MFPTHPFSGVTVPVS
```

A unified format makes provenance tracking and debugging easier.

### Step 2: Writing to the Database

After standardized FASTA parsing, records are written to the DuckDB `candidates` table:

| Field | Type | Description |
|------|------|------|
| candidate_id | BIGINT | Auto-increment primary key |
| source | VARCHAR | "uniprot" or "mgy" |
| source_id | VARCHAR | ID from the original FASTA header |
| header | VARCHAR | Full original header |
| sequence | VARCHAR | Amino acid sequence |
| length | SMALLINT | Sequence length |
| is_standard_aa | BOOLEAN | Whether it contains only standard amino acids |
| original_cluster_id | VARCHAR | Cluster ID assigned by CD-HIT (optional) |

### Step 3: Statistical Report

After preprocessing completes, a data overview report is generated, containing:
- The number of raw sequences per data source
- The number of sequences per length bin (3-5, 6-10, 11-15, 16-20, 21-25, 26-30 aa)
- The number of sequences and clusters after CD-HIT clustering
- The proportion of sequences with non-standard amino acids

---

## 5. Expected Data Reduction

| Step | Operation | Input | Output | Reduction rate |
|------|------|------|------|--------|
| — | Raw sequences | ~500 million | ~500 million | — |
| 0a | 3-30 aa filter | ~500 million | ~30 million - 100 million | 80-94% |
| 0b | CD-HIT redundancy removal | ~30 million - 100 million | ~20 million - 60 million | 30-40% |
| 0c | Standard AA filter | ~20 million - 60 million | ~19 million - 57 million | ~5% |
| **Total** | | **~500 million** | **~20 million - 60 million** | **88-96%** |

The number of candidate peptides that finally enter Stage 1 is expected to be on the order of **20 million to 60 million**.

---

## 6. Alternatives and Risk Assessment

### CD-HIT Performs Poorly on Short Peptides

**Risk**: CD-HIT's clustering accuracy may degrade for short sequences (especially <15 aa), because short sequences carry little k-mer statistical information.

**Alternative 1**: MMseqs2 (faster and more sensitive, especially suited to short-sequence clustering)
**Alternative 2**: exact 100% deduplication only (remove completely identical sequences) without similarity clustering
**Alternative 3**: use Linclust (an MMseqs2 subcommand) for fast clustering first, then CD-HIT for fine clustering

### Insufficient Memory

**Risk**: CD-HIT keeps the index of all sequences in memory. The memory needed for an index of 30 million 3-30 aa sequences must be estimated.

**Mitigation**:
- First bucket by length (3-10, 11-20, 21-30 aa) and cluster each bucket separately
- Each bucket's memory requirement is independent, avoiding loading all sequences at once
- If memory is still insufficient, bucket further or switch to MMseqs2

### Loss of Source Tracking

**Risk**: after multiple rounds of filtering, the final candidate peptides can no longer be traced back to the original database and original sequence.

**Mitigation**: always keep the `source` and `source_id` fields. Include the full provenance path of each candidate peptide in the final report.
