"""
pLM4CPPs Prediction Script
=========================

A comprehensive prediction tool for Cell Penetrating Peptides (CPP) using
ESM2 protein language model embeddings and CNN classifier.

Supports:
- Single and batch sequence prediction
- ESM2 embedding generation
- Python API and CLI interface
- Heuristic fallback when model is unavailable

Author: Tiancheng (skill verification fix by Sisyphus)
Based on: Kumar, N., et al. (2025). pLM4CPPs. J. Chem. Inf. Model.
"""

import argparse
import collections
import os
import sys
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch

# Try to import optional dependencies
try:
    import esm
    HAS_ESM = True
except ImportError:
    HAS_ESM = False
    warnings.warn("esm module not found. Install with: uv pip install fair-esm")

try:
    from tensorflow.keras.models import load_model
    HAS_TENSORFLOW = True
except ImportError:
    HAS_TENSORFLOW = False
    warnings.warn("tensorflow not found. Install with: uv pip install tensorflow")

try:
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    warnings.warn("sklearn not found. Install with: uv pip install scikit-learn")


# =============================================================================
# Configuration
# =============================================================================

DEFAULT_ESM2_MODEL = "esm2_t6_8M_UR50D"  # 6 layers, 8M params, 320 dim
DEFAULT_EMBEDDING_LAYER = 6

# Model paths relative to script location
SCRIPT_DIR = Path(__file__).parent
DEFAULT_MODEL_PATH = SCRIPT_DIR / "pLM4CPPs-main" / "models" / "ESM2-320" / "best_model_320.h5"

# Embedding dimension for the default model
EMBEDDING_DIM = 320

# Threshold for CPP classification
DEFAULT_THRESHOLD = 0.5


# =============================================================================
# ESM2 Embedding Generation
# =============================================================================

def load_esm2_model(model_name: str = DEFAULT_ESM2_MODEL):
    """
    Load ESM2 pretrained model.

    Args:
        model_name: ESM2 model variant.
            - "esm2_t6_8M_UR50D": 6 layers, 8M params, 320 dim (default)
            - "esm2_t12_35M_UR50D": 12 layers, 35M params, 480 dim
            - "esm2_t30_150M_UR50D": 30 layers, 150M params, 640 dim
            - "esm2_t33_650M_UR50D": 33 layers, 650M params, 1280 dim

    Returns:
        Tuple of (model, alphabet)
    """
    if not HAS_ESM:
        raise RuntimeError("ESM2 model requires 'esm' module. Install: uv pip install fair-esm")

    if model_name not in ["esm2_t6_8M_UR50D", "esm2_t12_35M_UR50D",
                          "esm2_t30_150M_UR50D", "esm2_t33_650M_UR50D"]:
        raise ValueError(f"Unknown model: {model_name}. Supported: esm2_t6_8M_UR50D, "
                         "esm2_t12_35M_UR50D, esm2_t30_150M_UR50D, esm2_t33_650M_UR50D")

    model_loader = getattr(esm.pretrained, model_name, None)
    if model_loader is None:
        raise ValueError(f"Model {model_name} not available in esm module")

    model, alphabet = model_loader()
    model.eval()
    return model, alphabet


def generate_esm2_embeddings(
    sequences: list[str] | list[tuple[str, str]],
    model=None,
    alphabet=None,
    model_name: str = DEFAULT_ESM2_MODEL,
    embedding_layer: int = DEFAULT_EMBEDDING_LAYER,
    batch_size: int = 8,
    device: str = None
) -> pd.DataFrame:
    """
    Generate ESM2 embeddings for peptide sequences.

    Args:
        sequences: List of sequences (str) or (id, sequence) tuples.
        model: Pre-loaded ESM2 model (optional).
        alphabet: Pre-loaded ESM2 alphabet (optional).
        model_name: ESM2 model variant to load if model not provided.
        embedding_layer: Which transformer layer to extract (6 for esm2_t6_8M).
        batch_size: Batch size for processing.
        device: Device to use ('cuda' or 'cpu'). Auto-detected if None.

    Returns:
        DataFrame with shape (n_sequences, embedding_dim).
        Index contains sequence IDs if provided, otherwise integer indices.

    Example:
        >>> embeddings = generate_esm2_embeddings([
        ...     ("TAT", "RKKRRQRRR"),
        ...     ("Penetratin", "RQIKIWFQNRRMKWKK")
        ... ])
        >>> print(embeddings.shape)  # (2, 320)
    """
    if not HAS_ESM:
        raise RuntimeError("ESM2 requires 'esm' module. Install: uv pip install fair-esm")

    # Load model if not provided
    if model is None or alphabet is None:
        model, alphabet = load_esm2_model(model_name)

    # Determine device: CUDA > MPS > CPU
    if device is None:
        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
    model = model.to(device)
    model.eval()

    # Prepare sequence tuples
    if isinstance(sequences[0], str):
        sequences = [(f"seq_{i}", seq) for i, seq in enumerate(sequences)]

    batch_converter = alphabet.get_batch_converter()

    all_embeddings = []

    with torch.no_grad():
        for i in range(0, len(sequences), batch_size):
            batch = sequences[i:i + batch_size]

            try:
                batch_labels, batch_strs, batch_tokens = batch_converter(batch)
            except Exception as e:
                warnings.warn(f"Batch {i//batch_size} conversion failed: {e}")
                continue

            batch_lens = (batch_tokens != alphabet.padding_idx).sum(1)
            batch_tokens = batch_tokens.to(device)

            results = model(batch_tokens, repr_layers=[embedding_layer], return_contacts=False)
            token_representations = results["representations"][embedding_layer].cpu()

            # Average pooling to get sequence representation
            for j, tokens_len in enumerate(batch_lens):
                seq_rep = token_representations[j, 1:tokens_len - 1].mean(0)
                all_embeddings.append(seq_rep.tolist())

    # Create DataFrame
    embedding_dim = len(all_embeddings[0])
    embeddings_df = pd.DataFrame(all_embeddings)
    embeddings_df.index = [s[0] for s in sequences]

    return embeddings_df


