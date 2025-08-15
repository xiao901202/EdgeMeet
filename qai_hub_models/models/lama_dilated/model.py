# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

import logging
from importlib import reload

import torch
from omegaconf import OmegaConf

from qai_hub_models.models._shared.repaint.model import RepaintModel
from qai_hub_models.utils.asset_loaders import (
    CachedWebModelAsset,
    SourceAsRoot,
    load_json,
    load_torch,
    set_log_level,
)

LAMA_SOURCE_REPOSITORY = "https://github.com/advimman/lama"
LAMA_SOURCE_REPO_COMMIT = "7dee0e4a3cf5f73f86a820674bf471454f52b74f"
MODEL_ID = __name__.split(".")[-2]
MODEL_ASSET_VERSION = 1
DEFAULT_WEIGHTS = "lama-dilated_celeba-hq"
MODEL_ASSET_VERSION = 1


class LamaDilated(RepaintModel):
    """Exportable LamaDilated inpainting algorithm by Samsung Research."""

    @staticmethod
    def from_pretrained(weights_name: str = DEFAULT_WEIGHTS) -> LamaDilated:
        """Load LamaDilated from a weights file created by the source LaMa repository."""

        # Load PyTorch model from disk
        lama_dilated_model = _load_lama_dilated_source_model_from_weights(weights_name)

        return LamaDilated(lama_dilated_model)

    def forward(self, image: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        """
        Run LamaDilated on `image` and `mask`, and produce an image with mask area inpainted.

        Parameters:
            image: Pixel values pre-processed for encoder consumption.
                   Range: float[0, 1]
                   3-channel Color Space: RGB

            mask: Pixel values pre-processed to have have mask values either 0. or 1.
                  Range: float[0, 1] and only values of 0. or 1.
                  1-channel binary image.

        Returns:
            inpainted_image: Pixel values
                   Range: float[0, 1]
                   3-channel Color Space: RGB
        """

        masked_img = image * (1 - mask)

        if self.model.concat_mask:
            masked_img = torch.cat([masked_img, mask], dim=1)

        predicted_image = self.model.generator(masked_img)
        inpainted = mask * predicted_image + (1 - mask) * image
        return inpainted


def _get_weightsfile_from_name(weights_name: str):
    """Convert from names of weights files to the url for the weights file"""
    return CachedWebModelAsset.from_asset_store(
        MODEL_ID, MODEL_ASSET_VERSION, f"checkpoints/{weights_name}.ckpt"
    )


def _get_config_url():
    """Get the url for the config file"""
    return CachedWebModelAsset.from_asset_store(
        MODEL_ID, MODEL_ASSET_VERSION, "checkpoints/training_config.json"
    )


def _load_lama_dilated_source_model_from_weights(weights_name: str) -> torch.nn.Module:
    # Load LamaDilated model from the source repository using the given weights.
    weights_url = _get_weightsfile_from_name(weights_name)
    config_url = _get_config_url()

    with SourceAsRoot(
        LAMA_SOURCE_REPOSITORY, LAMA_SOURCE_REPO_COMMIT, MODEL_ID, MODEL_ASSET_VERSION
    ):
        # This repository has a top-level "models", which is common. We
        # explicitly reload it in case it has been loaded and cached by another
        # package (or our models when executing from qai_hub_models/)
        import models

        reload(models)

        # Import module
        from saicinpainting.training.trainers.default import (
            DefaultInpaintingTrainingModule,
        )

        # Pass config as needed to create the module for tracing.
        config_json = load_json(config_url)
        config = OmegaConf.create(config_json)
        kwargs = dict(config.training_model)
        kwargs.pop("kind")
        kwargs["use_ddp"] = True
        state = load_torch(weights_url)
        with set_log_level(logging.WARN):
            lama_dilated_model = DefaultInpaintingTrainingModule(config, **kwargs)
            # Needed for pytorch-lightning to script the module appropriately.
            lama_dilated_model._jit_is_scripting = True

        lama_dilated_model.load_state_dict(state["state_dict"], strict=False)
        lama_dilated_model.on_load_checkpoint(state)
        lama_dilated_model.freeze()

        return lama_dilated_model
