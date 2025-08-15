# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

import warnings

from qai_hub_models.models._shared.llama3.export import export_model
from qai_hub_models.models.common import Precision, TargetRuntime
from qai_hub_models.models.llama_v3_1_sea_lion_3_5_8b_r import MODEL_ID, FP_Model, Model
from qai_hub_models.models.llama_v3_1_sea_lion_3_5_8b_r.model import (
    MODEL_ASSET_VERSION,
    NUM_LAYERS_PER_SPLIT,
    NUM_SPLITS,
)
from qai_hub_models.utils.args import enable_model_caching, export_parser

DEFAULT_EXPORT_DEVICE = "Snapdragon 8 Elite QRD"

ALL_COMPONENTS = [f"part_{i + 1}_of_{NUM_SPLITS}" for i in range(NUM_SPLITS)]

# Each components is two sub-components linked together with shared weights
ALL_SUB_COMPONENTS = {
    f"part_{i + 1}_of_{NUM_SPLITS}": [
        f"prompt_{i + 1}_of_{NUM_SPLITS}",
        f"token_{i + 1}_of_{NUM_SPLITS}",
    ]
    for i in range(NUM_SPLITS)
}


def main():
    warnings.filterwarnings("ignore")
    parser = export_parser(
        model_cls=Model,
        supported_precision_runtimes={
            Precision.w4a16: [TargetRuntime.QNN_CONTEXT_BINARY]
        },
        default_export_device=DEFAULT_EXPORT_DEVICE,
    )
    parser.add_argument(
        "--synchronous",
        action="store_true",
        help="Wait for each command to finish before submitting new.",
    )
    parser = enable_model_caching(parser)
    parser.set_defaults(_skip_quantsim_creation=True)
    args = parser.parse_args()
    additional_model_kwargs = vars(args)
    if additional_model_kwargs["checkpoint"] == "DEFAULT":
        additional_model_kwargs["fp_model"] = FP_Model.from_pretrained(  # type: ignore[index]
            sequence_length=args.sequence_length,
            context_length=args.context_length,
        )
    export_model(
        model_cls=Model,
        model_name=MODEL_ID,
        model_asset_version=MODEL_ASSET_VERSION,
        components=ALL_COMPONENTS,
        sub_components=ALL_SUB_COMPONENTS,
        num_layers_per_split=NUM_LAYERS_PER_SPLIT,
        **additional_model_kwargs,
    )


if __name__ == "__main__":
    main()
