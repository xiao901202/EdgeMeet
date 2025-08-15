# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

from tflite import Model
from torch import nn

from qai_hub_models.models.common import SampleInputsType
from qai_hub_models.models.mediapipe_selfie.utils import (
    build_state_dict,
    get_convert,
    get_probable_names,
)
from qai_hub_models.utils.asset_loaders import CachedWebModelAsset, load_image
from qai_hub_models.utils.base_model import BaseModel
from qai_hub_models.utils.image_processing import app_to_net_image_inputs
from qai_hub_models.utils.input_spec import InputSpec

MODEL_ID = __name__.split(".")[-2]
MODEL_ASSET_VERSION = 1
MEDIAPIPE_SELFIE_CKPT_MAP = dict(
    square=CachedWebModelAsset.from_asset_store(
        MODEL_ID, MODEL_ASSET_VERSION, "weights/selfie_segmentation.tflite"
    ),
    landscape=CachedWebModelAsset.from_asset_store(
        MODEL_ID, MODEL_ASSET_VERSION, "weights/selfie_segmentation_landscape.tflite"
    ),
)
DEFAULT_IMAGE_TYPE = "square"
IMAGE_ADDRESS = CachedWebModelAsset.from_asset_store(
    MODEL_ID, MODEL_ASSET_VERSION, "selfie.jpg"
)


class DepthwiseConv2d(nn.Module):
    def __init__(self, in_channels, kernel_size=3, stride=2, padding=1):
        super().__init__()
        self.depthwise = nn.Conv2d(
            in_channels,
            in_channels,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            groups=in_channels,
        )

    def forward(self, x):
        x = self.depthwise(x)
        return x


