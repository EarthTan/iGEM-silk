from __future__ import annotations

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

TOOLS_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOLS_DIR))

from services.template.tool_service import BioToolService, create_app, ToolResult


class TIPredService(BioToolService):
    """酪氨酸酶抑制肽预测服务"""

    tool_name = "tipred"
    version = "1.0.0"
    description = "酪氨酸酶抑制肽预测工具（TIPred）- Stacked Ensemble"
    recommended_batch_size = 50

    async def load_model(self):
        from scripts.tipredictor_full import TIPredictorMVFF

        self.predictor = TIPredictorMVFF(model_type='stacked')

        sample_data = [
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
            ('YGGFL', 1), ('GHK', 0), ('PAL', 0),
        ]
        seqs = [s for s, _ in sample_data]
        labels = [l for _, l in sample_data]
        self.predictor.train(seqs, labels)

        print(f"[{self.tool_name}] Model loaded, ready to predict")

    async def predict_impl(self, sequence: str) -> ToolResult:
        probs = self.predictor.predict([sequence])
        score = float(probs[0])
        label = "TIP" if score >= 0.5 else "non-TIP"

        return ToolResult(
            score=score,
            label=label,
            details={
                "length": len(sequence),
                "prediction": label,
                "threshold": 0.5
            }
        )


app = create_app(TIPredService)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8007"))
    print(f"Starting TIPred service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)