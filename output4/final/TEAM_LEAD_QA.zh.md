> [English](TEAM_LEAD_QA.md) | **中文**

# 组长问答：四题统一稿

本文件按四个问题分别成节，每节先给中文说明、再给英文说明，供wiki、parts、video 与汇报材料直接取用。

### 一、表格中 source data 与 round7_score 的含义

**中文**

表格中 `source_database` 与 `source_accession` 两列记录功能肽的原始出处。`source_database` 只取两个值：`mgy` 指 MGnify 宏基因组数据库，accession 形如 `MGYP003726304477`；`uniprot` 指 UniProt 参考蛋白库，accession 形如 `A0A5K0UWX3`。Top 10 中九条来自 MGnify、一条来自 UniProt；全部 250 个构建体中 244 条来自 MGnify。比例失衡不是设计选择，而是预处理第一步只保留 3–30 aa 短肽的结果——UniProt 以全长蛋白为主，几乎全部被长度筛除。MGnify 来源的肽只有序列存在，没有任何功能注释。

`round7_score` 是最终结构质量分，公式为 `0.40 × SASA + 0.40 × (1 − Aggrescan3D) + 0.20 × pLDDT_norm`。SASA 是功能肽在折叠后暴露于表面的相对溶剂可及面积，越高说明肽越容易被目标分子接触到；Aggrescan3D 是聚集倾向，越低越好，故取 1−A；pLDDT 是 OmegaFold 的结构置信度，经 min–max 归一化后使用。三项全部只衡量物理质量，**不含任何功能项**——抗氧化的预测值在第一轮划分通道之后就再未参与任何排名。因此 `global_rank` 前八名全部属于 Bottom 阴性对照通道，这是设计结果而非错误。全表 250 条的分数范围为 0.4800–0.7579。

**English**

Two columns in the table record where each functional peptide came from before the pipeline touched it. `source_database` takes one of two values. `mgy` denotes MGnify, the metagenomic sequence database, whose accessions take the form `MGYP003726304477`. `uniprot` denotes UniProt, the reference proteome database, whose accessions take the form `A0A5K0UWX3`. In the Top 10, nine peptides come from MGnify and one from UniProt; across all 250 final constructs, 244 come from MGnify. This imbalance is not a design choice. The first preprocessing step admits only peptides of 3 to 30 residues, and UniProt is predominantly a catalogue of full-length proteins, so nearly all of its entries are eliminated on length before any other criterion is applied. Peptides drawn from MGnify have a real sequence but carry no functional annotation of any kind.

`round7_score` is the final structure-quality score, computed as `0.40 × SASA + 0.40 × (1 − Aggrescan3D) + 0.20 × pLDDT_norm`. SASA is the relative solvent-accessible surface area of the functional peptide after folding: the higher it is, the more readily the peptide can make contact with its target. Aggrescan3D measures aggregation propensity, where lower is better, hence the term is inverted as 1−A. pLDDT is OmegaFold's structural confidence, min–max normalised across the dataset before use. All three terms describe physical quality only. **None of them is a functional term.** Predicted antioxidant activity is used once, to assign candidates to channels in the first round, and never re-enters any downstream ranking. A direct consequence is that global ranks 1 through 8 all belong to the Bottom negative-control channel, which is a structural outcome rather than a design fault. Across all 250 constructs the score ranges from 0.4800 to 0.7579.


### 二、蛋白质构建流程

**中文**

每一个进入表格的构建体都由三段序列组装而成：丝蛋白骨架、柔性连接肽、功能肽，末端再追加一次纯化标签。可变的量有三个——肽放在哪里、用哪种连接肽、用哪一条肽。

**骨架**是重组丝蛋白 `FibLNT8-10xRep-FibHCT`，合成时长372 aa：*B. mori* 纤维蛋白的 N 端结构域、十段甘氨酸富集重复序列（丝素 C 端的特征），以及一段自带组氨酸标签的 C 端。组装时把骨架自带的 C 端标签切除，避免与末端追加的标签重复，去除后骨架长 364 aa，250 个构建体全部使用同一段骨架。

**纯化标签**是 `LEHHHHHH` 八残基序列，统一追加在每个构建体的C 端，作用是亲和层析纯化的结合位点，同时把末端 `HHHHHH` 与蛋白主体隔开。每个构建体只有一份，不重复出现。

