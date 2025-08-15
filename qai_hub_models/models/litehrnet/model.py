# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

import torch

from qai_hub_models.evaluators.base_evaluators import BaseEvaluator
from qai_hub_models.evaluators.litehrnet_evaluator import LiteHRNetPoseEvaluator
from qai_hub_models.models.common import SampleInputsType
from qai_hub_models.utils.asset_loaders import CachedWebModelAsset, load_numpy
from qai_hub_models.utils.base_model import BaseModel
from qai_hub_models.utils.input_spec import InputSpec
from qai_hub_models.utils.printing import print_mmcv_import_failure_and_exit

try:
    from mmpose.apis import MMPoseInferencer
except ImportError as e:
    print_mmcv_import_failure_and_exit(e, "litehrnet", "MMPose")


MODEL_ID = __name__.split(".")[-2]
MODEL_ASSET_VERSION = 1

# More inferencer architectures for litehrnet can be found here
# https://github.com/open-mmlab/mmpose/tree/main/configs/body_2d_keypoint/topdown_heatmap/coco
DEFAULT_INFERENCER_ARCH = "td-hm_litehrnet-18_8xb64-210e_coco-256x192"

SAMPLE_INPUTS = CachedWebModelAsset.from_asset_store(
    MODEL_ID, MODEL_ASSET_VERSION, "sample_hrnet_inputs.npy"
)


class LiteHRNet(BaseModel):
    """Exportable LiteHRNet pose joint detector, end-to-end."""

    def __init__(self, inferencer) -> None:
        super().__init__()

        self.inferencer = inferencer
        self.model = self.inferencer.inferencer.model
        self.pre_processor = self.inferencer.inferencer.model.data_preprocessor
        self.H, self.W = self.inferencer.inferencer.model.head.decoder.heatmap_size
        self.K = self.inferencer.inferencer.model.head.out_channels
        self.B = 1

    @classmethod
    def from_pretrained(cls, inferencer_arch=DEFAULT_INFERENCER_ARCH) -> LiteHRNet:
        """LiteHRNet comes from the MMPose library, so we load using an internal config
        rather than a public weights file"""
        inferencer = MMPoseInferencer(inferencer_arch, device=torch.device(type="cpu"))
        return cls(inferencer)

    def forward(
        self, image: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Run LiteHRNet on `image`, and produce an upscaled image

        Parameters:
            image: Pixel values pre-processed for encoder consumption.
                   Range: float[0, 1]
                   3-channel Color Space: RGB

        Returns:
            keypoints: 1x17x2 array of coordinate pairs (in x,y format) denoting joint keypoints in the original image
            scores: 1x17 array of float[0,1] denoting the score of each corresponding keypoint
            heatmaps: 1x17 array of 64x48 heatmaps. These hold the raw confidence values of the locations
                      of each joint in the image. The keypoints and scores are derived from this
        """
        # Preprocess
        x = image[:, [2, 1, 0], ...]  # RGB -> BGR
        x = (x - self.pre_processor.mean) / self.pre_processor.std

        # Model prediction
        heatmaps = self.model._forward(x)

        batch_size = heatmaps.shape[0]
        num_keypoints = heatmaps.shape[1]

        # Reshape heatmaps to [B, K, H*W]
        heatmaps_flatten = heatmaps.view(batch_size, num_keypoints, -1)

        # Get max indices and values for each keypoint in each image
        scores, indices = torch.max(heatmaps_flatten, dim=2)

        # Convert flat indices to (x,y) coordinates
        y_locs = (indices // self.H).type(torch.float32)
        x_locs = (indices % self.H).type(torch.float32)

        keypoints = torch.stack((x_locs, y_locs), dim=-1)  # [B, K, 2]

        return keypoints, scores, heatmaps

    @staticmethod
    def get_input_spec(
        batch_size: int = 1,
        height: int = 256,
        width: int = 192,
    ) -> InputSpec:
        # Get the input specification ordered (name -> (shape, type)) pairs for this model.
        #
        # This can be used with the qai_hub python API to declare
        # the model input specification upon submitting a profile job.
        return {"image": ((batch_size, 3, height, width), "float32")}

    def _sample_inputs_impl(
        self, input_spec: InputSpec | None = None
    ) -> SampleInputsType:
        return {"image": [load_numpy(SAMPLE_INPUTS)]}

    @staticmethod
    def get_output_names() -> list[str]:
        return ["keypoints", "scores", "heatmaps"]

    def get_evaluator(self) -> BaseEvaluator:
        return LiteHRNetPoseEvaluator()

    @staticmethod
    def eval_datasets() -> list[str]:
        return ["cocowholebody"]

    @staticmethod
    def calibration_dataset_name() -> str:
        return "cocowholebody"
