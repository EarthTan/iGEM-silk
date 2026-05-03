from __future__ import annotations

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

TOOLS_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOLS_DIR))

from services.template.tool_service import BioToolService, create_app, ToolResult


class GraphCPPService(BioToolService):
    """图神经网络细胞穿膜肽预测服务"""

    tool_name = "graphcpp"
    version = "1.0.0"
    description = "细胞穿膜肽预测工具（GraphCPP）- 图神经网络"
    recommended_batch_size = 10

    async def load_model(self):
        import torch
        import yaml
        from rdkit import Chem
        from graphcpp.lightning import GraphCPPModule
        from graphcpp.dataset import _featurize_mol
        from graphcpp.fp_generators import fp_dict

        checkpoint_path = Path(__file__).parent / "model" / "checkpoints" / "epoch=22-step=69.ckpt"
        hparams_path = Path(__file__).parent / "model" / "hparams.yaml"

        with open(hparams_path, 'r') as f:
            hparams = yaml.safe_load(f)

        self.model = GraphCPPModule.load_from_checkpoint(
            checkpoint_path=str(checkpoint_path),
            map_location=torch.device('cpu')
        )
        self.model.eval()
        self.model.freeze()
        self.hparams = hparams

        print(f"[{self.tool_name}] GraphNN model loaded, ready to predict")

    async def predict_impl(self, sequence: str) -> ToolResult:
        import torch
        from rdkit import Chem
        from graphcpp.dataset import _featurize_mol
        from graphcpp.fp_generators import fp_dict

        mol = Chem.MolFromFASTA(sequence)
        if mol is None:
            return ToolResult(
                score=0.0,
                label="non-CPP",
                details={"error": "Invalid sequence"}
            )

        data = _featurize_mol(mol)
        fp = fp_dict[self.hparams['fingerprint_type']].GetFingerprint(mol)
        data.fp = torch.tensor([fp], dtype=torch.float32)

        with torch.no_grad():
            prediction = self.model(data)[0]
            probability = torch.sigmoid(prediction).item()

        is_cpp = probability >= 0.5
        label = "CPP" if is_cpp else "non-CPP"

        return ToolResult(
            score=float(probability),
            label=label,
            details={
                "length": len(sequence),
                "prediction": label,
                "threshold": 0.5
            }
        )


app = create_app(GraphCPPService)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8009"))
    print(f"Starting GraphCPP service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)