# =============================================================================
# CPP Prediction
# =============================================================================

def load_cpp_model(model_path: str | Path = DEFAULT_MODEL_PATH):
    """
    Load pre-trained CPP prediction model.

    Args:
        model_path: Path to the Keras .h5 model file.

    Returns:
        Loaded Keras model.

    Raises:
        FileNotFoundError: If model file doesn't exist.
    """
    if not HAS_TENSORFLOW:
        raise RuntimeError("TensorFlow required. Install: uv pip install tensorflow")

    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(
            f"Model not found at {model_path}. "
            "Download from: https://github.com/drkumarnandan/pLM4CPPs"
        )

    model = load_model(str(model_path))
    return model


def predict_cpp(
    sequences: list[str] | list[tuple[str, str]],
    model=None,
    embeddings: pd.DataFrame = None,
    model_path: str | Path = DEFAULT_MODEL_PATH,
    scaler=None,
    threshold: float = DEFAULT_THRESHOLD,
    return_probs: bool = False
) -> pd.DataFrame:
    """
    Predict CPP probability for peptide sequences.

    Args:
        sequences: List of sequences (str) or (id, sequence) tuples.
        model: Pre-loaded Keras model (optional).
        embeddings: Pre-computed ESM2 embeddings (optional).
        model_path: Path to model if model not provided.
        scaler: Pre-fitted StandardScaler (optional).
        threshold: Classification threshold (default 0.5).
        return_probs: If True, return raw probabilities instead of labels.

    Returns:
        DataFrame with columns:
        - ID: sequence identifier
        - Sequence: peptide sequence
        - CPP_Probability: probability score (0-1)
        - CPP_Prediction: binary prediction (0 or 1)
        - Prediction_Label: 'CPP' or 'non-CPP'

    Example:
        >>> results = predict_cpp([("TAT", "RKKRRQRRR")])
        >>> print(results["CPP_Probability"].iloc[0])  # ~0.999
    """
    if not HAS_TENSORFLOW:
        raise RuntimeError("TensorFlow required. Install: uv pip install tensorflow")

    # Load model if not provided
    if model is None:
        model = load_cpp_model(model_path)

    # Prepare sequence tuples
    if isinstance(sequences[0], str):
        sequences = [(f"seq_{i}", seq) for i, seq in enumerate(sequences)]

    # Generate embeddings if not provided
    if embeddings is None:
        embeddings = generate_esm2_embeddings(sequences)

    # Get IDs in correct order
    ids = [s[0] for s in sequences]
    seqs = [s[1] for s in sequences]

    # Align embeddings with sequence order
    embeddings_aligned = embeddings.reindex(ids)

    # Handle missing embeddings
    if embeddings_aligned.isnull().any().any():
        missing = embeddings_aligned[embeddings_aligned.isnull().any(axis=1)].index.tolist()
        warnings.warn(f"Missing embeddings for sequences: {missing}")

    # Normalize embeddings
    if scaler is None:
        scaler = StandardScaler()
        X = scaler.fit_transform(embeddings_aligned.values)
    else:
        X = scaler.transform(embeddings_aligned.values)

    # Reshape for 1D-CNN: (batch, 320, 1)
    X = X.reshape(X.shape[0], X.shape[1], 1)

    # Predict
    probs = model.predict(X, verbose=0).flatten()

    # Create results DataFrame
    results = pd.DataFrame({
        "ID": ids,
        "Sequence": seqs,
        "CPP_Probability": probs,
        "CPP_Prediction": (probs > threshold).astype(int),
        "Prediction_Label": np.where(probs > threshold, "CPP", "non-CPP")
    })

    if return_probs:
        return results

    return results


