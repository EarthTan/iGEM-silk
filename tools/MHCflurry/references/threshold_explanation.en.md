> English translation of [threshold_explanation.md](threshold_explanation.md). The Chinese original is kept unchanged as the source of truth.

# MHCflurry Binding Class Thresholds Explained

## Overview

This document explains in detail the binding class thresholds used in MHCflurry, including their definitions, biological significance, application scenarios, and customization methods. A correct understanding of these thresholds is essential for accurately interpreting prediction results.

## Standard Thresholds

### Default Thresholds

MHCflurry uses the following standard thresholds to classify binding affinity:

| Binding class | Threshold range (nM) | Description |
|----------|---------------|------|
| **Strong binder** | ≤ 50 nM | High-affinity binding, may trigger a strong T-cell response |
| **Weak binder** | 50-500 nM | Moderate-affinity binding, may trigger a weaker T-cell response |
| **Non-binder** | > 500 nM | Low-affinity binding, unlikely to trigger a T-cell response |

### Biological Basis for the Thresholds

These thresholds are based on immunological research and experimental data:

1. **50 nM threshold**:
   - Based on T-cell activation experiments: peptides with affinity below 50 nM generally activate T cells effectively
   - Immunodominant epitope studies: most immunodominant epitopes have affinity below 50 nM
   - Vaccine design standards: candidate vaccine peptides are usually required to have affinity below 50 nM

2. **500 nM threshold**:
   - Based on the lower limit of T-cell recognition: peptides with affinity above 500 nM generally cannot activate T cells effectively
   - Negative control standards: negative control peptides in experiments usually have affinity above 500 nM
   - Background binding level: a typical threshold for nonspecific binding

## Detailed Threshold Explanation

### Strong Binders (≤ 50 nM)

#### Biological Characteristics
- **High-affinity binding**: the peptide binds to the MHC molecule very stably
- **Effective T-cell activation**: can effectively activate CD8+ T cells
- **High immunogenicity**: very likely to trigger an immune response in vivo
- **High epitope likelihood**: very likely to be an immunodominant epitope

#### Application Scenarios
1. **Vaccine design**: preferentially select strong binders as vaccine candidates
2. **Tumor neoantigen prediction**: strong binders are more likely to be effective neoantigens
3. **Diagnostic reagent development**: strong binders are suitable as diagnostic antigens
4. **Immunology research**: strong binders are ideal models for studying T-cell recognition

#### Example
```python
# Strong binder examples
strong_binders = [
    ("SIINFEKL", "HLA-A*02:01", 25.5),    # 25.5 nM
    ("NLVPMVATV", "HLA-A*02:01", 12.3),   # 12.3 nM
    ("GILGFVFTL", "HLA-A*02:01", 8.7),    # 8.7 nM
]
```

### Weak Binders (50-500 nM)

#### Biological Characteristics
- **Moderate-affinity binding**: the peptide binds to the MHC molecule with moderate stability
- **Partial T-cell activation**: may activate T cells, but with lower efficiency
- **Moderate immunogenicity**: may trigger an immune response under specific conditions
- **Moderate epitope likelihood**: may be a subdominant epitope

#### Application Scenarios
1. **Secondary candidate screening**: consider weak binders when strong binders are insufficient
2. **Breadth-first strategy**: include weak binders in order to cover more epitopes
3. **Research use**: study the relationship between affinity and immunogenicity
4. **Combination therapy**: use in combination with other immunomodulators

#### Example
```python
# Weak binder examples
weak_binders = [
    ("RAKFKQLL", "HLA-A*02:01", 150.2),   # 150.2 nM
    ("CINGVCWTV", "HLA-A*02:01", 320.5),  # 320.5 nM
    ("YVLDHLIVV", "HLA-A*02:01", 480.3),  # 480.3 nM
]
```

### Non-Binders (> 500 nM)

#### Biological Characteristics
- **Low-affinity binding**: the peptide binds to the MHC molecule unstably
- **Ineffective T-cell activation**: usually cannot activate T cells
- **Low immunogenicity**: unlikely to trigger an immune response in vivo
- **Non-epitope**: very likely a non-immunogenic peptide

