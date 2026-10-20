> **English** | [中文](SAFETY_AND_AI_ETHICS.zh.md)

# Four Safety Scores and AI Ethics Measures

This document answers two questions: what exactly the four safety scores in the pipeline are and what criterion each uses; and what ethics measures the project has actually taken when using AI and machine learning models that can be stated externally. Two limitations that must be explained in external statements are appended at the end.

---

## 1. The Four Safety Scores

The project's safety assessment consists of four independent checks. Each sets its own threshold, failing any one eliminates the candidate, and none of the four participates in any weighted average, so there is no situation in which "excellent scores in other dimensions can compensate for a safety defect."

**First item, toxicity prediction (ToxinPred3)**. The criterion is predicted toxicity probability, threshold 0.38; a score at or above 0.38 is judged toxic and eliminated directly. The tool is based on an Extra Trees ensemble tree classifier, using amino acid composition (20 dimensions) and dipeptide composition (400 dimensions) features, with model weights of 2 MB. This item was executed twice in the pipeline: once in the safety screening round, and once in the pre-screening of the deep scoring round, where the second execution eliminated an additional 16,982 peptides, an elimination rate of 16.4%.

**Second item, hemolysis prediction (HemoPI2)**. The criterion is predicted hemolysis probability, threshold 0.55; a score at or above 0.55 is eliminated. The tool is based on a fine-tuned ESM-2 t6 language model, with model weights of 30 MB.

**Third item, allergenicity prediction (AlgPred2)**. The criterion is predicted allergenicity probability, threshold 0.30; a score at or above 0.30 is eliminated. The tool is based on amino acid composition and a random forest classifier, with model weights of 1 MB. Of the four, only this one is executed in the antioxidant split round, completed together with channel assignment.

**Fourth item, immunogenicity prediction (MHCflurry)**. The criterion is the predicted binding strength of the peptide to MHC class I molecules, threshold 0.50; stronger binding means higher immunogenicity risk, and a score at or above 0.50 is eliminated. The raw output is IC50 (nM); the service layer maps binding strength onto a 0–1 risk score: binding below 50 nM counts as a strong binder (0.5–1.0), 50–500 nM as a weak binder (0.25–0.5), and above 500 nM as a non-binder (0–0.25). The model is based on a PyTorch neural network, claims support for 14,883 MHC alleles, and covers a peptide length range of 5–15 aa.

Of the four, toxicity, hemolysis, and allergenicity all have complete score records on the final 250 constructs. Immunogenicity has a technical limitation, see Part 2 at the end of this document.

By design, these four are handled in the opposite way from the functional attributes (antioxidant activity, thermal stability, solubility, cell penetration). Functional attributes are ranked by a data-driven weighted composite score, with weights determined by each metric's standard deviation on the dataset; safety attributes enter no weighting at all and receive only a binary pass-or-eliminate decision. This distinction is the single most substantive methodological constraint of the project: a weighted average allows a high score to compensate for a low one, and therefore cannot be used for safety judgments.

---

## 2. AI Ethics Measures That Can Be Stated Externally

The following eight items are all practices already implemented in this project, not plans or intentions.

**First, all prediction tools use the original authors' implementations, and no scientific conclusion was produced with generative AI.** The project applies an "original work first" principle to all of its more than ten prediction tools: it uses the original authors' code, models, and design ideas directly, without rewriting them itself, without reimplementing them with large models, and without using large models to generate prediction results. The project's tool documentation explicitly names "avoiding AI hallucination and papering over the work" as a design motivation. The significance of this item is that every score output by the pipeline can be traced to a published, peer-reviewed model, with no traceability gap of "a model that wrote its own model."

**Second, a falsifiable control channel was built.** The pipeline does not retain only the peptides with the best predicted antioxidant activity; it also retains the batch with the worst predictions as a negative control channel, 100 constructs in total, forty percent of the final 250. This is not standard practice, and it means the project deliberately retained a set of candidates that "should fail as predicted," for use as controls in subsequent experiments. If experimental results show no difference between the high-antioxidant channel and the low-antioxidant channel, the hypothesis of the entire pipeline is refuted. The existence of this design is itself a commitment to the falsifiability of the conclusions.

**Third, safety attributes use a one-vote veto and cannot be compensated.** This was covered above; here only the ethical implication is emphasized: safety is defined methodologically as a non-negotiable condition. A peptide that performs excellently in every other dimension, as long as it triggers any one of the four safety checks, has no chance of entering subsequent rounds. This avoids the dilution effect of indicators such as "high composite score" on the safety dimension.

**Fourth, the whole chain from source to product is traceable.** Every peptide retains its source identifier in the original database (for example UniProt's A0A5K0UWX3, MGnify's MGYP003726304477); that identifier was never lost across all nine rounds of screening, and the four safety scores, the per-round rankings, the weight configuration snapshots, and the final scores are all written to disk item by item. The generation process of any construct can be fully reproduced and audited by a third party.

