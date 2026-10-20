> **English** | [中文](mhcflurry_guide.zh.md)

# MHCflurry Usage Guide

## Overview

MHCflurry is a deep learning based MHC class I peptide binding affinity prediction tool. This guide provides complete instructions for using MHCflurry, including installation, configuration, prediction, analysis, and troubleshooting.

## Installation and Configuration

### System Requirements

- Python 3.8 or later
- At least 2GB of available memory
- A network connection (to download the pre-trained models)
- About 200MB of disk space (for model storage)

### Installation Steps

1. **Install MHCflurry**:
   ```bash
   pip install mhcflurry
   ```

2. **Install the optional dependencies** (for data analysis and visualization):
   ```bash
   pip install pandas numpy matplotlib seaborn
   ```

3. **Download the pre-trained models**:
   ```bash
   python -c "from mhcflurry.downloads import fetch_models; fetch_models()"
   ```

   Alternatively, they are downloaded automatically on first use in code.

### Verifying the Installation

```python
from mhcflurry import Class1AffinityPredictor

# Create a predictor instance
predictor = Class1AffinityPredictor.load()

# Test prediction
predictions = predictor.predict(
    peptides=["SIINFEKL"],
    alleles=["HLA-A*02:01"]
)

print(f"Installation successful! Predictions: {predictions}")
```

## Core Concepts

### 1. Binding affinity

Binding affinity is expressed in nanomolar (nM) units; lower values indicate stronger binding:
- **< 50 nM**: strong binding
- **50-500 nM**: weak binding
- **> 500 nM**: non-binding

### 2. Percentile rank

The percentile rank indicates where the peptide's binding affinity ranks relative to random peptides:
- **< 0.5%**: extremely strong binding
- **0.5-2%**: strong binding
- **2-10%**: moderate binding
- **> 10%**: weak binding

### 3. Binding class

Automatically classified based on standard thresholds:
- **strong binder**: ≤ 50 nM
- **weak binder**: 50-500 nM
- **non-binder**: > 500 nM

## API Reference

### Main classes

#### Class1AffinityPredictor
The main predictor class, providing all prediction functionality.

```python
from mhcflurry import Class1AffinityPredictor

# Load the predictor
predictor = Class1AffinityPredictor.load()

# Main methods
predictions = predictor.predict(peptides, alleles)  # predict binding affinity
predictions = predictor.predict_to_dataframe(peptides, alleles)  # predict into a DataFrame
percentile_ranks = predictor.predict_percentile_ranks(peptides, alleles)  # predict percentile ranks
```

#### Class1PresentationPredictor
An enhanced predictor that includes antigen processing prediction.

```python
from mhcflurry import Class1PresentationPredictor

predictor = Class1PresentationPredictor.load()
predictions = predictor.predict(peptides, alleles)
```

### Prediction results

Prediction results contain the following fields:

| Field | Type | Description |
|------|------|------|
| peptide | str | peptide sequence |
| allele | str | MHC allele |
| prediction | float | binding affinity (nM) |
| percentile_rank | float | percentile rank |
| prediction_low | float | lower prediction bound (95% confidence interval) |
| prediction_high | float | upper prediction bound (95% confidence interval) |
| presentation_score | float | presentation score (Class1PresentationPredictor only) |
| processing_score | float | processing score (Class1PresentationPredictor only) |

## Usage Examples

### Example 1: basic prediction

```python
from mhcflurry import Class1AffinityPredictor

# Load the predictor
predictor = Class1AffinityPredictor.load()

# Predict a single peptide
peptides = ["SIINFEKL"]
alleles = ["HLA-A*02:01"]

predictions = predictor.predict(peptides, alleles)
print(predictions)
```

### Example 2: batch prediction

```python
from mhcflurry import Class1AffinityPredictor
import pandas as pd

predictor = Class1AffinityPredictor.load()

# Batch predict multiple peptides and alleles
peptides = ["SIINFEKL", "NLVPMVATV", "GILGFVFTL"]
alleles = ["HLA-A*02:01", "HLA-A*01:01"]

# Predict into a DataFrame
df = predictor.predict_to_dataframe(peptides, alleles)
print(df)

# Save the results
df.to_csv("predictions.csv", index=False)
```

### Example 3: using antigen processing prediction

```python
from mhcflurry import Class1PresentationPredictor

predictor = Class1PresentationPredictor.load()

peptides = ["SIINFEKL", "NLVPMVATV"]
alleles = ["HLA-A*02:01"]

# Predictions include processing and presentation scores
predictions = predictor.predict(peptides, alleles)
print(predictions)
```

### Example 4: custom thresholds

```python
from mhcflurry import Class1AffinityPredictor

predictor = Class1AffinityPredictor.load()

# Predict
peptides = ["SIINFEKL", "NLVPMVATV", "GILGFVFTL"]
alleles = ["HLA-A*02:01"]

df = predictor.predict_to_dataframe(peptides, alleles)

# Custom classification thresholds
def classify_affinity(affinity_nM, strong_threshold=50, weak_threshold=500):
    if affinity_nM <= strong_threshold:
        return "strong_binder"
    elif affinity_nM <= weak_threshold:
        return "weak_binder"
    else:
        return "non_binder"

df["binding_class"] = df["prediction"].apply(classify_affinity)
print(df[["peptide", "allele", "prediction", "binding_class"]])
```

