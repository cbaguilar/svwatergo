from __future__ import annotations


def _res_block(nn, in_ch: int, out_ch: int, stride: int = 1):
    block = nn.Sequential(
        nn.Conv2d(in_ch, out_ch, kernel_size=3, stride=stride, padding=1, bias=False),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(),
        nn.Conv2d(out_ch, out_ch, kernel_size=3, stride=1, padding=1, bias=False),
        nn.BatchNorm2d(out_ch),
    )
    if stride != 1 or in_ch != out_ch:
        skip = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, kernel_size=1, stride=stride, bias=False),
            nn.BatchNorm2d(out_ch),
        )
    else:
        skip = nn.Identity()
    relu = nn.ReLU()
    return nn.ModuleList([block, skip, relu])


def build_small_resnet_model(nn, *, out_dim: int):
    class _Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.stem = nn.Sequential(
                nn.Conv2d(1, 16, kernel_size=3, stride=1, padding=1, bias=False),
                nn.BatchNorm2d(16),
                nn.ReLU(),
            )
            self.b1 = _res_block(nn, 16, 16, stride=1)
            self.b2 = _res_block(nn, 16, 32, stride=2)
            self.b3 = _res_block(nn, 32, 64, stride=2)
            self.head = nn.Sequential(
                nn.AdaptiveAvgPool2d((1, 1)),
                nn.Flatten(),
                nn.Linear(64, 64),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(64, int(out_dim)),
            )

        @staticmethod
        def _run_block(block_parts, x):
            block, skip, relu = block_parts
            return relu(block(x) + skip(x))

        def forward(self, x):
            x = self.stem(x)
            x = self._run_block(self.b1, x)
            x = self._run_block(self.b2, x)
            x = self._run_block(self.b3, x)
            return self.head(x)

    return _Net()