class SelfieSegmentation(BaseModel):
    """Reconstruct the selfie segmentation graph for square as well as landscape image."""

    def __init__(self, image_type: str = "square"):
        """
        Parameters:
            image_type: str (choices: square or landscape)
                Instance of two model variations can be created:
                * One for square images (H=W)
                * One for rectangle images (landscape format)

        Returns:
            graph: Based on the image type, torch.nn.Module is returned.
                The only difference in architectures is that global average pool
                is only present in the model trained for landscape images.

        """
        if image_type not in ["square", "landscape"]:
            raise ValueError(f"Unsupported image type {image_type}")

        super().__init__()
        self.image_type = image_type
        self.allow_avg = image_type != "landscape"
        self.relu = nn.ReLU(inplace=True)
        self.hardswish = nn.Hardswish()
        self.sigmoid = nn.Sigmoid()

        self.conv1 = nn.Conv2d(3, 16, kernel_size=3, stride=2, padding=1)
        self.conv2 = nn.Conv2d(16, 16, 1)
        self.depthwise1 = DepthwiseConv2d(16, 3, 2, 1)
        if self.allow_avg:
            self.avgpool1 = nn.AvgPool2d(kernel_size=64, stride=64, padding=0)
        self.conv3 = nn.Conv2d(16, 8, kernel_size=1, stride=1, padding=0)
        self.conv4 = nn.Conv2d(8, 16, kernel_size=1, stride=1, padding=0)

        self.conv5 = nn.Conv2d(16, 16, 1)
        self.conv6 = nn.Conv2d(16, 72, 1)
        self.depthwise2 = DepthwiseConv2d(72, 3, 2, 1)

        self.conv7 = nn.Conv2d(72, 24, 1)
        self.conv8 = nn.Conv2d(24, 88, 1)
        self.depthwise3 = DepthwiseConv2d(88, 3, 1, 1)
        self.conv9 = nn.Conv2d(88, 24, 1)

        self.conv10 = nn.Conv2d(24, 96, kernel_size=1, stride=1, padding=0)
        self.depthwise4 = DepthwiseConv2d(96, 5, 2, 2)

        if self.allow_avg:
            self.avgpool2 = nn.AvgPool2d(kernel_size=16, stride=16, padding=0)
        self.conv11 = nn.Conv2d(96, 24, kernel_size=1, stride=1, padding=0)
        self.conv12 = nn.Conv2d(24, 96, kernel_size=1, stride=1, padding=0)
        self.conv13 = nn.Conv2d(96, 32, 1)

        self.conv14 = nn.Conv2d(32, 128, kernel_size=1, stride=1, padding=0)
        self.depthwise5 = DepthwiseConv2d(128, 5, 1, 2)
        if self.allow_avg:
            self.avgpool3 = nn.AvgPool2d(kernel_size=16, stride=16, padding=0)
        self.conv15 = nn.Conv2d(128, 32, kernel_size=1, stride=1, padding=0)
        self.conv16 = nn.Conv2d(32, 128, kernel_size=1, stride=1, padding=0)

        self.conv17 = nn.Conv2d(128, 32, 1)

        self.conv18 = nn.Conv2d(32, 128, kernel_size=1, stride=1, padding=0)
        self.depthwise6 = DepthwiseConv2d(128, 5, 1, 2)
        self.avgpool4 = nn.AvgPool2d(kernel_size=16, stride=16, padding=0)
        self.conv19 = nn.Conv2d(128, 32, kernel_size=1, stride=1, padding=0)
        self.conv20 = nn.Conv2d(32, 128, kernel_size=1, stride=1, padding=0)

        self.conv21 = nn.Conv2d(128, 32, 1)

        self.conv22 = nn.Conv2d(32, 96, kernel_size=1, stride=1, padding=0)
        self.depthwise7 = DepthwiseConv2d(96, 5, 1, 2)
        if self.allow_avg:
            self.avgpool5 = nn.AvgPool2d(kernel_size=16, stride=16, padding=0)
        self.conv23 = nn.Conv2d(96, 24, kernel_size=1, stride=1, padding=0)
        self.conv24 = nn.Conv2d(24, 96, kernel_size=1, stride=1, padding=0)

        self.conv25 = nn.Conv2d(96, 32, 1)

        self.conv26 = nn.Conv2d(32, 96, kernel_size=1, stride=1, padding=0)
        self.depthwise8 = DepthwiseConv2d(96, 5, 1, 2)
        self.avgpool6 = nn.AvgPool2d(kernel_size=16, stride=16, padding=0)
        self.conv27 = nn.Conv2d(96, 24, kernel_size=1, stride=1, padding=0)
        self.conv28 = nn.Conv2d(24, 96, kernel_size=1, stride=1, padding=0)

        self.conv29 = nn.Conv2d(96, 32, 1)

        self.conv30 = nn.Conv2d(32, 128, 1)
        if self.allow_avg:
            self.avgpool6 = nn.AvgPool2d(kernel_size=16, stride=16, padding=0)
        self.conv31 = nn.Conv2d(32, 128, kernel_size=1, stride=1, padding=0)
        self.conv32 = nn.Conv2d(128, 24, 1)
        if self.allow_avg:
            self.avgpool7 = nn.AvgPool2d(kernel_size=32, stride=32, padding=0)
        self.conv33 = nn.Conv2d(24, 24, 1)
        self.conv34 = nn.Conv2d(24, 24, 1)
        self.conv35 = nn.Conv2d(24, 24, 1)
        self.depthwise9 = DepthwiseConv2d(24, 3, 1, 1)

        self.conv36 = nn.Conv2d(24, 16, 1)
        self.avgpool8 = nn.AvgPool2d(kernel_size=64, stride=64, padding=0)
        self.conv37 = nn.Conv2d(16, 16, 1)
        self.conv38 = nn.Conv2d(16, 16, 1)
        self.conv39 = nn.Conv2d(16, 16, 1)
        self.depthwise10 = DepthwiseConv2d(16, 3, 1, 1)

        self.conv40 = nn.Conv2d(16, 16, 1)
        if self.allow_avg:
            self.avgpool9 = nn.AvgPool2d(kernel_size=128, stride=128, padding=0)
        self.conv41 = nn.Conv2d(16, 16, 1)
        self.conv42 = nn.Conv2d(16, 16, 1)
        self.conv43 = nn.Conv2d(16, 16, 1)
        self.depthwise11 = DepthwiseConv2d(16, 3, 1, 1)
        self.transpose_conv = nn.ConvTranspose2d(16, 1, 2, 2, 0)

        self.upsample = nn.Upsample(scale_factor=2, mode="bilinear")

    @classmethod
    def from_pretrained(cls, image_type: str = DEFAULT_IMAGE_TYPE):
        """
        Load the TFLite weights and convert them to PyTorch checkpoint.
        Weights for square input are different from landscape input.
        Hence, based on image_type different weights are loaded and
        different model instance is returned.

        Parameters:
            image_type: str (choices: square or landscape)
                Instance of two model variations can be created:
                * One for square images (H=W)
                * One for rectangle images (landscape format)
        Returns:
            Torch model with pretrained weights loaded.
        """
        front_net = cls(image_type)
        destination_path = MEDIAPIPE_SELFIE_CKPT_MAP[image_type].fetch()
        front_data = open(destination_path, "rb").read()
        front_model = Model.GetRootAsModel(front_data, 0)
        front_subgraph = front_model.Subgraphs(0)
        front_tensor_dict = {
            (front_subgraph.Tensors(i).Name().decode("utf8")): i
            for i in range(front_subgraph.TensorsLength())
        }

        front_probable_names = get_probable_names(front_subgraph)
        front_convert = get_convert(front_net, front_probable_names)
        front_state_dict = build_state_dict(
            front_model, front_subgraph, front_tensor_dict, front_net, front_convert
        )
        front_net.load_state_dict(front_state_dict, strict=True)
        return front_net

    @staticmethod
    def get_input_spec(batch_size: int = 1, image_type: str = "square") -> InputSpec:
        if image_type == "square":
            height, width = 256, 256
        else:
            height, width = 144, 256
        return {"image": ((batch_size, 3, height, width), "float32")}

    @staticmethod
    def get_output_names() -> list[str]:
        return ["mask"]

    @staticmethod
    def get_channel_last_inputs() -> list[str]:
        return ["image"]

    @staticmethod
    def get_channel_last_outputs() -> list[str]:
        return ["mask"]

    def forward(self, image):
        """
        Parameters:
            image: Input image to be segmented.
                Square: Shape [1, 3, 256, 256]
                Landscape: Shape [1, 3, 144, 256]
                Channel layout: RGB

        Returns:
            output (mask): Mask with person and the background segmented.
                Square: Shape [1, 256, 256]
                Landscape: Shape [1, 144, 256]

        """
        x = self.hardswish(self.conv1(image))
        x1 = x
        x = self.relu(self.conv2(x))
        x = self.relu(self.depthwise1(x))
        x1_1 = x
        if self.allow_avg:
            x = self.avgpool1(x)
        x = self.relu(self.conv3(x))
        x = self.sigmoid(self.conv4(x)) * x1_1
        x = self.conv5(x)
        x3 = x
        x = self.relu(self.conv6(x))
        x = self.relu(self.depthwise2(x))
        x = self.conv7(x)
        x4 = x
        x = self.relu(self.conv8(x))
        x = self.relu(self.depthwise3(x))
        x = self.conv9(x)
        x = x + x4
        x2 = x
        x = self.hardswish(self.conv10(x))
        x = self.hardswish(self.depthwise4(x))
        x2_2 = x
        if self.allow_avg:
            x = self.avgpool2(x)
        x = self.relu(self.conv11(x))
        x = self.sigmoid(self.conv12(x)) * x2_2
        x = self.conv13(x)

        x5 = x
        x = self.hardswish(self.conv14(x))
        x = self.hardswish(self.depthwise5(x))
        x3_3 = x
        if self.allow_avg:
            x = self.avgpool3(x)
        x = self.relu(self.conv15(x))
        x = self.sigmoid(self.conv16(x)) * x3_3
        x = self.conv17(x)
        x = x + x5

        x5 = x
        x = self.hardswish(self.conv18(x))
        x = self.hardswish(self.depthwise6(x))
        x4_4 = x
        if self.allow_avg:
            x = self.avgpool4(x)
        x = self.relu(self.conv19(x))
        x = self.sigmoid(self.conv20(x)) * x4_4
        x = self.conv21(x)
        x = x + x5

        x5 = x
        x = self.hardswish(self.conv22(x))
        x = self.hardswish(self.depthwise7(x))
        x5_5 = x
        if self.allow_avg:
            x = self.avgpool5(x)
        x = self.relu(self.conv23(x))
        x = self.sigmoid(self.conv24(x)) * x5_5
        x = self.conv25(x)
        x = x + x5

        x5 = x
        x = self.hardswish(self.conv26(x))
        x = self.hardswish(self.depthwise8(x))
        x6_6 = x
        if self.allow_avg:
            x = self.avgpool6(x)
        x = self.relu(self.conv27(x))
        x = self.sigmoid(self.conv28(x)) * x6_6
        x = self.conv29(x)
        x = x + x5

        x7_7 = x

        x = self.relu(self.conv30(x))
        if self.allow_avg:
            x7_7 = self.avgpool6(x7_7)

        x = x * self.sigmoid(self.conv31(x7_7))

        x = self.upsample(x)
        x6 = self.conv32(x)
        x = x2 + x6
        if self.allow_avg:
            x = self.avgpool7(x)
        x = x6 + x2 * self.sigmoid(self.conv34(self.relu(self.conv33(x))))
        x7 = self.relu(self.conv35(x))
        x = x7 + self.relu(self.depthwise9(x7))

        x = self.upsample(x)
        x = self.conv36(x)
        x8 = x
        x = x3 + x8
        if self.allow_avg:
            x = self.avgpool8(x)
        x = x8 + x3 * self.sigmoid(self.conv38(self.relu(self.conv37(x))))
        x = self.relu(self.conv39(x))
        x9 = x
        x = x9 + self.relu(self.depthwise10(x9))

        x = self.upsample(x)
        x = self.conv40(x)
        x10 = x
        x = x10 + x1
        if self.allow_avg:
            x = self.avgpool9(x)
        x = x10 + x1 * self.sigmoid(self.conv42(self.relu(self.conv41(x))))
        x11 = self.relu(self.conv43(x))
        x = x11 + self.relu(self.depthwise11(x11))

        x = self.sigmoid(self.transpose_conv(x))

        return x

    def _sample_inputs_impl(
        self, input_spec: InputSpec | None = None
    ) -> SampleInputsType:
        image = load_image(IMAGE_ADDRESS)
        if input_spec is not None:
            h, w = input_spec["image"][0][2:]
            image = image.resize((w, h))
        return {"image": [app_to_net_image_inputs(image)[1].numpy()]}
