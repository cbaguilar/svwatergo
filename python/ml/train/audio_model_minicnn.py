from __future__ import annotations


def build_tiny_cnn_model(nn, *, out_dim: int):
    return nn.Sequential(
        nn.Conv2d(1, 8, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(8, 16, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d((4, 8)),
        nn.Flatten(),
        nn.Linear(16 * 4 * 8, 32),
        nn.ReLU(),
        nn.Dropout(0.2),
        nn.Linear(32, int(out_dim)),
    )
