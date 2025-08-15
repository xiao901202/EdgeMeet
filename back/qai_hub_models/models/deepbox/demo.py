# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from PIL import Image

from qai_hub_models.models.deepbox.app import DeepBoxApp
from qai_hub_models.models.deepbox.model import MODEL_ASSET_VERSION, MODEL_ID, DeepBox
from qai_hub_models.utils.args import get_model_cli_parser, get_on_device_demo_parser
from qai_hub_models.utils.asset_loaders import CachedWebModelAsset, load_image
from qai_hub_models.utils.display import display_or_save_image

INPUT_IMAGE_ADDRESS = CachedWebModelAsset.from_asset_store(
    MODEL_ID, MODEL_ASSET_VERSION, "input_image.png"
)


def deepbox_demo(
    model_type: type[DeepBox],
    default_image: CachedWebModelAsset,
    is_test: bool = False,
):
    # Demo parameters
    parser = get_model_cli_parser(model_type)
    parser = get_on_device_demo_parser(parser, add_output_dir=True)
    parser.add_argument(
        "--image",
        type=str,
        default=default_image,
        help="image file path or URL",
    )
    args = parser.parse_args([] if is_test else None)

    wrapper = model_type.from_pretrained()
    app = DeepBoxApp(
        wrapper.yolo_2d_det,
        wrapper.vgg_3d_det,
    )
    print("Model Loaded")

    image = load_image(args.image)

    output = app.detect_image(image)
    assert isinstance(output, Image.Image)

    if not is_test:
        display_or_save_image(output, args.output_dir)


def main(is_test: bool = False) -> None:
    deepbox_demo(DeepBox, INPUT_IMAGE_ADDRESS, is_test)


if __name__ == "__main__":
    main()