#### Application Scenarios
1. **Negative control**: negative controls in experiments
2. **Specificity validation**: validate the specificity of prediction tools
3. **Background assessment**: assess the experimental background level
4. **Exclusion criterion**: exclude from candidate lists

#### Example
```python
# Non-binder examples
non_binders = [
    ("AAAAAAAA", "HLA-A*02:01", 1250.8),  # 1250.8 nM
    ("PPPPPPPP", "HLA-A*02:01", 980.3),   # 980.3 nM
    ("RRRRRRRR", "HLA-A*02:01", 750.6),   # 750.6 nM
]
```

## Percentile Rank Thresholds

In addition to absolute affinity thresholds, MHCflurry also provides percentile ranks, another important classification metric:

### Percentile Rank Thresholds

| Percentile rank | Category | Description |
|------------|------|------|
| **< 0.5%** | Extremely strong binding | Affinity within the top 0.5% |
| **0.5-2%** | Strong binding | Affinity within the top 0.5-2% |
| **2-10%** | Moderate binding | Affinity within the top 2-10% |
| **> 10%** | Weak binding | Affinity within the bottom 90% |

### Advantages of Percentile Ranks

1. **Allele normalization**: accounts for differences in binding distributions across alleles
2. **Relative comparison**: ranking relative to random peptides is more biologically relevant
3. **Stability**: better robustness to experimental variability

### Usage Example

```python
def classify_by_percentile(percentile_rank):
    """Classify by percentile rank"""
    if percentile_rank < 0.005:  # 0.5%
        return "extremely_strong"
    elif percentile_rank < 0.02:  # 2%
        return "strong"
    elif percentile_rank < 0.10:  # 10%
        return "moderate"
    else:
        return "weak"

# Example data
samples = [
    ("SIINFEKL", 0.001),   # 0.1%
    ("NLVPMVATV", 0.008),  # 0.8%
    ("GILGFVFTL", 0.015),  # 1.5%
    ("RAKFKQLL", 0.050),   # 5.0%
    ("AAAAAAAA", 0.850),   # 85.0%
]

for peptide, percentile in samples:
    category = classify_by_percentile(percentile)
    print(f"{peptide}: {percentile:.3f} → {category}")
```

## Custom Thresholds

### Why Custom Thresholds Are Needed

In some application scenarios, the standard thresholds may not be applicable:

1. **Specific disease research**: certain diseases may require stricter or looser thresholds
2. **Differences in experimental conditions**: different experimental systems may require adjusted thresholds
3. **Conservative strategy**: a more conservative screening strategy requires stricter thresholds
4. **Breadth-first strategy**: covering more possibilities requires looser thresholds

### Custom Threshold Methods

#### Method 1: Classify Directly with Thresholds

Use the standard Class1AffinityPredictor and apply custom thresholds after prediction:

```python
from mhcflurry import Class1AffinityPredictor

# Load the predictor
predictor = Class1AffinityPredictor.load()

# Predict
df = predictor.predict_to_dataframe(
    peptides=["SIINFEKL", "NLVPMVATV"],
    alleles=["HLA-A*02:01"]
)

# Custom classification thresholds
custom_strong_threshold = 100.0   # Relax the strong binder threshold
custom_weak_threshold = 1000.0    # Relax the weak binder threshold

def classify_with_custom_threshold(affinity_nM, strong=50.0, weak=500.0):
    """Classification function using custom thresholds"""
    if affinity_nM <= strong:
        return "strong_binder"
    elif affinity_nM <= weak:
        return "weak_binder"
    else:
        return "non_binder"

# Apply the custom thresholds
df["custom_class"] = df["prediction"].apply(
    lambda x: classify_with_custom_threshold(x, custom_strong_threshold, custom_weak_threshold)
)
print(df)
```

#### Method 2: Post-Processing Classification

```python
def custom_classify(affinity_nM, thresholds):
    """Custom classification function"""
    strong_thresh = thresholds.get("strong", 50.0)
    weak_thresh = thresholds.get("weak", 500.0)
    
    if affinity_nM <= strong_thresh:
        return "strong_binder"
    elif affinity_nM <= weak_thresh:
        return "weak_binder"
    else:
        return "non_binder"

# Usage example
custom_thresholds = {"strong": 100.0, "weak": 1000.0}
affinity = 75.0  # nM
category = custom_classify(affinity, custom_thresholds)
print(f"Affinity {affinity} nM: {category}")  # Output: strong_binder
```