**连接肽**是桥接骨架与功能肽的甘氨酸-丝氨酸柔性链。项目评估了十种连接肽设计，进入组装的是两种：`Flex_GGGGSx1` 为五残基 `GGGGS`，最短、结构扰动最小；`Flex_GGGGSx2` 为十残基 `GGGGSGGGGS`，自由度更高，更可能把肽顶到骨架表面之外。之所以用甘氨酸与丝氨酸，是因为甘氨酸无侧链、构象最灵活，丝氨酸体积小且极性、维持链条可溶，`GGGGS` 重复是重组蛋白文献中的标准柔性连接肽基序。

**位置**决定功能肽融合到骨架的哪一端，共枚举三种：`N` 端把肽放在骨架之前，`C` 端放在骨架之后，`Both` 端在骨架两端各放一份拷贝。每处融合都是同框直接相连，肽与骨架之间除连接肽外不再添加任何间隔序列。以`LEHHHHHH` 表示纯化标签，组装逻辑为：

```
N端：肽 + 连接肽 + 骨架 + LEHHHHHH
C 端：    骨架 + 连接肽 + 肽   + LEHHHHHH
两端：肽 + 连接肽 + 骨架 + 连接肽 + 肽 + LEHHHHHH
```

排名第一的 `con_0418` 走 `C` 端加长连接肽的组合：364 aa 骨架、`GGGGSGGGGS`、25 aa 功能肽 `MNRPWITGHHHHHHHRRRRRRRRRR`、标签，产物共 407 aa。排名第三的 `con_0317` 走两端加短连接肽的组合，肽在骨架两端各一份，产物共 426 aa。Top 10 中五个为 `C` 端、五个为两端，两端融合在更早的筛选阶段已是存活主力，因为双拷贝肽在溶解度与热稳定性两项预测上表现更好。

**功能肽本身不是挑出来的，是筛出来的。** 流程从 19,890,021 条序列起始，经九轮漏斗收敛到 250 个构建体，总淘汰率 99.9987%，各轮各用单一标准，不做跨属性混合。

预处理按长度与残基类型裁剪，只保留 3–30 aa、仅含二十种标准氨基酸的序列。上限由预测模型本身决定，多个模型无法接受更长的输入。第一轮对全部候选跑抗氧化预测与过敏原预测，预测致敏分达到或超过 0.30 者直接淘汰；其余按纯抗氧化分排序，前10% 划入 Top 通道、后 1% 划入 Bottom 通道作为阴性对照，这是抗氧化分唯一一次参与决策的位置。第二轮执行安全否决：毒性预测须低于 0.38、溶血预测须低于 0.55、免疫原性预测须低于 0.50，三项各自独立判定，任一项不通过即淘汰，不存在加权补偿。第三轮对存活肽评分抗原表位、热稳定性、溶解度、细胞穿透性四项，并加权成综合分排名；权重不由人工指定，而是正比于各指标在本数据集上的截尾标准差，区分度越高的指标权重越大——这是全流程唯一使用加权平均的位置。第四轮把排名前4,324 的肽（Top 通道 116条、Bottom 通道 4,208 条）各按三种位置与两种连接肽组合成6 个构建体，共 25,944 个；以完整融合蛋白为单位重跑溶解度与热稳定性预测，取综合分前 10%，得 2,594 个。之所以要在组装后再评一次，是因为一条肽在游离状态下稳定可溶，接到364 aa 骨架上未必如此。第五、六轮用 OmegaFold 预测全部存活构建体的三维结构，再在结构上计算表面暴露度与聚集倾向，250 个构建体全部产出可用结构。第七轮合成`round7_score` 并排名。第八轮对两通道各前十名共 20 个构建体用 AlphaFold3 独立重算结构，作为对 OmegaFold 排序的交叉检验。

**两处必须随流程一同说明的事实。** 其一，OmegaFold 置信度在本数据集整体偏低，均值 0.42、从未超过 0.50，原因是丝素的甘氨酸-丙氨酸重复序列本身无序，AlphaFold3 独立复核给出同样图景（均值 0.52）。因此 `round7_score` 应表述为对低置信度模型的一致排序方式，而非精确物理测量。其二，排名第一与第二的 `con_0418`、`con_0417` 携带的肽`MNRPWITGHHHHHHHRRRRRRRRRR` 在组成上是组氨酸标签加多聚精氨酸的纯化/克隆把手，而非具备抗氧化活性的功能肽；它仅通过了长度与残基类型预筛，靠抗氧化预测给出的中等偏高分进入通道，再靠结构排名升至前二，因为结构排名不考察一条肽的作用。