**Fifth, weight configurations are auditable, and manual intervention must leave a trace.** The composite score's weights are determined by the data's own standard deviation, and one manual adjustment coefficient is retained alongside them. Any manual adjustment must record its justification in the configuration table; if the justification is missing, the adjustment does not stand. The purpose of this constraint is to prevent going back after seeing the results to modify weights and beautify the ranking.

**Sixth, conclusions do not depend on a single model, and key conclusions have independent cross-validation.** The three-dimensional structures of all 250 constructs were predicted by OmegaFold, after which the top 10 of each of the two channels, 20 constructs in total, were independently recomputed with AlphaFold3. The confidence trends given by the two models agree (OmegaFold mean 0.42, AlphaFold3 mean 0.52), showing that the ranking conclusion is not the product of any single model.

**Seventh, data unfavorable to the project's own conclusions is proactively disclosed.** The project records the following facts in its reports: the antigen prediction tool BepiPred3 has a standard deviation of only 0.0053 at the construct level, with almost no discriminating power, because about 90% of the 400 aa full-length sequence is shared scaffold, so this metric is of no help for screening at the construct level; the structure prediction confidence of the final 250 constructs is overall low (pLDDT mean 0.42, never exceeding 0.50), because silk's glycine-alanine repeats are themselves disordered. Being able to write and make public conclusions of this kind, rather than reporting only favorable metrics, is a direct expression of research integrity.

**Eighth, the research scope is limited to non-systemic delivery routes, with an explicit statement that computational prediction cannot replace wet lab.** The project currently focuses on topical, nanocarrier, microneedle, and other non-systemic delivery routes, avoiding the systemic exposure risk of systemic administration. All four categories of functional prediction, the five physicochemical properties, and the three-dimensional structure metrics come from computational prediction, and in no external statement does the project equate these scores with functional evidence.

**One additional note on data sources**: all input for this project is protein sequence from public databases, involving no patient data, human subject data, or personal information, so ethics procedures related to informed consent and data privacy do not apply. This is a statement of fact, not "we passed ethics review" — the project has not currently gone through any formal ethics review process, and external statements should not imply that it has.

---

## 3. Two Limitations That Must Be Explained in External Statements

The following two are not advantages that can be publicized; they are facts that would become a risk under reviewers' follow-up questions if they were left out of the materials.

**First, the immunogenicity item did not actually take effect on the final constructs.** MHCflurry's peptide length input range is 5–15 aa, whereas the functional peptides entering the final 250 constructs are all between 8 and 30 aa, of which only one is 8 aa and the rest are all above 18 aa, entirely outside the tool's valid range. The service layer returns a score of 0.0 for out-of-range input and labels it "Invalid Length", while the screening logic's criterion is "pass if the score is below 0.50", so all of these out-of-range inputs were silently passed and produced no elimination effect. That is to say, of the four safety checks, only three actually executed on the final products. There are two reasonable ways to handle this: first, state truthfully in the materials that the immunogenicity check could not take effect at the final stage due to the tool's length limitation; second, in the next round switch to an immunogenicity prediction method suitable for long peptides, or predict instead the core fragment that might be presented after trimming.

**Second, safety checks pass permissively when a service is unavailable.** The screening logic's criterion for each safety check is "eliminate if the item has a score and exceeds the threshold", so when some service returns a null value, the verdict is pass. This means that one service timeout or one failed batch request causes that batch of candidates to enter the next round without that check. In a multi-round run at the 19.9 million scale, this permissive strategy ensured the process was not interrupted by local failures, at the cost that individual unchecked candidates may pass. External statements should not claim that "every candidate passed all four safety checks"; the more accurate formulation is "candidates that triggered no safety veto were retained."

---

## 4. One-Sentence Version (for verbal replies)

The four safety scores are toxicity (ToxinPred3, threshold 0.38), hemolysis (HemoPI2, 0.55), allergenicity (AlgPred2, 0.30), and immunogenicity (MHCflurry, 0.50); all four are independent hard thresholds, any failure eliminates, and none participates in weighting. On AI ethics, the measures that can be mentioned include: all tools use the original authors' published models and generative AI is not used to produce scientific conclusions; a negative control channel is deliberately retained so that conclusions are falsifiable; safety attributes cannot be compensated by other scores; sources and weights are traceable and auditable along the whole chain; key conclusions are cross-validated with two independent models; data unfavorable to the project is proactively disclosed; delivery routes are limited to non-systemic ones with an explicit statement that computational prediction is not equivalent to functional evidence. Two points require proactive explanation: the immunogenicity check did not take effect at the final stage due to the tool's length limitation, and safety checks pass permissively when a service is unavailable.
