# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.nn.init as init


class SeModule(nn.Module):
    """cutomized squeeze exitationm module"""

    def __init__(self, in_size: int, reduction: int = 4):
        super().__init__()
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.se = nn.Sequential(
            nn.Conv2d(
                in_size,
                in_size // reduction,
                kernel_size=1,
                stride=1,
                padding=0,
                bias=False,
            ),
            nn.BatchNorm2d(in_size // reduction),
            nn.ReLU(inplace=True),
            nn.Conv2d(
                in_size // reduction,
                in_size,
                kernel_size=1,
                stride=1,
                padding=0,
                bias=False,
            ),
            nn.BatchNorm2d(in_size),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor):
        """
        x:   N,C,H,W  tensor
        return: N,C,H,W tensor

        """
        return x * self.se(self.pool(x))


class Block3x3(nn.Module):
    """mobileNetV3 block modified version for simplification"""

    def __init__(
        self,
        kernel_size: int,
        in_size: int,
        expand_size: int,
        out_size: int,
        nolinear: nn.Module,
        semodule: nn.Module | None,
        stride: int,
    ):
        super().__init__()
        self.kernel_size = kernel_size
        self.stride = stride
        self.se = semodule
        self.conv1 = nn.Conv2d(
            in_size, expand_size, kernel_size=1, stride=1, padding=0, bias=False
        )
        self.bn1 = nn.BatchNorm2d(expand_size)
        self.nolinear1 = nolinear
        if kernel_size == 3:
            self.conv2 = nn.Conv2d(
                expand_size,
                out_size,
                kernel_size=3,
                stride=stride,
                padding=1,
                bias=False,
            )
        else:
            self.conv2 = nn.Conv2d(
                expand_size, out_size, kernel_size=3, stride=1, padding=1, bias=False
            )
            self.conv3 = nn.Conv2d(
                out_size, out_size, kernel_size=3, stride=stride, padding=1, bias=False
            )
            self.bn3 = nn.BatchNorm2d(out_size)
            self.nolinear3 = nolinear
        self.bn2 = nn.BatchNorm2d(out_size)
        self.nolinear2 = nolinear
        self.shortcut = nn.Sequential()
        if stride == 1 and in_size != out_size:
            self.shortcut = nn.Sequential(
                nn.Conv2d(
                    in_size, out_size, kernel_size=1, stride=1, padding=0, bias=False
                ),
                nn.BatchNorm2d(out_size),
            )

    def forward(self, x: torch.Tensor):
        """
        x: N,C,H,W input feature
        return: N,C,H,W torch.tensor
        """
        out = self.nolinear1(self.bn1(self.conv1(x)))
        out = self.nolinear2(self.bn2(self.conv2(out)))
        if self.kernel_size == 5:
            out = self.nolinear3(self.bn3(self.conv3(out)))

        if self.se is not None:
            out = self.se(out)
        out = out + self.shortcut(x) if self.stride == 1 else out
        return out


class CBAModule(nn.Module):
    """Conv BatchNorm Activation block"""

    def __init__(
        self,
        in_channels: int,
        out_channels: int = 24,
        kernel_size: int = 3,
        stride: int = 1,
        padding: int = 0,
        bias: bool = False,
        act: str = "relu",
    ):
        super().__init__()
        self.conv = nn.Conv2d(
            in_channels, out_channels, kernel_size, stride, padding=padding, bias=bias
        )
        self.bn = nn.BatchNorm2d(out_channels)
        if act == "relu":
            self.act = nn.ReLU(inplace=True)
        elif act == "identity":
            self.act = nn.Identity()
        else:
            self.act = nn.PReLU()

        init.xavier_uniform_(self.conv.weight.data)
        if self.conv.bias is not None:
            self.conv.bias.data.zero_()

    def forward(self, x: torch.Tensor):
        """
        x: N,C,H,W tensor
        return:  N,C,H,W tensor
        """
        x = self.conv(x)
        x = self.bn(x)
        x = self.act(x)
        return x


class UpModule(nn.Module):
    """Upsampling module"""

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int = 2,
        stride: int = 2,
        bias: bool = False,
        mode: str = "UCBA",
        act: str = "relu",
    ):
        super().__init__()
        self.mode = mode

        if self.mode == "UCBA":
            self.up = nn.Upsample(size=None, scale_factor=2, mode="nearest")
            self.conv = CBAModule(
                in_channels, out_channels, 3, padding=1, bias=bias, act=act
            )
        elif self.mode == "DeconvBN":
            self.dconv = nn.ConvTranspose2d(
                in_channels, out_channels, kernel_size, stride, bias=bias
            )
            self.bn = nn.BatchNorm2d(out_channels)
        elif self.mode == "DeCBA":
            self.dconv = nn.ConvTranspose2d(
                in_channels, out_channels, kernel_size, stride, bias=bias
            )
            self.conv = CBAModule(out_channels, out_channels, 3, padding=1, bias=bias)
        else:
            raise RuntimeError(f"Unsupport mode: {mode}")

    def forward(self, x: torch.Tensor):
        """
        x: N,C,H,W tensor
        return: N,C,H,W tesnor.
        """
        if self.mode == "UCBA":
            return self.conv(self.up(x))
        elif self.mode == "DeconvBN":
            return F.relu(self.bn(self.dconv(x)))
        elif self.mode == "DeCBA":
            return self.conv(self.dconv(x))