#### Method 3: Thresholds Based on Percentile Rank

```python
def classify_by_percentile_custom(percentile_rank, thresholds):
    """Custom classification based on percentile rank"""
    extremely_strong = thresholds.get("extremely_strong", 0.005)  # 0.5%
    strong = thresholds.get("strong", 0.02)  # 2%
    moderate = thresholds.get("moderate", 0.10)  # 10%
    
    if percentile_rank < extremely_strong:
        return "extremely_strong"
    elif percentile_rank < strong:
        return "strong"
    elif percentile_rank < moderate:
        return "moderate"
    else:
        return "weak"

# Usage example
custom_percentile_thresholds = {
    "extremely_strong": 0.01,  # 1%
    "strong": 0.05,            # 5%
    "moderate": 0.20           # 20%
}

percentile = 0.03  # 3%
category = classify_by_percentile_custom(percentile, custom_percentile_thresholds)
print(f"Percentile rank {percentile:.3f}: {category}")  # Output: strong
```

### Application-Specific Threshold Recommendations

#### Vaccine Design
```python
vaccine_thresholds = {
    "strong_binder": 50.0,     # Strict standard to ensure high immunogenicity
    "weak_binder": 200.0,      # Moderate standard, allowing secondary candidates
    "percentile_strong": 0.01, # Top 1%
    "percentile_weak": 0.05    # Top 5%
}
```

#### Tumor Neoantigen Prediction
```python
neoantigen_thresholds = {
    "strong_binder": 100.0,    # Slightly relaxed to account for mutation specificity
    "weak_binder": 500.0,      # Standard
    "percentile_strong": 0.02, # Top 2%
    "percentile_weak": 0.10    # Top 10%
}
```

#### Diagnostic Reagent Development
```python
diagnostic_thresholds = {
    "strong_binder": 20.0,     # Very strict to ensure high specificity
    "weak_binder": 100.0,      # Strict
    "percentile_strong": 0.005, # Top 0.5%
    "percentile_weak": 0.02    # Top 2%
}
```

#### Basic Research
```python
research_thresholds = {
    "strong_binder": 500.0,    # Relaxed, to include more samples
    "weak_binder": 5000.0,     # Very relaxed
    "percentile_strong": 0.10, # Top 10%
    "percentile_weak": 0.50    # Top 50%
}
```

## Threshold Validation

### Experimental Validation Methods

1. **ELISA binding assay**: directly measure peptide-MHC binding affinity
2. **T-cell activation assay**: measure the T-cell response induced by the peptide
3. **MHC multimer staining**: detect peptide-specific T cells
4. **Immunized animal experiments**: evaluate the in vivo immunogenicity of the peptide

### Validation Dataset

Use a dataset of known immunogenic peptides to validate the thresholds:

```python
def validate_thresholds(validation_data, thresholds):
    """Validate threshold performance on a known dataset"""
    true_positives = 0
    false_positives = 0
    true_negatives = 0
    false_negatives = 0
    
    for peptide, affinity, is_immunogenic in validation_data:
        # Classify using the thresholds
        if affinity <= thresholds["strong_binder"]:
            predicted_immunogenic = True
        else:
            predicted_immunogenic = False
        
        # Tally
        if is_immunogenic and predicted_immunogenic:
            true_positives += 1
        elif not is_immunogenic and predicted_immunogenic:
            false_positives += 1
        elif not is_immunogenic and not predicted_immunogenic:
            true_negatives += 1
        elif is_immunogenic and not predicted_immunogenic:
            false_negatives += 1
    
    # Compute performance metrics
    sensitivity = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    specificity = true_negatives / (true_negatives + false_positives) if (true_negatives + false_positives) > 0 else 0
    accuracy = (true_positives + true_negatives) / len(validation_data)
    
    return {
        "sensitivity": sensitivity,
        "specificity": specificity,
        "accuracy": accuracy,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "true_negatives": true_negatives,
        "false_negatives": false_negatives
    }
```

