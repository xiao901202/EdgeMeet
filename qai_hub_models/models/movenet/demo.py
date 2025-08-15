# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

import numpy as np
from PIL import Image

from qai_hub_models.models.movenet.app import MovenetApp
from qai_hub_models.models.movenet.model import MODEL_ASSET_VERSION, MODEL_ID, Movenet
from qai_hub_models.utils.args import (
    demo_model_from_cli_args,
    get_model_cli_parser,
    get_on_device_demo_parser,
    validate_on_device_demo_args,
)
from qai_hub_models.utils.asset_loaders import CachedWebModelAsset, load_image
from qai_hub_models.utils.display import display_or_save_image

IMAGE_ADDRESS = CachedWebModelAsset.from_asset_store(
    MODEL_ID, MODEL_ASSET_VERSION, "movenet_demo.png"
)


# The demo will display a image with the predicted keypoints.
def movenet_demo(model_cls: type[Movenet], is_test: bool = False):
    # Demo parameters
    parser = get_model_cli_parser(model_cls)
    parser = get_on_device_demo_parser(parser, add_output_dir=True)
    parser.add_argument(
        "--image",
        type=str,
        default=IMAGE_ADDRESS,
        help="image file path or URL",
    )
    args = parser.parse_args([] if is_test else None)
    validate_on_device_demo_args(args, MODEL_ID)

    # Load image & model
    model = demo_model_from_cli_args(model_cls, MODEL_ID, args)
    image = load_image(args.image)

    print("Model Loaded")

    h, w = model_cls.get_input_spec()["image"][0][1:3]
    app = MovenetApp(model, h, w)
    keypoints = app.predict_pose_keypoints(image)[0]
    if isinstance(keypoints, np.ndarray):
        keypoints = Image.fromarray(keypoints.astype(np.uint8))
    if not is_test:
        display_or_save_image(
            keypoints, args.output_dir, "movenet_demo_output.png", "keypoints"
        )


def main(is_test: bool = False):
    return movenet_demo(Movenet, is_test)


if __name__ == "__main__":
    main()
