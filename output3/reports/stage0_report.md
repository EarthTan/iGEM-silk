> **English** | [中文](stage0_report.zh.md)

# Stage 0 Preprocessing Report

> Generated: 2026-05-17 02:59:44

## Summary

| Metric | Value |
|------|-----|
| Total candidate pool | 19,890,021 |
| UniProt scanned | 225,619,586 |
| UniProt written | 733,573 |
| MGnify scanned | 623,796,864 |
| MGnify written | 19,156,448 |
| Total duration | 5924s |
| Filter range | 3-30 aa |

## Per-Source Statistics

| Source | Entries | Min length | Max length | Mean length |
|--------|--------|---------|---------|---------|
| mgy | 19,156,448 | 4 | 30 | 25.4 |
| uniprot | 733,573 | 3 | 30 | 22.5 |

## Length Distribution

| Length | Count |
|------|------|
| 3 | 5 █ |
| 4 | 24 █ |
| 5 | 40 █ |
| 6 | 33 █ |
| 7 | 223 █ |
| 8 | 11,107 █ |
| 9 | 16,160 █ |
| 10 | 17,663 █ |
| 11 | 14,835 █ |
| 12 | 38,375 █ |
| 13 | 13,294 █ |
| 14 | 14,316 █ |
| 15 | 15,068 █ |
| 16 | 20,050 █ |
| 17 | 19,952 █ |
| 18 | 19,265 █ |
| 19 | 21,381 █ |
| 20 | 974,672 █████████████████ |
| 21 | 1,626,128 █████████████████████████████ |
| 22 | 1,685,486 ██████████████████████████████ |
| 23 | 1,737,195 ███████████████████████████████ |
| 24 | 1,781,590 ████████████████████████████████ |
| 25 | 1,810,758 ████████████████████████████████ |
| 26 | 1,879,227 ██████████████████████████████████ |
| 27 | 1,911,595 ██████████████████████████████████ |
| 28 | 1,944,134 ███████████████████████████████████ |
| 29 | 2,198,924 ████████████████████████████████████████ |
| 30 | 2,118,521 ██████████████████████████████████████ |

## Pre-Filtering Details

| Stage | Count |
|------|------|
| UniProt raw sequences | 225,619,586 |
| UniProt passing length (3-30aa) | 744,565 |
| UniProt passing AA filter | 733,573 |
| UniProt written after deduplication | 733,573 |
| UniProt duplicates skipped | 0 |
| MGnify raw sequences | 623,796,864 |
| MGnify passing length (3-30aa) | 19,156,521 |
| MGnify passing AA filter | 19,156,448 |
| MGnify written after deduplication | 19,156,448 |
| MGnify duplicates skipped | 0 |