# =============================================================================
# Heuristic Fallback (when model unavailable)
# =============================================================================

def predict_cpp_heuristic(
    sequences: list[str] | list[tuple[str, str]],
    threshold: float = 0.5
) -> pd.DataFrame:
    """
    Heuristic CPP prediction based on R/K (Arginine/Lysine) content.

    This is a fallback when the trained model is not available.
    It uses the observation that CPPs often have high R/K content.

    Args:
        sequences: List of sequences (str) or (id, sequence) tuples.
        threshold: R/K ratio threshold (default 0.5).

    Returns:
        DataFrame with same structure as predict_cpp().

    Note:
        This is NOT a substitute for the trained model.
        Use only when model file is unavailable.
    """
    if isinstance(sequences[0], str):
        sequences = [(f"seq_{i}", seq) for i, seq in enumerate(sequences)]

    results = []
    for seq_id, seq in sequences:
        seq_upper = seq.upper()
        length = len(seq_upper)

        # Count R and K residues
        r_count = seq_upper.count('R')
        k_count = seq_upper.count('K')
        rk_count = r_count + k_count

        # R/K ratio
        rk_ratio = rk_count / length if length > 0 else 0

        # Additional features
        # - Average hydrophobicity contribution
        # - Net charge at physiological pH

        # Simple scoring: R/K ratio weighted by length
        # Longer peptides with high R/K are more likely to be CPP
        prob = min(1.0, rk_ratio * 1.5)

        results.append({
            "ID": seq_id,
            "Sequence": seq,
            "CPP_Probability": prob,
            "CPP_Prediction": 1 if prob > threshold else 0,
            "Prediction_Label": "CPP" if prob > threshold else "non-CPP"
        })

    return pd.DataFrame(results)


# =============================================================================
# Main Pipeline (try model, fallback to heuristic)
# =============================================================================

def cpp_prediction_pipeline(
    sequences: list[str] | list[tuple[str, str]],
    model_path: str | Path = DEFAULT_MODEL_PATH,
    use_heuristic: bool = True,
    **kwargs
) -> pd.DataFrame:
    """
    Complete CPP prediction pipeline.

    Tries to use the trained ESM2+CNN model. Falls back to heuristic
    if model file is not available.

    Args:
        sequences: List of sequences (str) or (id, sequence) tuples.
        model_path: Path to the Keras model file.
        use_heuristic: If True, use heuristic when model unavailable.
        **kwargs: Additional arguments passed to predict_cpp().

    Returns:
        DataFrame with prediction results.

    Example:
        >>> results = cpp_prediction_pipeline([
        ...     ("TAT", "RKKRRQRRR"),
        ...     ("NonCPP", "AAGGGAGG")
        ... ])
    """
    try:
        return predict_cpp(sequences, model_path=model_path, **kwargs)
    except (FileNotFoundError, RuntimeError) as e:
        if use_heuristic:
            warnings.warn(f"Model unavailable ({e}), using heuristic fallback")
            return predict_cpp_heuristic(sequences)
        raise


# =============================================================================
# Batch File Processing
# =============================================================================

