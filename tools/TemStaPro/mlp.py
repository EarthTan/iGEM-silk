"""
MLP_C2H2 — 2-hidden-layer feedforward classifier for thermostability prediction.

From TemStaPro (Ieva Pudžiuvelytė et al., 2024). MIT license.
Architecture: Linear(1024→512)+ReLU → Linear(512→256)+ReLU → Linear(256→1)+Sigmoid
"""

import torch
from torch import nn


class MLP_C2H2(nn.Module):
    def __init__(self, input_size=1024, hidden_size_1=512, hidden_size_2=256):
        super().__init__()
        self.input_size = input_size
        self.hidden_size_1 = hidden_size_1
        self.hidden_size_2 = hidden_size_2

        self.model = nn.ModuleList([
            nn.Linear(self.input_size, self.hidden_size_1),
            nn.ReLU(),
            nn.Linear(self.hidden_size_1, self.hidden_size_2),
            nn.ReLU(),
            nn.Linear(self.hidden_size_2, 1),
            nn.Sigmoid(),
        ])
        self.loss_function = nn.BCELoss()

    def forward(self, point):
        for layer in self.model:
            point = layer(point)
        return point

    def calculate_loss(self, point, label):
        return self.loss_function(point, label)