## Allele Support

### Common Human HLA Alleles

MHCflurry supports hundreds of MHC class I alleles, including:

#### HLA-A
- HLA-A*02:01 (most common worldwide)
- HLA-A*01:01 (common in Europe)
- HLA-A*03:01 (distributed worldwide)
- HLA-A*11:01 (common in Asia)
- HLA-A*24:02 (most common in Asia)

#### HLA-B
- HLA-B*07:02 (common worldwide)
- HLA-B*08:01 (common in Europe)
- HLA-B*15:01 (distributed worldwide)
- HLA-B*35:01 (common in the Mediterranean region)
- HLA-B*40:01 (common in Asia)

#### HLA-C
- HLA-C*07:02 (most common worldwide)
- HLA-C*04:01 (common in Europe)
- HLA-C*05:01 (common in the Middle East)
- HLA-C*06:02 (common in Asia)

### Other Species

#### Mouse (H-2)
- H-2-Kb
- H-2-Db
- H-2-Kd
- H-2-Dd
- H-2-Ld

#### Rhesus macaque (Mamu)
- Mamu-A1*001
- Mamu-B*001
- Mamu-B*003
- Mamu-B*004

#### Chimpanzee (Patr)
- Patr-A*0101
- Patr-B*0101

### Getting the Supported List

```python
from mhcflurry import Class1AffinityPredictor

predictor = Class1AffinityPredictor.load()
alleles = predictor.supported_alleles

print(f"Total supported alleles: {len(alleles)}")
print("First 20 alleles:")
for i, allele in enumerate(alleles[:20], 1):
    print(f"  {i:2d}. {allele}")
```

## Performance Optimization

### 1. Batch processing

Batch prediction is more efficient than predicting one by one:

```python
# Recommended: batch prediction
predictions = predictor.predict(peptides, alleles)

# Not recommended: predicting one by one
for peptide in peptides:
    prediction = predictor.predict([peptide], alleles)
```

### 2. Reducing the number of alleles

Prediction time is proportional to the number of alleles:

```python
# Efficient: use fewer alleles
predictions = predictor.predict(peptides, ["HLA-A*02:01", "HLA-B*07:02"])

# Inefficient: use a large number of alleles
predictions = predictor.predict(peptides, all_alleles[:50])
```

### 3. Using appropriate data structures

Use lists rather than single values for prediction:

```python
# Correct: use lists
peptides = ["SIINFEKL", "NLVPMVATV"]
alleles = ["HLA-A*02:01"]

# Wrong: use single values (requires extra handling)
peptide = "SIINFEKL"
allele = "HLA-A*02:01"
```

### 4. Memory management

For large-scale predictions, process the data in batches:

```python
def predict_in_batches(peptides, alleles, batch_size=1000):
    results = []
    for i in range(0, len(peptides), batch_size):
        batch = peptides[i:i+batch_size]
        batch_results = predictor.predict(batch, alleles)
        results.extend(batch_results)
    return results

# Large-scale prediction
large_peptide_list = [...]  # 10000 peptides
results = predict_in_batches(large_peptide_list, ["HLA-A*02:01"])
```

## Result Analysis

### Statistical summary

```python
import pandas as pd
import numpy as np

def analyze_predictions(df):
    """Analyze the prediction results"""
    summary = {
        "total_predictions": len(df),
        "strong_binders": len(df[df["prediction"] <= 50]),
        "weak_binders": len(df[(df["prediction"] > 50) & (df["prediction"] <= 500)]),
        "non_binders": len(df[df["prediction"] > 500]),
        "mean_affinity": df["prediction"].mean(),
        "median_affinity": df["prediction"].median(),
        "min_affinity": df["prediction"].min(),
        "max_affinity": df["prediction"].max(),
        "std_affinity": df["prediction"].std(),
    }
    
    # Group statistics by allele
    allele_stats = df.groupby("allele")["prediction"].agg([
        "count", "mean", "median", "min", "max", "std"
    ]).round(2)
    
    return summary, allele_stats

# Example usage
df = predictor.predict_to_dataframe(peptides, alleles)
summary, allele_stats = analyze_predictions(df)

print("Statistical summary:")
for key, value in summary.items():
    print(f"  {key}: {value}")

print("\nAllele statistics:")
print(allele_stats)
```

### Visualization

