> **English** | [中文](PROGRAM%20Old.zh.md)

# **Project Background**

The current mainstream practice in the skincare industry is to simply mix multiple active ingredients (antioxidants, anti-glycation agents, collagen promoters, etc.) into a single product, but this approach has three core problems:

1. **Ingredients lack synergy**, and may even interfere with each other
2. **No penetration mechanism** — most highly effective active ingredients cannot cross the skin surface
3. **Unpredictable stability** — the behavior of complex mixtures is hard to control

Traditional peptide discovery relies on random experiments: high cost, long cycles, and heavy dependence on luck.

# **Project Goals**

The project proposes an **AI-driven modular functional peptide design platform**. The core idea: integrate multiple functions into **a single molecule** rather than simply mixing several ingredients. The user enters the desired effect, and the platform automatically outputs an experimentally validated optimal molecular design. This platform is not only a publicly available tool but can also help wet-lab screening of high-potential peptides.

From the user experience perspective, the platform built in this project will enable the following: the user selects the **two** functions they want (for example, antioxidant + delivery), and the platform automatically finds the **two short peptides** with potential for those two functions, along with all possible **linkers**. It enumerates all possible `short peptide A + linker + short peptide B` combinations and presents the most promising combination to the user.

From the engineering perspective, the computational engineering built in this project needs to deliver two major capabilities:

### **1) Functional prediction scoring for peptides**

We need to train a **model** through machine learning that can do the following: given a specified **peptide (FASTA format, amino acid sequence)** as input, the model outputs a predicted score for that **peptide** on a particular dimension (for example, antioxidant).

Since we need to predict multiple functions, we actually need multiple models, each providing prediction scores for one of six efficacies:

- **Antioxidant & anti-glycation**;
- **Collagen production promotion**;
- **Antibacterial** (especially against acne bacteria);
- **Anti-inflammatory**;
- **Anti-melanogenesis**;
- **Transdermal delivery module**

Specifically, model training is divided into three steps:

1. Raw data acquisition. (For each FASTA sequence, a corresponding binary label: with/without the corresponding function)
2. Feature engineering of the data. (Physicochemical property calculation, amino acid/dipeptide composition calculation, ESM embedding, ...)
3. Model training. (Possible machine learning algorithms: Random Forest, XGBoost, MLP...)

### 2) Fusion engine

The fusion engine needs to enumerate all possible `short peptide A + linker + short peptide B` combinations and push the best ones according to the scenario (injection/topical/patch). Therefore, the fusion engine needs to implement at least the following:

1. Find promising `short peptide A, linkers and short peptide B` and take the full permutation.
2. Filter out obviously unreasonable combinations. (Hard-coded filtering, for example linker length limits, filtering out net charge that is too high or too low...)
3. **Score** each combination. (Penalty for excessive molecular weight, penalty for excessive hydrophobicity...)

Through these three steps, we screen out the likely optimal combinations and push them to the user.

 

# Tasks

The main CS tasks in this iGEM project are as follows:

1. Peptide design R&D (collect data, train single-function prediction models, develop the fusion engine, integrate tools)
2. Full-stack development of the platform (organize the functionality into backend servers, develop the frontend, design APIs, etc.) (Reference stack: React+TS+Vite+Tailwind CSS+React Queries+Python+FastAPI)
3. Wiki (frontend UIX design, frontend development) (Reference stack: React/Flask)

 