**English**

Every construct listed in the table is one three-part assembly — a silk fibroin scaffold, a flexible linker, and the functional peptide — followed by a single purification tag appended at the end. Three variables define the product: where the peptide sits, which linker joins it, and which peptide is used.

**The scaffold** is a recombinant silk protein, `FibLNT8-10xRep-FibHCT`, 372 residues as synthesised: the N-terminal domain of *B. mori* fibroin, ten glycine-rich repeats characteristic of the silk C-terminal region, and a C-terminal segment carrying a histidine tag. The scaffold's native C-terminal tag is removed during assembly so that it does not duplicate the tag added afterwards, leaving a364-residue scaffold used by all 250 constructs without exception.

**The tag** is the eight-residue sequence `LEHHHHHH`, appended to the C-terminus of every construct. It serves as the binding site for affinity chromatography and as the spacer that holds the terminal `HHHHHH` motif clear of the protein body. Exactly one copy is present in each construct, never more.

**The linker** is a glycine-serine flexible chain bridging scaffold and peptide. Ten linker designs were evaluated for the library; two were carried into assembly. `Flex_GGGGSx1` is the five-residue `GGGGS`, the shortest and least structurally disruptive option. `Flex_GGGGSx2` is `GGGGSGGGGS`, a ten-residue version offering more freedom of motion and a higher likelihood of pushing the peptide clear of the scaffold surface. Glycine and serine are used because glycine has no side chain and is the most conformationally flexible residue, while serine is small and polar and keeps the chain soluble; the repeating `GGGGS` pattern is the standard flexible-linker motif established in the recombinant protein literature.

**The position** determines where the functional peptide is fused, and three positions were enumerated for every peptide: `N` places the peptide before the scaffold, `C` places it after the scaffold, and `Both` places one copy at each end. Each fusion is a direct in-frame join, with nothing added between peptide and scaffold beyond the linker. Writing `LEHHHHHH` for the purification tag, the assembly logic is:

```
N端：肽 + 连接肽 + 骨架 + LEHHHHHH
C 端：    骨架 + 连接肽 + 肽   + LEHHHHHH
两端：肽 + 连接肽 + 骨架 + 连接肽 + 肽 + LEHHHHHH
```

`con_0418`, the highest-ranked construct in the Top channel, follows the `C` pattern with the longer linker: a 364-residue scaffold, `GGGGSGGGGS`, the 25-residue peptide `MNRPWITGHHHHHHHRRRRRRRRRR`, and the tag, giving a 407-residue product. `con_0317`, at channel rank 3, follows the `Both` pattern with the shorter linker, placing the peptide at each end of the scaffold for a 426-residue product. Five of the Top 10 use the `C` position and five use `Both`. Two-ended fusion was already the dominant survivor at the earlier filtering stage, because a doubled peptide scores better on both the solubility and the thermal-stability predictions.

**The functional peptides were not chosen by the team; they are what survived the filter.** The funnel begins with 19,890,021 sequences and converges on 250 constructs, an overall rejection rate of 99.9987 percent, with each round applying a single criterion and no blending across properties.

Preprocessing trims on length and residue type, admitting only sequences of 3 to 30 residues composed solely of the twenty standard amino acids. The upper bound is set by the prediction models themselves, several of which cannot accept longer input. Round 1 scores every candidate for predicted antioxidant activity and predicted allergenicity, removing outright any candidate scoring 0.30 or above on allergenicity; the remainder are sorted on antioxidant score alone, with the top ten percent assigned to the Top channel and the bottom one percent to the Bottom channel as a negative control. This is the one and only point at which predicted antioxidant activity influences anything. Round 2 applies the safety veto: predicted toxicity below 0.38, predicted haemolysis below 0.55, predicted immunogenicity below 0.50, each judged independently, with failure of any single item eliminating the candidate outright and no compensating weighted average. Round 3 scores surviving peptides for B-cell epitope propensity, thermal stability, solubility, and cell-penetration propensity and combines them into a composite score. The weights are not set by hand but are proportional to each metric's winsorised standard deviation across the dataset, so a metric that genuinely separates candidates receives more weight; this is the only weighted average anywhere in the pipeline. Round 4 takes the top 4,324 ranked peptides — 116 from the Top channel, 4,208 from the Bottom — and assembles each into all six combinations of position and linker, giving 25,944 constructs. Solubility and thermal stability are then re-predicted on the complete fusion protein rather than the free peptide, and the top ten percent by combined score, 2,594 constructs, advances. The reason for scoring after assembly is that a peptide which is stable and soluble on its own need not behave the same way once attached to a 364-residue scaffold. Rounds 5 and 6 predict the three-dimensional structure of every survivor with OmegaFold and compute surface exposure and aggregation propensity on that structure; all 250 constructs yielded usable structures. Round 7 combines these into `round7_score` and produces the ranked tables. Round 8 re-predicts the top ten constructs from each channel — twenty in total — with AlphaFold3 as an independent check on the OmegaFold-based ordering.

