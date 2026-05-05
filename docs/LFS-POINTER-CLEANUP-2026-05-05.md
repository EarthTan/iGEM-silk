# LFS Pointer Cleanup Log

**Date:** 2026-05-05
**Reason:** Cloud LFS storage objects missing (404 error)

## Deleted Files

### Models (3 files)
| File | OID | Size (pointer) |
|------|-----|----------------|
| `pLM4CPPs-main/models/ESM2-640/best_model_640.h5` | f14ee131ba... | 134 bytes |
| `pLM4CPPs-main/models/Port-T5-BFD/best_model_1024-bfd.h5` | 62321769c6... | 134 bytes |
| `pLM4CPPs-main/models/SeqVec/best_model_1024-seqvec.h5` | 5d8a035106... | 134 bytes |

### Embedded Data (7 files)
| File | OID | Size (pointer) |
|------|-----|----------------|
| `pLM4CPPs-main/embedded_data/kelm_dataset.csv` | b2d8c893bc... | 129 bytes |
| `pLM4CPPs-main/embedded_data/prot_t5_xl_bfd_per_protein_embeddings.csv` | 642cc9056b... | 133 bytes |
| `pLM4CPPs-main/embedded_data/seqvev_whole_smaple_reduced_embeddings_file_ordered.csv` | daf59488a3... | 133 bytes |
| `pLM4CPPs-main/embedded_data/whole_sample_dataset_esm2_t12_35M_UR50D_unified_480_dimension.csv` | 9f4e9b3c29... | 133 bytes |
| `pLM4CPPs-main/embedded_data/whole_sample_dataset_esm2_t30_150M_UR50D_unified_640_dimension.csv` | 46ae006479... | 133 bytes |
| `pLM4CPPs-main/embedded_data/whole_sample_dataset_esm2_t33_650M_UR50D_unified_1280_dimension.csv` | 14d543ba38... | 134 bytes |
| `pLM4CPPs-main/embedded_data/whole_sample_dataset_esm2_t6_8M_UR50D_unified_320_dimension.csv` | 2f8f3a1466... | 133 bytes |

### Removed Empty Directories
- `pLM4CPPs-main/models/ESM2-640/`
- `pLM4CPPs-main/models/Port-T5-BFD/`
- `pLM4CPPs-main/models/SeqVec/`

## Gitattributes Updated

Removed LFS tracking for missing files. Now only tracks:
```
models/ESM2-320/*.h5 filter=lfs diff=lfs merge=lfs -text
models/ESM2-480/*.h5 filter=lfs diff=lfs merge=lfs -text
```

## Impact

- **ESM2-320**: Available (32MB real file)
- **ESM2-480**: Available (47MB real file)
- **ESM2-640**: Unavailable (LFS object missing)
- **Port-T5-BFD**: Unavailable (LFS object missing)
- **SeqVec**: Unavailable (LFS object missing)

Core CPP prediction functionality unaffected (uses ESM2-320 by default).