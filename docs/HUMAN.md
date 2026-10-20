> **English** | [中文](HUMAN.zh.md)

# HUMAN.md

This document mainly records the tools and methods that researchers can use manually in this project, **outside our core business pipeline**.

The use of such tools/methods has the following characteristics:

- **Methods from a human perspective**. These tools are provided for human use and are used in a human way of thinking; they may embody how humans read operational information and how they think. For example, a tool on a website that is operated through a UI. The counterexample is a tool that can only be executed by scripts and code.
- **Small-scale comparison**. Because the number of researchers is limited and their time is limited, they can inevitably conduct detailed synthetic biology research only on part of the final machine-screening results. These tools help researchers study peptides faster and more nimbly using biological thinking.



# TOOLS

### Functional peptide design:

- Binding ddG performs single-point mutation scanning (alanine scanning) on the key residues of a functional peptide to identify the critical activity sites, for use in the later optimization stage
- GROMACS MD simulates the trajectory of the peptide moving in solution, from which its stability and exposure can be analyzed
