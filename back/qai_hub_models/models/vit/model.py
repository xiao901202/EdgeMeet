# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

import torchvision.models as tv_models

from qai_hub_models.models._shared.imagenet_classifier.model import ImagenetClassifier

MODEL_ID = __name__.split(".")[-2]
DEFAULT_WEIGHTS = "IMAGENET1K_V1"


class VIT(ImagenetClassifier):
    @classmethod
    def from_pretrained(cls, weights: str = DEFAULT_WEIGHTS) -> VIT:
        net = tv_models.vit_b_16(weights=weights)
        return cls(net)