**Two facts must travel with this description.** First, OmegaFold confidence is low across this dataset, averaging 0.42 and never exceeding 0.50, because the glycine-alanine repeats of silk are intrinsically disordered; AlphaFold3 independently returns the same picture at a mean of 0.52. `round7_score` should therefore be described as a consistent way to rank low-confidence models rather than as a precise physical measurement. Second, the peptide carried by the top two constructs, `MNRPWITGHHHHHHHRRRRRRRRRR`, is compositionally a histidine tag plus a poly-arginine purification or cloning handle rather than a functional peptide with antioxidant activity. It passed the length and residue-type prefilter, entered a channel on a middling-to-high predicted antioxidant score, and rose to the top of the structural ranking, which never examines what a peptide does.

### 三、四项安全评分是哪四项

**中文**

本项目的安全性评估由四项独立检查构成，各自设阈值，任一项不通过即淘汰，四项完全不参与任何加权平均，因此不存在其他维度分数优秀可以补偿安全性缺陷的情况。

**毒性（ToxinPred3）**，阈值 0.38，基于Extra Trees 集成树分类器与氨基酸组成、二肽组成特征，模型 2 MB。该项执行两次：一次在安全筛检轮次，一次在深度评分轮次的前置筛查中，第二次额外淘汰 16,982 条肽段，淘汰率 16.4%。**溶血性（HemoPI2）**，阈值 0.55，基于微调后的 ESM-2 t6 语言模型，模型 30 MB。**过敏原性（AlgPred2）**，阈值 0.30，基于氨基酸组成与随机森林分类器，模型 1 MB；四项中只有这一项在抗氧化分选轮次执行，与通道划分同步。**免疫原性（MHCflurry）**，阈值 0.50，结合越强即风险越高。原始输出为 IC50（nM），服务层映射为 0–1 风险分：低于 50 nM 记为强结合剂（0.5–1.0），50–500 nM 记为弱结合剂（0.25–0.5），高于 500 nM 记为非结合剂（0–0.25）。

安全属性的处理方式与功能属性正好相反：功能属性用数据驱动的加权综合分排名，安全属性只做通过或淘汰的二元判定。这一区分是本项目方法学上最实质的一条约束。

需同时说明两点局限。其一，免疫原性检查在最终 250 个构建体上实际未生效——MHCflurry 接受 5–15 aa 肽，而入选功能肽中仅一条为 8 aa、其余均在 18 aa 以上，服务层对超范围输入返回 0.0 分并标注为无效长度，而判定条件为低于 0.50 即通过，故全部静默放行，四项检查在最终产物上实际只有三项真正执行。其二，安全检查在服务不可用时按通过处理，故对外不宜表述为"每一项候选都通过了全部四项安全检查"，准确说法是"未触发任何一项安全否决的候选被保留"。

**English**

Safety in this pipeline rests on four independent checks. Each sets its own threshold, each can eliminate a candidate on its own, and none of the four enters any weighted average — so strong performance elsewhere can never compensate for a safety failure.

