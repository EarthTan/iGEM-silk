"""
service.py
==========
AMP-ESM 微服务入口 — 抗菌肽（AMP）预测，支持两个模型版本。

原仓库: ../amp-esm（AMPlify-ESM2）
上游三个"版本"的说明:
    - v0.1.0（TF/Keras 基线，**本服务默认**）— one-hot + BiLSTM + Multi-Head
      Attention + Context Attention + sigmoid，5 折 stratified ensemble。
      代码在 src/（AMPlify.py / layers.py），权重为 models/<mode>/ 下的
      AMPlify h5（balanced / imbalanced 各 5 个，共 ~300 MB）。
    - v0.2.0（PyTorch + ESM-2）— facebook/esm2_t33_650M_UR50D 端到端微调 +
      MHA(32 heads) + Context Attention + Dense(1)，5 折 ensemble。
      权重为 models/amp_esm_<mode>/（5×fold ckpt，每组 ~37 GB），
      imbalanced 与 balanced 都可用（balanced 来自 2026-08-05 的训练 run）。
    - v0.2.1（推理优化）— 与 v0.2.0 同一组权重，仅推理代码优化
      （双 forward 合并 + inference_mode）；本服务移植的 amp_esm 包即此代码，
      因此 v0.2.0 天然带 v0.2.1 的加速。

模型来源:
    - v0.1.0: 随服务移植的 AMPlify h5 权重（models/balanced|imbalanced/）
    - v0.2.0: HuggingFace facebook/esm2_t33_650M_UR50D（首次自动下载 ~2.5 GB）
              + 随服务移植的 fold ckpt（models/amp_esm_imbalanced/）

环境变量:
    PORT               覆盖默认端口（默认 8011）
    AMP_ESM_VERSION    模型版本: v0.1.0（默认）/ v0.2.0
    AMP_ESM_MODE       训练模式: imbalanced（默认）/ balanced
                       （v0.1.0 与 v0.2.0 都支持）
    AMP_ESM_MODELS_DIR 模型根目录（默认: 本服务 models/，
                       可指向 ../amp-esm/models 复用原仓库权重）

API 端点:
    GET  /              → 服务信息
    GET  /health        → 健康检查
    GET  /info          → 工具信息
    POST /predict       → 单序列预测
    POST /predict/batch → 批量预测
"""

from __future__ import annotations

import json
import math
import os
import sys
import threading
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")  # 抑制 TF 日志噪音

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# `import amp_esm` / `import AMPlify` 从本服务目录解析（跨包导入目标: tools/__init__.py 等）
_SERVICE_DIR = Path(__file__).parent
sys.path.insert(0, str(_SERVICE_DIR))

from tools.template.fasta_service import FastaToolService, ToolResult, create_app
from tools.template.logger import get_logger
from tools.utils import detect_gpu, detect_system

# ─────────────────────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_ESM2_NAME = "facebook/esm2_t33_650M_UR50D"
MAX_LEN = 200
STANDARD_AA = frozenset("ACDEFGHIKLMNPQRSTVWY")
DEFAULT_MODELS_DIR = _SERVICE_DIR / "models"

SUPPORTED_VERSIONS = ("v0.1.0", "v0.2.0")
DEFAULT_VERSION = "v0.1.0"  # 用户指定优先使用 v0.1.0（TF/Keras 基线）

# 各版本的实现说明（/health 与 details 使用）
VERSION_INFO = {
    "v0.1.0": {
        "implementation": "TF/Keras BiLSTM + Multi-Head + Context Attention",
        "weight_kind": "AMPlify h5 权重 (5-fold)",
    },
    "v0.2.0": {
        "implementation": "PyTorch ESM-2 t33 650M (v0.2.1 推理优化)",
        "weight_kind": "fold ckpt (5-fold)",
    },
}