### Threshold Optimization

Use grid search to optimize the thresholds:

```python
import numpy as np

def optimize_thresholds(validation_data):
    """Optimize the binding class thresholds"""
    best_accuracy = 0
    best_thresholds = {"strong": 50.0, "weak": 500.0}
    
    # Grid search
    strong_candidates = np.arange(10, 200, 10)  # 10-200 nM
    weak_candidates = np.arange(100, 1000, 50)  # 100-1000 nM
    
    for strong_thresh in strong_candidates:
        for weak_thresh in weak_candidates:
            if weak_thresh <= strong_thresh:
                continue  # The weak threshold must be greater than the strong threshold
            
            thresholds = {"strong": strong_thresh, "weak": weak_thresh}
            performance = validate_thresholds(validation_data, thresholds)
            
            if performance["accuracy"] > best_accuracy:
                best_accuracy = performance["accuracy"]
                best_thresholds = thresholds
    
    return best_thresholds, best_accuracy
```

## Threshold Selection Guide

### When to Use the Standard Thresholds

1. **Standard immunological research**: use the default thresholds (50/500 nM)
2. **Comparison with the literature**: use field-standard thresholds to ensure comparability
3. **Preliminary screening**: use conservative thresholds to reduce false positives
4. **Teaching purposes**: standard thresholds are easier to understand

### When to Use Custom Thresholds

1. **Specific disease research**: adjust thresholds according to disease characteristics
2. **Experimental validation**: optimize thresholds for the experimental system
3. **High-throughput screening**: use relaxed thresholds to increase the number of candidates
4. **Precision medicine**: personalize thresholds according to patient characteristics

### Threshold Selection Decision Tree

```
Start
  ↓
Do you need to compare with existing research?
  ├─ Yes → Use the standard thresholds from the literature
  └─ No → Do you have experimental validation data?
        ├─ Yes → Optimize the thresholds based on validation data
        └─ No → What is the application scenario?
              ├─ Vaccine design → Use strict thresholds (≤50 nM)
              ├─ Tumor neoantigen → Use moderate thresholds (≤100 nM)
              ├─ Diagnostic development → Use very strict thresholds (≤20 nM)
              └─ Basic research → Use relaxed thresholds (≤500 nM)
```

## FAQ

### Q1: Why use 50 nM as the strong binder threshold?

**A**: The 50 nM threshold is based on a large body of experimental data:
- T-cell activation experiments show that peptides with affinity below 50 nM effectively activate T cells
- Immunodominant epitopes usually have affinity below 50 nM
- Vaccine design standards usually require candidate peptides to have affinity below 50 nM
- This threshold provides a good balance between sensitivity and specificity

### Q2: Which matters more, percentile rank or absolute affinity?

**A**: Both matter, but they serve different purposes:
- **Absolute affinity**: suitable for cross-allele comparisons and absolute threshold applications
- **Percentile rank**: suitable for within-allele comparisons and relative assessment
- **Recommendation**: consider both, and prefer percentile rank for allele-normalized comparisons

### Q3: How do I choose thresholds for a specific application?

**A**: Follow these steps:
1. Clarify the application goal (vaccine design, diagnostic development, etc.)
2. Consult the relevant literature for field standards
3. If experimental data are available, optimize the thresholds based on the data
4. Consider the cost of false positives and false negatives
5. Start from conservative thresholds and adjust as needed

### Q4: Do the thresholds apply to all alleles?

**A**: The standard thresholds (50/500 nM) were established based on common alleles (such as HLA-A*02:01). For rare alleles:
- Absolute thresholds may not fully apply
- Percentile ranks are recommended for normalization
- If possible, adjust the thresholds based on allele-specific data

### Q5: How do I validate the effectiveness of thresholds?

**A**: Use the following methods:
1. Collect experimental data for known immunogenic peptides
2. Compute performance metrics for the thresholds on these data
3. Compare the performance of different thresholds
4. Choose the threshold with the best balance between sensitivity and specificity
5. Validate on an independent dataset

## Summary

MHCflurry's binding class thresholds are practical tools established on the basis of immunological research and experimental data. Correctly understanding and using these thresholds is essential for accurate