class ContextModule(nn.Module):
    """single stage headless face detector context module"""

    def __init__(self, in_channels: int, act: str = "relu"):
        super().__init__()

        block_wide = in_channels // 4
        self.inconv = CBAModule(in_channels, block_wide, 3, 1, padding=1, act=act)
        self.upconv = CBAModule(block_wide, block_wide, 3, 1, padding=1, act=act)
        self.downconv = CBAModule(block_wide, block_wide, 3, 1, padding=1, act="relu")
        self.downconv2 = CBAModule(block_wide, block_wide, 3, 1, padding=1, act=act)

    def forward(self, x: torch.Tensor):
        """
        x: N,C,H,W tensor
        return:  N,C,H,W tensor
        """
        x = self.inconv(x)
        up = self.upconv(x)
        down = self.downconv(x)
        down = self.downconv2(down)
        return torch.cat([up, down], dim=1)


class DetectModule(nn.Module):
    def __init__(self, in_channels: int, act: str = "relu"):
        super().__init__()

        self.upconv = CBAModule(in_channels, in_channels // 2, 3, 1, padding=1, act=act)
        self.context = ContextModule(in_channels, act=act)

    def forward(self, x: torch.Tensor):
        """
        x:  N,C,H,W tensor
        return:  N,C,H,W tensor
        """
        up = self.upconv(x)
        down = self.context(x)
        return torch.cat([up, down], dim=1)


class HeadModule(nn.Module):
    """head module for specific task assignment"""

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        has_ext: bool = False,
        act: str = "relu",
    ):
        super().__init__()
        self.head = nn.Conv2d(in_channels, out_channels, kernel_size=1)
        self.has_ext = has_ext

        if has_ext:
            self.ext = CBAModule(
                in_channels,
                in_channels,
                kernel_size=3,
                padding=1,
                bias=False,
                act=act,
            )

    def init_normal(self, std: float, bias: float):
        nn.init.normal_(self.head.weight, std=std)
        nn.init.constant_(self.head.bias, bias)

    def forward(self, x: torch.Tensor):
        """
        x: N,C,H,W tensor
        return: N,C,H,W tensor
        """
        if self.has_ext:
            x = self.ext(x)
        return self.head(x)


class Mbv3SmallFast(nn.Module):
    def __init__(self, act="relu", RGB=True, has_se=True):
        super().__init__()

        self.keep = [2, 7]
        self.uplayer_shape = [32, 64]
        self.output_channels = 96

        if RGB:
            self.conv1 = nn.Conv2d(
                3, 16, kernel_size=3, stride=2, padding=1, bias=False
            )
        else:  # for gray
            self.conv1 = nn.Conv2d(
                1, 16, kernel_size=3, stride=2, padding=1, bias=False
            )

        self.bn1 = nn.BatchNorm2d(16)
        if act == "relu":
            self.hs1 = nn.ReLU(inplace=True)
        if has_se:
            self.bneck = nn.Sequential(
                Block3x3(3, 16, 16, 16, self.hs1, None, 2),  # 0 *
                Block3x3(3, 16, 64, 32, self.hs1, None, 2),  # 1
                Block3x3(3, 32, 96, 32, self.hs1, None, 1),  # 2 *
                Block3x3(5, 32, 96, 32, self.hs1, SeModule(32), 2),  # 3
                Block3x3(5, 32, 224, 32, self.hs1, SeModule(32), 1),  # 4
                Block3x3(5, 32, 224, 32, self.hs1, SeModule(32), 1),  # 5
                Block3x3(5, 32, 128, 64, self.hs1, SeModule(64), 1),  # 6
                Block3x3(5, 64, 160, 64, self.hs1, SeModule(64), 1),  # 7 *
                Block3x3(5, 64, 256, 96, self.hs1, SeModule(96), 2),  # 8
            )

        else:
            self.bneck = nn.Sequential(
                Block3x3(3, 16, 16, 16, self.hs1, None, 2),  # 0 *
                Block3x3(3, 16, 72, 24, self.hs1, None, 2),  # 1
                Block3x3(3, 24, 88, 24, self.hs1, None, 1),  # 2 *
                Block3x3(5, 24, 96, 40, self.hs1, None, 2),  # 3
                Block3x3(5, 40, 240, 40, self.hs1, None, 1),  # 4
                Block3x3(5, 40, 240, 40, self.hs1, None, 1),  # 5
                Block3x3(5, 40, 120, 48, self.hs1, None, 1),  # 6
                Block3x3(5, 48, 144, 48, self.hs1, None, 1),  # 7 *
                Block3x3(5, 48, 288, 96, self.hs1, None, 2),  # 8
            )

    def initialize_weights(self):
        print("random init...")
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2.0 / n))
                if m.bias is not None:
                    m.bias.data.zero_()
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()
            elif isinstance(m, nn.Linear):
                n = m.weight.size(1)
                m.weight.data.normal_(0, 0.01)
                m.bias.data.zero_()

    def forward(self, x):
        x = self.hs1(self.bn1(self.conv1(x)))
        outs = []
        for index, item in enumerate(self.bneck):
            x = item(x)

            if index in self.keep:
                outs.append(x)
        outs.append(x)
        return outs
