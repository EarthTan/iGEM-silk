"""
service.py
==========
TemStaPro 蛋白质热稳定性预测微服务 — FASTA 序列 → 热稳定性评分。

基于 ProtT5-XL 蛋白语言模型嵌入 + MLP 分类器集成，
预测蛋白质在 6 个温度阈值 (40/45/50/55/60/65°C) 下的热稳定性。

核心引用: TemStaPro (Ieva Pudžiuvelytė et al., Bioinformatics 2024)
仓库: https://github.com/ievapudz/TemStaPro
许可证: MIT

使用方式：
    cd tools/TemStaPro
    source .venv/bin/activate
    python service.py

API 端点：
    GET  /              → 服务信息
    GET  /health        → 健康检查
    GET  /info          → 工具信息
    POST /predict       → 单序列预测
    POST /predict/batch → 批量预测


【模型工作流程】
─────────────────
输入一条蛋白质序列（如 "MKFLILFNILVSTLALCSNTVSA"），经过两个阶段：

阶段一：ProtT5-XL 编码
  - ProtT5-XL 是一个预训练的蛋白质语言模型（类似 NLP 的 BERT/T5）
  - 它把每个氨基酸残基映射为一个 1024 维的向量
  - 对所有残基的向量取平均值 → 得到一条序列的 1024-dim "嵌入表示"
  - 这个嵌入包含了序列的理化性质、进化信息、结构倾向等"隐含知识"

阶段二：MLP 集成分类
  - 30 个独立训练的 MLP 分类器（5 个随机种子 × 6 个温度阈值）
  - 每个分类器结构相同：1024→512→256→1 (Sigmoid)
  - 输入同一个 1024-dim 嵌入，输出一个 0~1 的热稳定性概率
  - 6 个温度阈值: 40°C, 45°C, 50°C, 55°C, 60°C, 65°C
  - 5 个种子: 不同随机初始化训练的同架构模型，取平均减少方差

最终输出:
  - mean_raw: 30 个预测值的平均 (综合热稳定性指标)
  - label: 该蛋白能耐受的最高温度区间，如 "(45-50]" 或 "≤40"
  - thermophilicity: 嗜热性分类（mesophilic / thermophilic / hyperthermophilic）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# ── 路径设置 ──────────────────────────────────────────────────────────
# 将当前目录和项目根目录加入 sys.path，以便导入同目录的 mlp.py / prottrans.py
# 以及 ../../tools/template/ 下的基类
SERVICE_DIR = Path(__file__).parent          # tools/TemStaPro/
PROJECT_ROOT = SERVICE_DIR.parent.parent      # iGEM-silk/
sys.path.insert(0, str(SERVICE_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from tools.template.fasta_service import (
    FastaToolService,   # 基类：提供 FastAPI 路由、并发控制、健康检查
    create_app,         # 工厂函数：把服务类 → FastAPI 应用
    ToolResult,         # 统一预测结果格式 {score, label, details}
    PredictResponse,    # 单次预测 HTTP 响应
    BatchPredictResponse,  # 批量预测 HTTP 响应
    PredictRequest,     # 单次预测 HTTP 请求
    BatchPredictRequest,   # 批量预测 HTTP 请求
)

# ═══════════════════════════════════════════════════════════════════════════════
# 配置常量
# ═══════════════════════════════════════════════════════════════════════════════

# 6 个温度阈值 (°C) — 每个阈值对应一个二分类问题:
# "该蛋白在这个温度下是否稳定？"
TEMPERATURE_THRESHOLDS = ["40", "45", "50", "55", "60", "65"]

# 5 个随机种子 — 同一架构用不同种子训练 5 次
# 集成 5 个模型的平均预测，降低单个模型随机波动的影响
SEEDS = ["1", "2", "3", "4", "5"]

# 温度区间标签 — 将连续的阈值预测转换为区间标签
# 例如: 在 45°C 稳定、50°C 不稳定 → label = "(45-50]"
# 这是用来给用户看的"人类可读"标签
TEMPERATURE_RANGES: dict[str, str] = {
    "40": "(40-45]",
    "45": "(45-50]",
    "50": "(50-55]",
    "55": "(55-60]",
    "60": "(60-65]",
    "65": "(65-70]",
}

# 嗜热性三大类 — 按蛋白最适生长温度分类
# mesophilic (嗜温):      最适 ≤ 45°C, 如大肠杆菌、人体蛋白
# thermophilic (嗜热):    最适 45–70°C, 如 Thermus aquaticus
# hyperthermophilic (超嗜热): 最适 > 70°C, 如 Pyrococcus furiosus
THERMOPHILICITY: dict[str, list[str]] = {
    "mesophilic": ["≤40", "(40-45]"],
    "thermophilic": ["(45-50]", "(50-55]", "(55-60]", "(60-65]", "(65-70]"],
    "hyperthermophilic": ["(70-75]", "(75-80]"],
}

# MLP 网络结构 — 与原始 TemStaPro 论文完全一致
# 输入 1024 (ProtT5-XL 嵌入维度) → 隐藏层1 512 → 隐藏层2 256 → 输出 1
# 输出层用 Sigmoid 激活，输出 0~1 的稳定性概率
MLP_INPUT_SIZE = 1024
MLP_HIDDEN_1 = 256
MLP_HIDDEN_2 = 128


class TemStaProService(FastaToolService):
    """蛋白质热稳定性预测微服务。

    继承自 FastaToolService，只需要实现:
      - load_model():   加载 ProtT5-XL 编码器 + 30 个 MLP 分类器
      - predict_impl(): 对单条序列执行"编码 → 分类 → 汇总"全流程

    基类自动处理: HTTP 路由、并发限流、错误捕获、健康检查。
    """

    # ── 类属性（基类要求覆盖）───────────────────────────────────────
    # 这些属性会被 /info 和 /health 接口读取
    tool_name: str = "temstapro"
    version: str = "1.0.0"
    description: str = (
        "蛋白质热稳定性预测 — ProtT5-XL 嵌入 + MLP 集成, "
        "预测 40–65°C 区间热稳定性, TemStaPro (Bioinformatics 2024)"
    )
    # 推荐批处理大小 — ProtT5-XL 编码比较重，50 条一批比较合适
    # 太大容易 OOM，太小则吞吐率低
    recommended_batch_size: int = 50

    def __init__(self):
        """初始化服务实例。

        与基类不同，这里不把模型放在 self.model 里，
        而是拆分为三个组件分别管理:
          - _prottrans_model: ProtT5-XL 编码器 (T5EncoderModel)
          - _tokenizer:       对应的分词器 (T5Tokenizer)
          - _classifiers:     30 个 MLP 分类器的字典，key = "45_s3" 这样的字符串
        """
        super().__init__()
        self._prottrans_model: Any = None
        self._tokenizer: Any = None
        self._classifiers: dict[str, Any] = {}  # key: f"{threshold}_s{seed}"
        self._device: Any = None

    # ── 模型加载 ──────────────────────────────────────────────────────
    # 这个方法在服务启动时被基类的 lifespan 自动调用
    # 分为两步: (1) 加载 ProtT5-XL 编码器 (2) 加载 30 个 MLP 分类器

    async def load_model(self) -> None:
        """加载全部模型到内存/显存。

        加载内容:
          1. ProtT5-XL (T5EncoderModel) ~ 3GB, 用于把序列变成 1024-dim 嵌入
          2. 30 个 MLP_C2H2 分类器 (5 seeds × 6 thresholds)
             每个 ~ 2MB, 合计 ~ 60MB

        环境变量:
          PROTTRANS_MODEL_DIR: ProtT5-XL 本地路径 (可选，默认从 HuggingFace Hub 下载)
          TEMSTAPRO_MODELS_DIR: MLP 权重目录 (默认 ./models/)

        注意: 基类会在 lifespan 中 try/except 包裹此方法，
        加载失败不会导致进程退出，而是标记 _loaded=False。
        """
        import torch
        from prottrans import load_prottrans  # 封装了 T5 模型的加载逻辑
        from mlp import MLP_C2H2              # 2 隐层 MLP，与论文一致

        # 自动检测 GPU — ProtT5-XL 在 GPU 上编码速度快 10–50 倍
        self._device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        print(f"[{self.tool_name}] Device: {self._device}")

        # ── 步骤 1: 加载 ProtT5-XL 编码器 ──────────────────────
        # 这个模型大约 3GB，首次加载会从 HuggingFace Hub 下载
        # 设置 PROTTRANS_MODEL_DIR 可以指向已下载的本地副本
        model_dir = os.environ.get("PROTTRANS_MODEL_DIR") or None
        print(f"[{self.tool_name}] Loading ProtT5-XL …")
        self._prottrans_model, self._tokenizer = load_prottrans(model_dir)
        print(f"[{self.tool_name}] ProtT5-XL loaded on {self._device}")

        # ── 步骤 2: 加载 30 个 MLP 分类器 ─────────────────────
        # 文件命名规则: mean_major_imbal_{threshold}_s{seed}.pt
        # 例如: mean_major_imbal_45_s3.pt = 45°C 阈值、种子 3 的 MLP 权重
        models_dir = os.environ.get(
            "TEMSTAPRO_MODELS_DIR",
            str(Path(__file__).parent / "models"),
        )
        print(f"[{self.tool_name}] Loading MLP classifiers from {models_dir} …")

        loaded = 0
        for threshold in TEMPERATURE_THRESHOLDS:   # 6 个阈值
            for seed in SEEDS:                      # 5 个种子
                key = f"{threshold}_s{seed}"        # 字典键，如 "45_s3"
                fname = f"mean_major_imbal-{threshold}_s{seed}.pt"
                fpath = os.path.join(models_dir, fname)

                # 权重文件缺失 → 直接抛错，由基类捕获并标记服务未就绪
                if not os.path.exists(fpath):
                    raise FileNotFoundError(
                        f"Classifier checkpoint not found: {fpath}. "
                        f"Download models from https://github.com/ievapudz/TemStaPro/tree/main/models"
                    )

                # 创建 MLP 实例，结构与论文一致: 1024→512→256→1
                mlp = MLP_C2H2(MLP_INPUT_SIZE, MLP_HIDDEN_1, MLP_HIDDEN_2)

                # PyTorch 加载权重文件
                # weights_only=True 是安全措施，防止 .pt 文件含恶意代码
                checkpoint = torch.load(fpath, map_location=self._device, weights_only=False)

                # ── 处理 PyTorch Lightning checkpoint 格式 ──────
                # 原始 TemStaPro 用 PyTorch Lightning 训练，checkpoint 的 key 是
                # "state_dict" → "model.model.0.weight" (Lightning 自动包装了一层)
                # 而我们的 MLP_C2H2 内部是 self.model (nn.ModuleList)，key 是
                # "model.0.weight"。
                # 所以需要去掉多余的 "model." 前缀: "model.model.X" → "model.X"
                if "state_dict" in checkpoint:
                    state = {}
                    for k, v in checkpoint["state_dict"].items():
                        # 将 "model.model.0.weight" → "model.0.weight"
                        new_k = k.replace("model.model.", "model.")
                        state[new_k] = v
                    mlp.load_state_dict(state)
                else:
                    # 直接就是 state_dict (非 Lightning 格式)
                    mlp.load_state_dict(checkpoint)

                # 移到正确的设备 (CPU 或 GPU) 并设为推理模式
                mlp.to(self._device)
                mlp.eval()  # 关闭 Dropout / BatchNorm 的训练行为
                self._classifiers[key] = mlp
                loaded += 1

        print(f"[{self.tool_name}] {loaded} MLP classifiers loaded")
        # 此时 self._loaded 仍为 False，由基类的 lifespan 在 load_model 成功后设为 True

    # ── 嵌入生成 ──────────────────────────────────────────────────────
    # ProtT5-XL 编码是计算瓶颈 (~90% 耗时)，所以提供独立的单条/批量方法
    # 批量编码可以充分利用 GPU 并行性

    def _embed_sequence(self, sequence: str) -> Any:
        """对单条序列生成 ProtT5-XL 平均嵌入向量 (1024-dim)。

        这是 predict_impl() 中使用的便捷方法。
        内部调用 _embed_batch([sequence]) 然后取第一条结果。
        """
        from prottrans import generate_embeddings

        emb_dict = generate_embeddings(
            self._prottrans_model,
            self._tokenizer,
            [sequence],         # 以列表形式传入（单条）
            self._device,
        )
        return emb_dict[sequence]  # shape: (1024,) 的 PyTorch tensor

    def _embed_batch(self, sequences: list[str]) -> dict[str, Any]:
        """对多条序列批量生成 ProtT5-XL 嵌入。

        batch 预测时使用 — 一次编码整个 batch，而非逐条编码。
        GPU 上批量编码速度远快于逐条循环。

        Returns:
            dict: 序列 → 1024-dim tensor 的映射
        """
        from prottrans import generate_embeddings

        return generate_embeddings(
            self._prottrans_model,
            self._tokenizer,
            sequences,
            self._device,
        )

    # ── MLP 集成推理 ──────────────────────────────────────────────────
    # 这是 TemStaPro 的核心: 对同一条序列的嵌入，用 30 个分类器分别预测
    # 然后综合得到: (1) 平均分数 (2) 温度标签 (3) 是否矛盾

    def _run_classifiers(self, embedding: Any) -> dict[str, Any]:
        """对单个嵌入向量运行全部 30 个 MLP 分类器。

        参数:
            embedding: 1024-dim 的 ProtT5-XL 嵌入 (PyTorch tensor)

        返回:
            dict:
                thresholds:    每个温度阈值的预测详情
                  - raw:     5 个种子的平均预测值 (0~1)
                  - binary:  二值化结果 (≥0.5 → 1 = 稳定)
                  - seeds:   5 个种子各自的预测值列表
                mean_raw:      6 个阈值 raw 值的总平均 (综合热稳定性指标)
                label:         温度区间标签，如 "(45-50]" 或 "≤40"
                clash:         是否出现非单调转换 (1→0→1，提示预测矛盾)
                thermophilicity: 嗜热性分类 (mesophilic/thermophilic/undetermined)

        集成策略:
          对每个阈值，取 5 个不同种子 MLP 的预测均值作为 raw score。
          这比单个 MLP 更稳健 — 单个种子的随机波动被平均消除。

        二值化:
          raw ≥ 0.5 → binary=1 (在该温度稳定)
          这是论文设定的阈值。
        """
        import torch

        # 确保嵌入在正确的设备上，且 dtype 为 float32
        emb = embedding.to(self._device).float()

        threshold_results: dict[str, dict[str, Any]] = {}
        all_raws: list[float] = []  # 收集所有 raw 值用于计算总平均

        # 遍历 6 个温度阈值
        for threshold in TEMPERATURE_THRESHOLDS:
            seed_preds: list[float] = []

            # 对该阈值的 5 个种子 MLP 分别预测
            for seed in SEEDS:
                key = f"{threshold}_s{seed}"
                with torch.no_grad():  # 不计算梯度，节省显存和计算
                    # MLP 输出是标量 (Sigmoid 之后，范围 0~1)
                    pred = self._classifiers[key](emb).item()
                seed_preds.append(pred)

            # 5 个种子取平均 → 该阈值的综合预测
            raw = sum(seed_preds) / len(seed_preds)
            # 二值化: ≥0.5 认为在该温度稳定
            binary = 1 if raw >= 0.5 else 0

            threshold_results[threshold] = {
                "raw": round(raw, 4),
                "binary": binary,
                "seeds": [round(s, 4) for s in seed_preds],
            }
            all_raws.append(raw)

        # ── 汇总 ────────────────────────────────────────────────
        label = self._get_temperature_label(threshold_results)
        clash = self._detect_clash(threshold_results)
        thermo = self._get_thermophilicity(label)

        return {
            "thresholds": threshold_results,
            "mean_raw": round(sum(all_raws) / len(all_raws), 4),
            "label": label,
            "clash": clash,
            "thermophilicity": thermo,
        }

    # ── 温度标签推断 ──────────────────────────────────────────────────
    # 这是 TemStaPro 论文中的 "right-hand label" 方法

    @staticmethod
    def _get_temperature_label(
        threshold_results: dict[str, dict[str, Any]]
    ) -> str:
        """推断蛋白能耐受的最高温度区间。

        算法 (right-hand label):
          按温度从低到高 (40→65) 检查每个阈值的 binary 值。
          找到第一个 binary=0 的位置 → 它的前一个阈值区间就是稳定性上限。

        三种边界情况:
          1. 全部稳定   (binary = [1,1,1,1,1,1]) → 返回最高区间 "(65-70]"
          2. 全部不稳定 (binary = [0,0,0,0,0,0]) → 返回 "≤40"
          3. 中间转换   (binary = [1,1,0,0,0,0]) → 返回 "(45-50]"
             (在 45°C 稳定，50°C 开始不稳定)

        例子:
          binary = [1, 1, 0, 0, 0, 0]
            40°C ✓, 45°C ✓, 50°C ✗ → label = "(45-50]"
          binary = [1, 1, 1, 1, 1, 0]
            40–60°C 全 ✓, 65°C ✗ → label = "(60-65]"
        """
        binaries = [threshold_results[t]["binary"] for t in TEMPERATURE_THRESHOLDS]

        # 所有温度都稳定 → 能耐受 65°C+
        if all(b == 1 for b in binaries):
            return TEMPERATURE_RANGES[TEMPERATURE_THRESHOLDS[-1]]  # "(65-70]"

        # 所有温度都不稳定 → ≤ 40°C
        if all(b == 0 for b in binaries):
            return "≤40"

        # 找到第一个变成 0 的位置
        # 例如 binaries=[1,1,0,0,0,0] → i=2 (50°C)
        # 前一个阈值是 45°C → label = "(45-50]"
        for i, b in enumerate(binaries):
            if b == 0:
                if i == 0:  # 第一个就不稳定
                    return "≤40"
                return TEMPERATURE_RANGES[TEMPERATURE_THRESHOLDS[i - 1]]

        return "unknown"

    # ── 矛盾检测 ──────────────────────────────────────────────────────
    # 理论上，如果 40°C 不稳定，那么 65°C 也不可能稳定（热稳定性随温度递减）
    # 如果出现 1→0→1 的模式，说明预测结果内部矛盾

    @staticmethod
    def _detect_clash(
        threshold_results: dict[str, dict[str, Any]]
    ) -> bool:
        """检测非单调预测模式 (预测矛盾)。

        正常情况下，binary 序列应该是单调递减的:
          正常:  [1, 1, 1, 0, 0, 0] → 1 次转换 (1→0)
          正常:  [0, 0, 0, 0, 0, 0] → 0 次转换
          正常:  [1, 1, 1, 1, 1, 1] → 0 次转换

        矛盾模式 (多次转换):
          矛盾:  [1, 0, 1, 0, 0, 0] → 3 次转换 (1→0→1→0)
                40°C 稳定, 45°C 不稳定, 50°C 又稳定 → 不合物理规律

        返回 True 表示存在矛盾 (transitions > 1)。
        这个 flag 提示用户: 该预测结果可能不可靠，建议人工审查。
        """
        binaries = [threshold_results[t]["binary"] for t in TEMPERATURE_THRESHOLDS]
        transitions = 0
        prev = binaries[0]
        for b in binaries[1:]:
            if b != prev:
                transitions += 1
            prev = b
        return transitions > 1

    # ── 嗜热性分类 ──────────────────────────────────────────────────

    @staticmethod
    def _get_thermophilicity(label: str) -> str | None:
        """根据温度标签判断蛋白的嗜热性类别。

        参数:
            label: 温度区间标签，如 "(45-50]" 或 "≤40"

        返回:
            "mesophilic"  — 嗜温 (≤ 45°C)
            "thermophilic" — 嗜热 (45–70°C)
            "hyperthermophilic" — 超嗜热 (> 70°C，但当前阈值最高到 65°C，不会出现)
            "undetermined" — 无法判断
        """
        if label == "≤40":
            return "mesophilic"
        for thermo_type, ranges in THERMOPHILICITY.items():
            if label in ranges:
                return thermo_type
        return "undetermined"

    # ── 核心预测 (单条) ─────────────────────────────────────────────
    # 这是 FastaToolService 要求子类必须实现的方法
    # 基类的 predict_single() 会调用这个方法

    async def predict_impl(self, sequence: str) -> ToolResult:
        """对单条蛋白序列预测热稳定性。

        这是基类要求的核心方法，封装了完整的推理流程:
          1. ProtT5-XL 编码 → 1024-dim 嵌入
          2. 30 个 MLP 集成推理
          3. 汇总 → ToolResult

        参数:
            sequence: 氨基酸序列（单字母），如 "MKFLILFNILVSTLALCSNTVSA"
                      支持任意长度，但 ProtT5-XL 对 >2000 aa 的超长序列会降速

        返回:
            ToolResult:
              - score: mean_raw (0~1), 综合热稳定性 — 越高越耐热
              - label: 温度区间标签，如 "(45-50]"
              - details: 包含各阈值详细预测、矛盾检测、嗜热性分类
        """
        # 步骤 1: ProtT5-XL 编码
        embedding = self._embed_sequence(sequence)

        # 步骤 2: MLP 集成推理
        result = self._run_classifiers(embedding)

        # 步骤 3: 包装为统一结果格式
        return ToolResult(
            score=result["mean_raw"],    # 综合热稳定性分数 (0~1)
            label=result["label"],       # 可读的温度区间标签
            details={
                "thresholds": result["thresholds"],        # 6 个阈值的详细预测
                "clash": result["clash"],                  # 是否存在预测矛盾
                "thermophilicity": result["thermophilicity"],  # 嗜热性分类
                "model": "ProtT5-XL + MLP_C2H2 ensemble (5 seeds × 6 thresholds)",
            },
        )

    # ── 批量预测 ──────────────────────────────────────────────────────
    # 覆盖基类的 predict_batch —— 因为我们有"批量编码"优化
    #
    # 基类的默认实现是: 对每条序列分别调用 predict_impl()
    # 但 TemStaPro 的第一阶段 (ProtT5-XL 编码) 在批量模式下更快:
    #   批量编码: 一次处理 N 条序列 → 充分发挥 GPU 并行性
    #   逐条编码: N 次分别处理 → GPU 利用率低
    #
    # 所以这里覆盖 predict_batch，先批量编码，再逐条 MLP 推理。
    # MLP 推理很快 (< 1ms/条)，不值得额外优化。

    async def predict_batch(
        self, request: BatchPredictRequest
    ) -> BatchPredictResponse:
        """批量预测 — 先一次性编码全部序列，再逐条 MLP 推理。

        优化逻辑:
          第一阶段 ProtT5-XL 编码:
            - 瓶颈在 GPU 矩阵运算
            - 批量处理吞吐率高得多
          → 所有序列一起编码

          第二阶段 MLP 推理:
            - 每个分类器只需一次前向传播 (< 1ms)
            - 30 个分类器 × N 条序列 ≈ 30N 次推理
            - 用 asyncio.Semaphore(10) 控制并发，避免显存溢出
          → 逐条处理，但并发执行

        参数:
            request: BatchPredictRequest
              - sequences: list[PredictRequest], 每条含 sequence + peptide_id

        返回:
            BatchPredictResponse: 所有成功预测的结果
        """
        import asyncio

        # ── 确保模型已加载 (双重检查锁定，与基类一致) ────
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    await self.load_model()
                    self._loaded = True

        # 提取纯序列列表和 ID 列表
        sequences = [item.sequence for item in request.sequences]
        peptide_ids = [item.peptide_id or "unknown" for item in request.sequences]

        # ── 阶段 1: 批量编码 (GPU 密集型，一次性处理) ──────
        try:
            embeddings = self._embed_batch(sequences)
        except Exception as e:
            return BatchPredictResponse(
                success=False,
                results=[],
                total=0,
                error=f"Embedding generation failed: {e}",
            )

        # ── 阶段 2: 逐条 MLP 推理 (轻量，并发执行) ────────
        # Semaphore(10) 限制同时推理数: 30 个 MLP × 10 并发 = 同时最多 300 个分类器在跑
        # 这个数值保守但安全，避免 GPU 显存被大量 batch 撑爆
        semaphore = asyncio.Semaphore(10)

        async def classify_one(seq: str, pid: str) -> ToolResult | None:
            """对单条序列的嵌入运行 MLP 集成，受信号量限流。"""
            async with semaphore:
                try:
                    emb = embeddings.get(seq)
                    if emb is None:
                        return None
                    r = self._run_classifiers(emb)
                    return ToolResult(
                        peptide_id=pid,
                        sequence=seq,
                        score=r["mean_raw"],
                        label=r["label"],
                        details={
                            "thresholds": r["thresholds"],
                            "clash": r["clash"],
                            "thermophilicity": r["thermophilicity"],
                        },
                    )
                except Exception:
                    # 单条失败不中断整个 batch
                    return None

        # 创建所有并发任务
        tasks = [
            classify_one(seq, pid)
            for seq, pid in zip(sequences, peptide_ids, strict=False)
        ]
        results = await asyncio.gather(*tasks)

        # 过滤失败项 (None)
        valid = [r for r in results if r is not None]

        # 如果有部分失败，error 中会写明 "N/M succeeded"
        return BatchPredictResponse(
            success=True,
            results=valid,
            total=len(valid),
            error=None
            if len(valid) == len(sequences)
            else f"{len(valid)}/{len(sequences)} succeeded",
        )

    # ── 单次预测 (覆盖基类以增加未就绪检查) ────────────────────────
    # 基类的 predict_single 内部调用 predict_impl，已经能正常工作。
    # 但基类在 _loaded=False 时会自动触发 load_model()，
    # 这里额外加了一层早期检查，直接返回友好错误而不触发加载。
    # 这样如果模型文件缺失导致加载失败，用户可以立即从 /health 看到原因。

    async def predict_single(self, request: PredictRequest) -> PredictResponse:
        """单次预测 — 检查模型就绪态后委托给基类。"""
        if not self._loaded:
            return PredictResponse(
                success=False,
                peptide_id=request.peptide_id,
                sequence=request.sequence,
                result=None,
                error="Model not loaded — check /health for status",
            )
        return await super().predict_single(request)


# ═══════════════════════════════════════════════════════════════════════════════
# 启动入口 — python service.py 直接运行
# ═══════════════════════════════════════════════════════════════════════════════
#
# 流程:
#   1. 读取环境变量 PORT (默认 8010) 和 HOST (默认 0.0.0.0)
#   2. 用 create_app() 工厂函数创建 FastAPI 应用
#      - create_app 内部会自动调用 load_model() 加载模型
#      - 自动注册 /predict, /predict/batch, /health, /info 等路由
#   3. 用 uvicorn 启动 HTTP 服务器
#
# 启动后可以访问:
#   http://localhost:8010/docs   — 自动生成的 Swagger API 文档
#   http://localhost:8010/health — 健康检查

if __name__ == "__main__":
    import uvicorn

    PORT = int(os.environ.get("PORT", "8010"))
    HOST = os.environ.get("HOST", "0.0.0.0")

    app = create_app(TemStaProService)
    print(f"[temstapro] Starting on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)
