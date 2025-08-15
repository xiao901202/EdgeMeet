# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

import torch

from qai_hub_models.models._shared.imagenet_classifier.model import ImagenetClassifier
from qai_hub_models.utils.asset_loaders import CachedWebModelAsset, SourceAsRoot

EFFICIENTVIT_SOURCE_REPOSITORY = "https://github.com/CVHub520/efficientvit"
EFFICIENTVIT_SOURCE_REPO_COMMIT = "6ecbe58ab66bf83d8f784dc4a6296b185d64e4b8"
MODEL_ID = __name__.split(".")[-2]

DEFAULT_WEIGHTS = "l2-r384.pt"
MODEL_ASSET_VERSION = 1


class EfficientViT(ImagenetClassifier):
    """Exportable EfficientViT Image classifier, end-to-end."""

    @classmethod
    def from_pretrained(cls, weights: str | None = None):
        """Load EfficientViT from a weightfile created by the source repository."""
        with SourceAsRoot(
            EFFICIENTVIT_SOURCE_REPOSITORY,
            EFFICIENTVIT_SOURCE_REPO_COMMIT,
            MODEL_ID,
            MODEL_ASSET_VERSION,
            imported_but_unused_modules=[
                "onnxsim",
                "torchpack",
                "torchpack.distributed",
                "timm.data.auto_augment",
            ],
        ):
            from efficientvit.cls_model_zoo import create_cls_model

            if not weights:
                pass
                weights = CachedWebModelAsset.from_asset_store(
                    MODEL_ID, MODEL_ASSET_VERSION, DEFAULT_WEIGHTS
                ).fetch()

            efficientvit_model = create_cls_model(name="l2", weight_url=weights)
            efficientvit_model.to(torch.device("cpu"))
            efficientvit_model.eval()
            return cls(efficientvit_model)