**Toxicity (ToxinPred3)**, threshold 0.38. An Extra Trees ensemble classifier over amino-acid composition and dipeptide composition features, 2 MB. This check runs twice: once at the safety-screening round, and once more as a pre-screen within the deep-scoring round, where it eliminates a further 16,982 peptides, or 16.4 percent. **Haemolysis (HemoPI2)**, threshold 0.55. A fine-tuned ESM-2 t6 language model, 30 MB. **Allergenicity (AlgPred2)**, threshold 0.30. Amino-acid composition with a random forest classifier, 1 MB; this is the only one of the four executed at the antioxidant-splitting round, alongside channel assignment. **Immunogenicity (MHCflurry)**, threshold 0.50, where stronger binding denotes higher risk. Raw output is IC50 in nM, mapped by the service layer onto a 0-to-1 risk score: below 50 nM is a strong binder scoring 0.5 to 1.0, 50 to 500 nM a weak binder scoring 0.25 to 0.5, and above 500 nM a non-binder scoring 0 to 0.25.

The treatment of safety attributes is the mirror image of that of functional attributes. Functional attributes are ranked by a data-driven weighted composite; safety attributes receive only a binary pass or eliminate decision. This distinction is the single most substantive methodological constraint in the project.

Two limitations must be stated alongside this. First, the immunogenicity check does not in fact operate on the final 250 constructs. MHCflurry accepts peptides of 5 to 15 residues, whereas among the selected functional peptides exactly one is 8 residues and every other one is at least 18 residues. The service returns a score of 0.0 for out-of-range input and labels it as an invalid length, and the acceptance condition is a score below 0.50, so all such inputs are silently passed and nothing is eliminated on this basis: of the four checks, only three genuinely execute on the final products. Second, a safety check whose service is unavailable is treated as passed. It is therefore inaccurate to state that every candidate passed all four checks; the accurate formulation is that candidates triggering no safety veto were retained.

### 四、使用 AI 时考虑的 AI 道德问题

**中文**

**第一，全部预测工具采用原作者已发表的代码与模型，不用生成式 AI 产出任何科学结论。** 项目工具文档把"避免 AI 幻觉和搪塞工作"写为明确设计动机。因此每一个分数都可追溯到一个经同行评议的模型，不存在模型自己生成模型的缺口。**第二，主动保留阴性对照。** 除高抗氧化通道外，另留100 个预测最差的构建体，占最终 250 个的四成，用于证伪流水线自身的假设。**第三，安全属性一票否决**，不可被其他分数补偿。**第四，全链路可追溯**，来源标识与权重配置理由全部落盘，人工调整权重必须填写理由才成立。**第五，不依赖单一模型**，250 个构建体全部由 OmegaFold 预测，两通道各前十名另用 AlphaFold3 交叉验证，两者趋势一致。**第六，主动披露不利数据**：BepiPred3 在构建体层面标准差仅 0.0053、几乎无区分度，结构预测置信度整体偏低，均写入报告。**第七，限定非系统性给药路径**，避开全身暴露风险，并声明计算预测不等同于功能实证。

需同时说明：项目全部输入为公开数据库蛋白序列，不涉患者或受试者数据，因此不适用知情同意程序；但项目**未经过任何正式伦理审查**，对外表述不应暗示已经过审查。

**English**

**First, every prediction tool runs on its original authors' published code and models; no scientific conclusion is produced by a generative model.** The project's own design documentation names the avoidance of AI hallucination as an explicit motivation. Every score is therefore traceable to a peer-reviewed model, and there is no gap in which a model generates its own model. **Second, a negative control was retained deliberately.** Alongside the high-antioxidant channel, 100 constructs with the poorest predicted activity were kept — two-fifths of the final 250 — so that the pipeline's own hypothesis can be falsified. **Third, safety attributes carry an absolute veto** and cannot be compensated by strength elsewhere. **Fourth, the chain is fully traceable**: source identifiers and the stated reason for every weight adjustment are persisted, and a manual weight change is only valid once its justification is recorded. **Fifth, no conclusion rests on a single model.** All 250 structures were predicted with OmegaFold, and the top ten constructs from each channel were independently re-predicted with AlphaFold3; the two models agree on trend. **Sixth, data unfavourable to the project is disclosed**: BepiPred3 achieves a standard deviation of only 0.0053 at the construct level and therefore has essentially no discriminating power, and structural prediction confidence is low throughout; both facts appear in the reports. **Seventh, the work is scoped to non-systemic delivery routes**, avoiding the risks of systemic exposure, with an explicit statement that computational prediction is not functional evidence.

Two qualifications accompany this. All input is protein sequence from public databases with no patient or human-subject data, so informed-consent procedures do not apply; but the project **has not undergone any formal ethics review**, and external descriptions should not imply otherwise.
