# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

import os

import torch
import torch.nn as nn

from qai_hub_models.evaluators.base_evaluators import BaseEvaluator
from qai_hub_models.evaluators.foot_track_evaluator import FootTrackNetEvaluator
from qai_hub_models.models.foot_track_net.layers import (
    CBAModule,
    DetectModule,
    HeadModule,
    Mbv3SmallFast,
    UpModule,
)
from qai_hub_models.utils.asset_loaders import CachedWebModelAsset
from qai_hub_models.utils.base_model import BaseModel
from qai_hub_models.utils.input_spec import InputSpec

MODEL_ID = __name__.split(".")[-2]
MODEL_ASSET_VERSION = 1
DEFAULT_WEIGHTS = "SA-e30_finetune50_conv_norm.pth"


class FootTrackNet(BaseModel):
    """FootTrackNet model"""

    def __init__(
        self,
        wide: int = 64,
        has_ext: bool = True,
        upmode: str = "UCBA",
        act: str = "relu",
        RGB: bool = True,
        strict: bool = False,
        n_lmk: int = 17,
    ):
        super().__init__()
        """
        FootTrackNet multi task human detector model for person, face detection plus head and feet landmark detection.
        Draw the given points on the frame.
        It takes RGB (uint8) as input directly.
        Parameters:
            wide: the channel size of bandwith of the intermediate layers
            has_ext: if add extension layer in the head module.
            upmode: upsampling mode.
            act: activation function.
            RGB: if the input is a 3 channel RGB
            acb_mode: the ACBlock mode.
            stand_conv: if use the standard convolution.
            strict: if load the model weights in a strict way
            n_lmk: the number of landmarks for detection.

        Returns:
            FootTrackNet model instance.
        """
        self.use_rgb = RGB
        self.strict = strict

        # internal normalization layer,  RGB->BGR, as a conv norm
        self.conv_layer = nn.Conv2d(3, 3, 1, stride=1, padding=0, bias=False)
        # norm layer
        self.bn2 = nn.BatchNorm2d(3)

        # define backbone
        self.bb = Mbv3SmallFast(act, RGB)

        # Get the number of branch node channels stride 4, 8, 16
        c0, c1, c2 = self.bb.uplayer_shape
        act = "relu" if act == "hswish" else act
        self.conv3 = CBAModule(
            self.bb.output_channels,
            wide,
            kernel_size=1,
            stride=1,
            padding=0,
            bias=False,
            act=act,
        )  # s32
        self.connect0 = CBAModule(c0, wide, kernel_size=1, act=act)  # s4
        self.connect1 = CBAModule(c1, wide, kernel_size=1, act=act)  # s8
        self.connect2 = CBAModule(
            c2, wide, kernel_size=1, act=act
        )  # s16, conv, batchnorm activation.

        self.up0 = UpModule(
            wide, wide, kernel_size=2, stride=2, mode=upmode, act=act
        )  # s16 nearest
        self.up1 = UpModule(
            wide, wide, kernel_size=2, stride=2, mode=upmode, act=act
        )  # s8
        self.up2 = UpModule(
            wide, wide, kernel_size=2, stride=2, mode=upmode, act=act
        )  # s4
        self.detect = DetectModule(wide, act=act)

        self.heatmap1 = HeadModule(wide, 1, has_ext=has_ext)
        self.box1 = HeadModule(wide, 4, has_ext=has_ext)
        self.heatmap2 = HeadModule(wide, 1, has_ext=has_ext)
        self.box2 = HeadModule(wide, 4, has_ext=has_ext)
        self.heatmap3 = HeadModule(wide, 1, has_ext=has_ext)
        self.box3 = HeadModule(wide, 4, has_ext=has_ext)

        self.landmark = HeadModule(wide, 2 * n_lmk, has_ext=has_ext)
        self.landmark_vis = HeadModule(wide, n_lmk, has_ext=has_ext)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, ...]:
        """
        Forward computation of FootTrackNet.

        Inputs:
            image: torch.Tensor
                Input image.
        Outputs: List[torch.Tensor]
            heatmap: N,C,H,W the heatmap for the person/face detection.
            bbox: N,C*4, H,W the bounding box coordinate as a map.
            landmark: N,C*34,H,W the coordinates of landmarks as a map.
            landmark_visibility: N,C*17,H,W the visibility of the landmark as a map.
        """
        x = self.conv_layer(x * 1.0)  # conv to float
        x = self.bn2(x)
        s4, s8, s16, s32 = self.bb(x)
        s32 = self.conv3(s32)
        s16 = self.up0(s32) + self.connect2(s16)
        s8 = self.up1(s16) + self.connect1(s8)
        s4 = self.up2(s8) + self.connect0(s4)
        x = self.detect(s4)

        # simplify with sigmoid
        center1 = self.heatmap1(x).sigmoid()
        center2 = self.heatmap2(x).sigmoid()
        center3 = self.heatmap3(x).sigmoid()

        box1 = self.box1(x)
        box2 = self.box2(x)
        box3 = self.box3(x)  # when demo, no hand
        landmark = self.landmark(x)  # 2 * 17
        landmark_vis = self.landmark_vis(x).sigmoid()
        return (
            torch.cat((center1, center2, center3), dim=1),
            torch.cat((box1, box2, box3), dim=1),
            landmark,
            landmark_vis,
        )  # simple one landmark

    def load_weights(self, base_file):
        """load pretrined weights"""
        other, ext = os.path.splitext(base_file)
        if ext == ".pkl" or ".pth":
            print("Loading pretrained weights into state dict...")

            pretrained_dict = torch.load(
                base_file, map_location=lambda storage, loc: storage
            )
            model_dict = self.state_dict()

            if not self.strict:
                pretrained_dict = {
                    k: v for k, v in pretrained_dict.items() if k in model_dict
                }
                if (
                    self.use_rgb and pretrained_dict["bb.conv1.weight"].shape[1] == 1
                ):  # single channel.
                    pretrained_dict["bb.conv1.weight"] = torch.tile(
                        pretrained_dict["bb.conv1.weight"], [1, 3, 1, 1]
                    )  # the input channel to 3.
            model_dict.update(pretrained_dict)

            self.load_state_dict(model_dict, strict=self.strict)
            print("Finished!")
        else:
            raise ValueError("Sorry only .pth and .pkl files supported.")

    @classmethod
    def from_pretrained(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls, checkpoint_path: str | None = None
    ) -> FootTrackNet:
        """
        Load model from pretrained weights.

        Inputs:
            checkpoint_path: str
                Checkpoint path of pretrained weights.
        Output: nn.Module
            FootTrackNet model.
        """
        model = FootTrackNet()
        checkpoint_to_load = (
            checkpoint_path
            if checkpoint_path is not None
            else CachedWebModelAsset.from_asset_store(
                MODEL_ID, MODEL_ASSET_VERSION, DEFAULT_WEIGHTS
            ).fetch()
        )

        model.load_weights(checkpoint_to_load)
        model.to(torch.device("cpu"))
        model.eval()
        return model

    @staticmethod
    def get_input_spec(
        batch_size: int = 1,
        height: int = 480,
        width: int = 640,
    ) -> InputSpec:
        """
        Returns the input specification (name -> (shape, type). This can be
        used to submit profiling job on Qualcomm AI Hub. Default resolution is 2048x1024
        so this expects an image where width is twice the height.
        """
        return {"image": ((batch_size, 3, height, width), "float32")}

    @staticmethod
    def get_output_names() -> list[str]:
        return ["heatmap", "bbox", "landmark", "landmark_visibility"]

    @staticmethod
    def get_channel_last_inputs() -> list[str]:
        return ["image"]

    @staticmethod
    def get_channel_last_outputs() -> list[str]:
        return ["heatmap", "bbox", "landmark", "landmark_visibility"]

    def get_evaluator(self) -> BaseEvaluator:
        input_spec = self.get_input_spec()
        return FootTrackNetEvaluator(
            input_spec["image"][0][2], input_spec["image"][0][3]
        )

    @staticmethod
    def eval_datasets() -> list[str]:
        return ["foot_track_dataset"]

    @staticmethod
    def calibration_dataset_name() -> str:
        return "foot_track_dataset"