```python
import matplotlib.pyplot as plt
import seaborn as sns

def visualize_predictions(df, output_path=None):
    """Visualize the prediction results"""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    # 1. Binding affinity distribution
    axes[0, 0].hist(df["prediction"], bins=50, edgecolor='black', alpha=0.7)
    axes[0, 0].axvline(x=50, color='red', linestyle='--', label='strong binder threshold')
    axes[0, 0].axvline(x=500, color='orange', linestyle='--', label='weak binder threshold')
    axes[0, 0].set_xlabel("Binding affinity (nM)")
    axes[0, 0].set_ylabel("Frequency")
    axes[0, 0].set_title("Binding affinity distribution")
    axes[0, 0].legend()
    axes[0, 0].set_xscale('log')
    
    # 2. Binding class pie chart
    binding_classes = []
    for affinity in df["prediction"]:
        if affinity <= 50:
            binding_classes.append("strong binder")
        elif affinity <= 500:
            binding_classes.append("weak binder")
        else:
            binding_classes.append("non-binder")
    
    class_counts = pd.Series(binding_classes).value_counts()
    axes[0, 1].pie(class_counts.values, labels=class_counts.index, autopct='%1.1f%%')
    axes[0, 1].set_title("Binding class distribution")
    
    # 3. Allele box plot
    if len(df["allele"].unique()) > 1:
        sns.boxplot(data=df, x="allele", y="prediction", ax=axes[1, 0])
        axes[1, 0].set_yscale('log')
        axes[1, 0].set_xlabel("Allele")
        axes[1, 0].set_ylabel("Binding affinity (nM)")
        axes[1, 0].set_title("Allele comparison")
        axes[1, 0].tick_params(axis='x', rotation=45)
    
    # 4. Peptide length scatter plot
    df["peptide_length"] = df["peptide"].apply(len)
    axes[1, 1].scatter(df["peptide_length"], df["prediction"], alpha=0.6)
    axes[1, 1].set_xlabel("Peptide length")
    axes[1, 1].set_ylabel("Binding affinity (nM)")
    axes[1, 1].set_title("Relationship between peptide length and binding affinity")
    axes[1, 1].set_yscale('log')
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Visualization saved to: {output_path}")
    
    plt.show()

# Example usage
visualize_predictions(df, "mhcflurry_visualization.png")
```

## Troubleshooting

### Common issues

#### Q1: MHCflurry installation fails
**Error**: `pip install mhcflurry` fails
**Solution**:
```bash
# Upgrade pip
pip install --upgrade pip

# Use the Tsinghua mirror
pip install mhcflurry -i https://pypi.tuna.tsinghua.edu.cn/simple

# Or use conda
conda install -c bioconda mhcflurry
```

#### Q2: Model download fails
**Error**: the model download fails on first use
**Solution**:
```bash
# Manual download
python -c "from mhcflurry.downloads import fetch_models; fetch_models()"

# Or specify a mirror
python -c "from mhcflurry.downloads import fetch_models; fetch_models(mirror='https://github.com')"
```

#### Q3: Prediction is slow
**Problem**: prediction is slow when scoring large amounts of data
**Solution**:
1. Use batch prediction instead of single predictions
2. Reduce the number of alleles predicted at the same time
3. Use more powerful hardware
4. Consider GPU acceleration (if available)

#### Q4: Out of memory
**Problem**: out of memory when predicting large amounts of data
**Solution**:
1. Reduce the batch size
2. Process the data in batches
3. Add system memory
4. Use streaming

#### Q5: Allele not supported
**Error**: `ValueError: Unsupported allele`
**Solution**:
```python
# Check the supported alleles
alleles = predictor.supported_alleles
print(f"Supported alleles: {alleles}")

# Use a supported allele
if "HLA-A*02:01" in alleles:
    predictions = predictor.predict(peptides, ["HLA-A*02:01"])
```

### Error handling example

```python
from mhcflurry import Class1AffinityPredictor

try:
    # Try to load the predictor
    predictor = Class1AffinityPredictor.load()
    
    # Try to predict
    predictions = predictor.predict(["SIINFEKL"], ["HLA-A*02:01"])
    
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure MHCflurry is installed: pip install mhcflurry")
    
except ValueError as e:
    print(f"Value error: {e}")
    print("Check the peptide sequence or allele format")
    
except RuntimeError as e:
    print(f"Runtime error: {e}")
    print("Check whether the model files exist")
    
except Exception as e:
    print(f"Unknown error: {e}")
    print("See the MHCflurry documentation or report the issue")
```

## Advanced Usage

### Custom models

```python
from mhcflurry import Class1AffinityPredictor

# Load the model from a custom path
predictor = Class1AffinityPredictor.load("/path/to/custom/models")

# Or train a custom model
# predictor.train(training_data, ...)
```

### Integration into a workflow

```python
def vaccine_candidate_pipeline(fasta_file, alleles, output_dir):
    """Vaccine candidate peptide screening pipeline"""
    import os
    from Bio import SeqIO
    
    # 1. Read peptide sequences from FASTA
    peptides = []
    for record in SeqIO.parse(fasta_file, "fasta"):
        peptides.append(str(record.seq))
    
    # 2. Initialize the predictor
    predictor = Class1AffinityPredictor.load()
    
    # 3. Batch prediction
    df = predictor.predict_to_dataframe(peptides, alleles)
    
    # 4. Filter strong binders
    strong_binders = df[df["prediction"] <= 50].copy()
    
    # 5. Sort by affinity
    strong_binders = strong_binders.sort_values("prediction")
    
    # 6. Save the results
    os.makedirs(output_dir, exist