class AMPESMService(FastaToolService):
    """AMP-ESM 抗菌肽预测服务（v0.1.0 TF/Keras 或 v0.2.0 ESM-2）。"""

    tool_name = "amp-esm"
    version = "0.2.1"
    description = "抗菌肽（AMP）预测工具（AMP-ESM）- 支持 v0.1.0 TF/Keras 与 v0.2.0 ESM-2"
    recommended_batch_size = 20

    def __init__(self):
        super().__init__()
        # 模型前向非线程安全，用锁串行化推理（模板最多并发 10 个预测任务）
        self._infer_lock = threading.Lock()

        self.version = os.environ.get("AMP_ESM_VERSION", DEFAULT_VERSION).strip().lower()
        if self.version not in SUPPORTED_VERSIONS:
            self.logger.warning(
                "unknown AMP_ESM_VERSION=%r, falling back to %s",
                self.version, DEFAULT_VERSION,
            )
            self.version = DEFAULT_VERSION

        self.mode = os.environ.get("AMP_ESM_MODE", "imbalanced").strip().lower()
        if self.mode not in ("balanced", "imbalanced"):
            self.logger.warning(
                "unknown AMP_ESM_MODE=%r, falling back to 'imbalanced'",
                self.mode,
            )
            self.mode = "imbalanced"

        models_dir_env = os.environ.get("AMP_ESM_MODELS_DIR")
        self.models_dir = (
            Path(models_dir_env).expanduser()
            if models_dir_env
            else DEFAULT_MODELS_DIR
        )

        self.ckpt_paths: list[Path] = []
        self.models: list = []
        self.tokenizer = None
        self._v01_module = None
        self.device = "cpu"
        self.gpu_info: dict = {"backend": "unknown"}

    # ----------------------------------------------------------------------
    # 模型加载
    # ----------------------------------------------------------------------

    def _resolve_ckpt_paths(self) -> list[Path]:
        """定位 v0.2.0 的 fold 检查点列表（绝对路径）。

        优先读取 ``<models_dir>/amp_esm_<mode>/ensemble_ckpts.json``，
        manifest 中的相对路径按 manifest 所在目录解析（自包含移植）；
        无 manifest 时回退 glob ``fold-*.ckpt``。
        """
        root = self.models_dir / f"amp_esm_{self.mode}"
        if not root.exists():
            raise FileNotFoundError(
                f"checkpoint directory not found: {root.resolve()} "
                f"(set AMP_ESM_MODELS_DIR to point at the models root)"
            )
        manifest = root / "ensemble_ckpts.json"
        if manifest.exists():
            data = json.loads(manifest.read_text())
            paths = [Path(p) for p in data.get("checkpoints", [])]
            if paths:
                resolved = [
                    p if p.is_absolute() else manifest.parent / p for p in paths
                ]
                missing = [p for p in resolved if not p.exists()]
                if missing:
                    raise FileNotFoundError(
                        f"checkpoint(s) missing per {manifest}: "
                        + ", ".join(str(p) for p in missing[:5])
                    )
                return resolved
        paths = sorted(root.glob("fold-*.ckpt"))
        if not paths:
            raise FileNotFoundError(
                f"no fold-*.ckpt files found under {root.resolve()}"
            )
        return paths

    def _resolve_v01_weights(self) -> list[Path]:
        """定位 v0.1.0 的 5 个 AMPlify h5 权重（绝对路径）。"""
        mode_dir = self.models_dir / self.mode
        if not mode_dir.exists():
            raise FileNotFoundError(
                f"v0.1.0 weight directory not found: {mode_dir.resolve()} "
                f"(set AMP_ESM_MODELS_DIR to point at the models root)"
            )
        paths = [
            mode_dir / f"AMPlify_{self.mode}_model_weights_{i + 1}.h5"
            for i in range(5)
        ]
        missing = [p for p in paths if not p.exists()]
        if missing:
            raise FileNotFoundError(
                "missing v0.1.0 weights: " + ", ".join(str(p) for p in missing)
            )
        return paths

    def _load_v01(self) -> None:
        """加载 v0.1.0 TF/Keras 模型（5 个 AMPlify h5 权重）。"""
        import tensorflow as tf

        # src/AMPlify.py 原样导入（照搬代码，不修改），复用其 build/ensemble 逻辑
        src_dir = _SERVICE_DIR / "src"
        sys.path.insert(0, str(src_dir))
        import AMPlify  # noqa: F401  (原仓库 CLI 模块)

        weight_paths = self._resolve_v01_weights()
        self.logger.info(
            "v0.1.0 mode=%s loading %d AMPlify weights",
            self.mode, len(weight_paths),
        )
        for p in weight_paths:
            self.logger.info("  - %s", p)

        self._v01_module = AMPlify
        self.models = AMPlify.load_multi_model(
            [str(p) for p in weight_paths], AMPlify.build_amplify
        )

        # TF 的 CUDA 运行时库可能缺失（本机仅驱动），如实上报实际设备
        tf_devices = tf.config.list_physical_devices("GPU")
        self.device = "gpu" if tf_devices else "cpu"
        if not tf_devices:
            self.logger.info(
                "TF GPU libraries unavailable, falling back to CPU "
                "(v0.1.0 BiLSTM 推理 CPU 足够快)"
            )

        self.recommended_batch_size = 20  # v0.1.0 轻量，CPU 可高并发

    def _load_v02(self) -> None:
        """加载 v0.2.0 ESM-2 5-fold 集成（每个 fold 重建一个 AmplifyESM）。"""
        import torch
        from amp_esm.training.ensemble import load_fold_checkpoints
        from transformers import AutoTokenizer

        if torch.cuda.is_available():
            self.device = "cuda"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"

        self.ckpt_paths = self._resolve_ckpt_paths()
        self.logger.info(
            "v0.2.0 mode=%s loading %d fold checkpoints (device=%s)",
            self.mode, len(self.ckpt_paths), self.device,
        )
        for p in self.ckpt_paths:
            self.logger.info("  - %s", p)

        self.models = load_fold_checkpoints(
            self.ckpt_paths,
            esm2_name=DEFAULT_ESM2_NAME,
            map_location=self.device,
        )
        self.tokenizer = AutoTokenizer.from_pretrained(DEFAULT_ESM2_NAME)
        self.recommended_batch_size = 5  # v0.2.0 5×650M 模型，显存/内存占用大

    async def load_model(self) -> None:
        """按 AMP_ESM_VERSION 加载对应版本模型，常驻内存。"""
        self.gpu_info = detect_gpu()
        self._system_info = detect_system()
        self.logger.info("%s", self.gpu_info["message"])

        if self.version == "v0.1.0":
            self._load_v01()
        else:
            self._load_v02()

        self._model_status = {
            "status": "ready",
            "version": self.version,
            "implementation": VERSION_INFO[self.version]["implementation"],
            "model": (
                f"AMP-ESM {self.version} {self.mode} "
                f"({len(self.models)}-fold ensemble)"
            ),
            "weight_kind": VERSION_INFO[self.version]["weight_kind"],
            "device": self.device,
            "backend": self.gpu_info["backend"],
            "weights": (
                [str(p) for p in self.ckpt_paths]
                if self.version == "v0.2.0"
                else [str(p) for p in self._resolve_v01_weights()]
            ),
        }
        self.logger.info(
            "ensemble ready | version=%s | mode=%s | device=%s | folds=%d",
            self.version, self.mode, self.device, len(self.models),
        )

    # ----------------------------------------------------------------------
    # 预测
    # ----------------------------------------------------------------------

    def _amplify_log_score(self, prob: float) -> float:
        """AMPlify 对数标度分数 = -10*log10(1 - min(p, 1-1e-8))，与两版本一致。"""
        p = min(float(prob), 1.0 - 1e-8)
        return -10.0 * math.log10(1.0 - p)

    def _forward_one_v01(self, sequence: str) -> dict:
        """v0.1.0 单序列 5 折集成前向（复用原 src/AMPlify.py 的 ensemble）。"""
        mod = self._v01_module
        X = mod.one_hot_padding([sequence], MAX_LEN)
        ens, indv = mod.ensemble(self.models, X)
        score = float(ens[0])
        label = str(mod.proba_to_class_name([score])[0])
        return {
            "probability": score,
            "amplify_score": self._amplify_log_score(score),
            "prediction": label,
            "charge": (
                sequence.count("K") + sequence.count("R")
                - sequence.count("D") - sequence.count("E")
            ),
            "sub_model_probabilities": [float(p) for p in indv[:, 0]],
        }

    def _forward_one_v02(self, sequence: str) -> dict:
        """v0.2.0 单序列 5-fold 集成前向，数学与原 predict_records 完全一致:

        logits 平均 → sigmoid → P_ens。
        """
        import numpy as np
        import torch
        from amp_esm.evaluation.metrics import proba_to_class_name
        from amp_esm.utils.fasta import charge

        enc = self.tokenizer(
            [sequence],
            padding="max_length",
            max_length=MAX_LEN,
            truncation=True,
            return_tensors="pt",
        )
        input_ids = enc["input_ids"]
        attention_mask = enc["attention_mask"]
        if self.device != "cpu":
            input_ids = input_ids.to(self.device)
            attention_mask = attention_mask.to(self.device)

        with torch.inference_mode():
            logit_list = [
                float(
                    m(input_ids=input_ids, attention_mask=attention_mask)
                    .squeeze(-1)
                    .item()
                )
                for m in self.models
            ]

        mean_logit = float(np.mean(logit_list))
        prob = 1.0 / (1.0 + np.exp(-mean_logit))
        sub_probs = [1.0 / (1.0 + np.exp(-l)) for l in logit_list]

        return {
            "probability": prob,
            "amplify_score": self._amplify_log_score(prob),
            "prediction": proba_to_class_name(prob),
            "charge": charge(sequence),
            "sub_model_probabilities": sub_probs,
        }

    def _forward_one(self, sequence: str) -> dict:
        if self.version == "v0.1.0":
            return self._forward_one_v01(sequence)
        return self._forward_one_v02(sequence)

    async def predict_impl(self, sequence: str) -> ToolResult:
        """预测单条序列的抗菌肽概率（0-1）。

        校验（与原版一致）: 长度 2–200（v0.1.0）/ 3–200（v0.2.0），
        仅标准 20 种氨基酸，尾部 '*' 视为终止符剥离。
        不合法序列抛出 ValueError，由模板转为 success=False 响应。
        """
        seq = sequence.strip().upper()
        if seq.endswith("*"):
            seq = seq[:-1]
        min_len = 2 if self.version == "v0.1.0" else 3
        if not (min_len <= len(seq) <= MAX_LEN):
            raise ValueError(
                f"sequence length {len(seq)} outside [{min_len}, {MAX_LEN}]"
            )
        bad = sorted({c for c in seq if c not in STANDARD_AA})
        if bad:
            raise ValueError(
                f"non-standard amino acid(s): {''.join(bad)}"
            )

        with self._infer_lock:
            out = self._forward_one(seq)

        return ToolResult(
            score=float(out["probability"]),
            label=out["prediction"],
            details={
                "length": len(seq),
                "charge": int(out["charge"]),
                "amplify_log_scaled_score": round(float(out["amplify_score"]), 6),
                "version": self.version,
                "implementation": VERSION_INFO[self.version]["implementation"],
                "mode": self.mode,
                "device": self.device,
                "gpu_backend": self.gpu_info.get("backend", "unknown"),
                "sub_model_probabilities": [
                    round(float(p), 6) for p in out["sub_model_probabilities"]
                ],
            },
        )


# 创建 FastAPI 应用
app = create_app(AMPESMService)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8011"))
    logger = get_logger("amp-esm")
    logger.info("Starting on port %d ...", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