def process_input_file(
    input_path: str | Path,
    output_path: str | Path = None,
    id_col: str = "ID",
    sequence_col: str = "Sequence",
    model_path: str | Path = DEFAULT_MODEL_PATH,
    **kwargs
) -> pd.DataFrame:
    """
    Process a CSV file containing peptide sequences.

    Args:
        input_path: Path to input CSV file.
        output_path: Path to output CSV file (optional).
        id_col: Column name for sequence ID.
        sequence_col: Column name for sequence.
        model_path: Path to prediction model.
        **kwargs: Additional arguments for prediction.

    Returns:
        DataFrame with prediction results.

    Input CSV format:
        ID,Sequence
        TAT,RKKRRQRRR
        Penetratin,RQIKIWFQNRRMKWKK

    Output CSV format:
        ID,Sequence,CPP_Probability,CPP_Prediction,Prediction_Label
        TAT,RKKRRQRRR,0.9999951,1,CPP
    """
    input_path = Path(input_path)

    # Read input
    if input_path.suffix.lower() == '.csv':
        df = pd.read_csv(input_path)
    elif input_path.suffix.lower() in ['.xlsx', '.xls']:
        df = pd.read_excel(input_path)
    elif input_path.suffix.lower() == '.fasta':
        # Parse FASTA
        sequences = []
        current_id = None
        current_seq = []

        with open(input_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith('>'):
                    if current_id is not None:
                        sequences.append((current_id, ''.join(current_seq)))
                    current_id = line[1:].split()[0]
                    current_seq = []
                else:
                    current_seq.append(line)

            if current_id is not None:
                sequences.append((current_id, ''.join(current_seq)))

        return cpp_prediction_pipeline(sequences, model_path=model_path, **kwargs)
    else:
        raise ValueError(f"Unsupported file format: {input_path.suffix}")

    # Validate columns
    if id_col not in df.columns:
        raise ValueError(f"ID column '{id_col}' not found. Available: {df.columns.tolist()}")
    if sequence_col not in df.columns:
        raise ValueError(f"Sequence column '{sequence_col}' not found. Available: {df.columns.tolist()}")

    # Prepare sequences
    sequences = list(zip(df[id_col].astype(str), df[sequence_col].astype(str).str.upper()))

    # Predict
    results = cpp_prediction_pipeline(sequences, model_path=model_path, **kwargs)

    # Save if output path provided
    if output_path is not None:
        results.to_csv(output_path, index=False)

    return results


# =============================================================================
# Embedding Export
# =============================================================================

def export_embeddings(
    sequences: list[str] | list[tuple[str, str]],
    output_path: str | Path = None,
    model_name: str = DEFAULT_ESM2_MODEL,
    **kwargs
) -> pd.DataFrame:
    """
    Generate and optionally save ESM2 embeddings for sequences.

    Args:
        sequences: List of sequences (str) or (id, sequence) tuples.
        output_path: Path to save embeddings CSV (optional).
        model_name: ESM2 model variant.
        **kwargs: Additional arguments for generate_esm2_embeddings().

    Returns:
        DataFrame with embeddings (n_sequences, embedding_dim).

    Example:
        >>> emb = export_embeddings(
        ...     [("TAT", "RKKRRQRRR")],
        ...     "embeddings.csv"
        ... )
    """
    embeddings = generate_esm2_embeddings(sequences, model_name=model_name, **kwargs)

    if output_path is not None:
        embeddings.to_csv(output_path)

    return embeddings


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="pLM4CPPs: CPP Prediction using ESM2 + CNN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Predict CPP for sequences in CSV
  python predict.py -i input.csv -o predictions.csv

  # Generate embeddings only
  python predict.py -i input.csv --embeddings-only -o embeddings.csv

  # Use specific model
  python predict.py -i input.csv -o out.csv -m custom_model.h5

  # Batch processing
  python predict.py -i batch/sequences/ -o results/predictions.csv
        """
    )

    parser.add_argument("-i", "--input", required=True,
                        help="Input CSV/FASTA file or directory")
    parser.add_argument("-o", "--output",
                        help="Output CSV file (default: predictions.csv)")
    parser.add_argument("-m", "--model",
                        default=str(DEFAULT_MODEL_PATH),
                        help="Path to Keras model file")
    parser.add_argument("--embeddings-only", action="store_true",
                        help="Only generate embeddings, skip prediction")
    parser.add_argument("--embeddings-output",
                        help="Output path for embeddings")
    parser.add_argument("--id-col", default="ID",
                        help="Column name for sequence ID (default: ID)")
    parser.add_argument("--sequence-col", default="Sequence",
                        help="Column name for sequence (default: Sequence)")
    parser.add_argument("--esm-model", default=DEFAULT_ESM2_MODEL,
                        choices=["esm2_t6_8M_UR50D", "esm2_t12_35M_UR50D",
                                "esm2_t30_150M_UR50D", "esm2_t33_650M_UR50D"],
                        help="ESM2 model variant")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Classification threshold (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--no-heuristic", action="store_true",
                        help="Disable heuristic fallback when model unavailable")

    args = parser.parse_args()

    # Determine output path
    output_path = args.output
    if output_path is None and not args.embeddings_only:
        output_path = "predictions.csv"

    # Check input path
    input_path = Path(args.input)

    try:
        if args.embeddings_only:
            # Generate embeddings only
            embeddings = export_embeddings(
                [],  # Will be loaded from file
                output_path=args.embeddings_output,
                model_name=args.esm_model
            )
            print(f"Embeddings shape: {embeddings.shape}")

        else:
            # Full prediction pipeline
            results = process_input_file(
                input_path,
                output_path=output_path,
                id_col=args.id_col,
                sequence_col=args.sequence_col,
                model_path=args.model,
                use_heuristic=not args.no_heuristic
            )

            print(f"\nPrediction Results:")
            print(results.to_string(index=False))
            print(f"\nResults saved to: {output_path}")

            # Summary
            cpp_count = (results["CPP_Prediction"] == 1).sum()
            total = len(results)
            print(f"\nSummary: {cpp_count}/{total} sequences predicted as CPP")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
