# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
import numpy as np
import pytest
import torch
from transformers import SegformerForSemanticSegmentation

from qai_hub_models.models._shared.segmentation.app import SegmentationApp
from qai_hub_models.models.segformer_base.demo import (
    INPUT_IMAGE_ADDRESS,
    OUTPUT_IMAGE_ADDRESS,
)
from qai_hub_models.models.segformer_base.demo import main as demo_main
from qai_hub_models.models.segformer_base.model import SegformerBase
from qai_hub_models.utils.asset_loaders import load_image
from qai_hub_models.utils.image_processing import (
    normalize_image_transform,
    preprocess_PIL_image,
)
from qai_hub_models.utils.testing import assert_most_close

WEIGHTS = "nvidia/segformer-b0-finetuned-ade-512-512"


def test_task():
    """Verify that raw (numeric) outputs of both (QAIHM and non-qaihm) networks are the same."""
    source_model = SegformerForSemanticSegmentation.from_pretrained(WEIGHTS)
    qaihm_model = SegformerBase.from_pretrained(WEIGHTS)
    processed_sample_image = preprocess_PIL_image(load_image(INPUT_IMAGE_ADDRESS))

    with torch.no_grad():
        # original model output
        source_out = source_model(normalize_image_transform()(processed_sample_image))

        # Qualcomm AI Hub Model output
        qaihm_out = qaihm_model(processed_sample_image)
        for i in range(0, len(source_out)):
            assert np.allclose(source_out[i], qaihm_out[i])


@pytest.mark.trace
def test_trace():
    net = SegformerBase.from_pretrained(WEIGHTS)
    input_spec = net.get_input_spec()
    trace = net.convert_to_torchscript(input_spec, check_trace=False)

    # Collect output via app for traced model
    img = load_image(INPUT_IMAGE_ADDRESS)
    (_, _, height, width) = SegformerBase.get_input_spec()["image"][0]
    img_resized = img.resize((height, width))
    app = SegmentationApp(trace, normalize_input=False)
    out_imgs = app.predict(img_resized)
    out_imgs = out_imgs[0].resize(img.size)

    expected_out = load_image(OUTPUT_IMAGE_ADDRESS)
    assert_most_close(
        np.asarray(out_imgs, dtype=np.float32),
        np.asarray(expected_out, dtype=np.float32),
        0.005,
        rtol=0.02,
        atol=1.5,
    )


def test_demo():
    # Run demo and verify it does not crash
    demo_main(is_test=True)
