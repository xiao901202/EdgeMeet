# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
# THIS FILE WAS AUTO-GENERATED. DO NOT EDIT MANUALLY.


from __future__ import annotations

import os
import shutil
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional, cast

import qai_hub as hub

from qai_hub_models.models.common import ExportResult, Precision, TargetRuntime
from qai_hub_models.models.controlnet import Model
from qai_hub_models.utils.args import export_parser, validate_precision_runtime
from qai_hub_models.utils.base_model import CollectionModel
from qai_hub_models.utils.printing import print_profile_metrics_from_job
from qai_hub_models.utils.qai_hub_helpers import (
    can_access_qualcomm_ai_hub,
    export_without_hub_access,
)


def profile_model(
    model_name: str,
    hub_device: hub.Device,
    components: list[str],
    profile_options: dict[str, str],
    target_runtime: TargetRuntime,
    uploaded_models: dict[str, hub.Model],
) -> dict[str, hub.client.ProfileJob]:
    profile_jobs: dict[str, hub.client.ProfileJob] = {}
    for component_name in components:
        print(f"Profiling model {component_name} on a hosted device.")
        submitted_profile_job = hub.submit_profile_job(
            model=uploaded_models[component_name],
            device=hub_device,
            name=f"{model_name}_{component_name}",
            options=profile_options.get(component_name, ""),
        )
        profile_jobs[component_name] = cast(
            hub.client.ProfileJob, submitted_profile_job
        )
    return profile_jobs


def inference_model(
    model: CollectionModel,
    model_name: str,
    hub_device: hub.Device,
    components: list[str],
    profile_options: str,
    target_runtime: TargetRuntime,
    uploaded_models: dict[str, hub.Model],
) -> dict[str, hub.client.InferenceJob]:
    inference_jobs: dict[str, hub.client.InferenceJob] = {}
    for component_name in components:
        print(
            f"Running inference for {component_name} on a hosted device with example inputs."
        )
        profile_options_all = model.components[component_name].get_hub_profile_options(
            target_runtime, profile_options
        )
        sample_inputs = model.components[component_name].sample_inputs(
            use_channel_last_format=target_runtime.channel_last_native_execution
        )
        submitted_inference_job = hub.submit_inference_job(
            model=uploaded_models[component_name],
            inputs=sample_inputs,
            device=hub_device,
            name=f"{model_name}_{component_name}",
            options=profile_options_all,
        )
        inference_jobs[component_name] = cast(
            hub.client.InferenceJob, submitted_inference_job
        )
    return inference_jobs


def download_model(
    output_path: Path,
    compile_jobs: dict[str, hub.client.CompileJob],
) -> None:
    os.makedirs(output_path, exist_ok=True)
    for component_name, compile_job in compile_jobs.items():
        target_model = compile_job.get_target_model()
        assert target_model is not None
        target_model.download(str(output_path / component_name))


def export_model(
    device: Optional[str] = None,
    chipset: Optional[str] = None,
    components: Optional[list[str]] = None,
    skip_profiling: bool = False,
    skip_inferencing: bool = False,
    skip_summary: bool = False,
    output_dir: Optional[str] = None,
    profile_options: str = "",
    fetch_static_assets: bool = False,
    **additional_model_kwargs,
) -> Mapping[str, ExportResult] | list[str]:
    """
    This function executes the following recipe:

        1. Initialize model
        2. Saves the model asset to the output directory
        3. Upload model assets to hub
        4. Profiles the model performance on a real device
        5. Summarizes the results from profiling

    Each of the last 3 steps can be optionally skipped using the input options.

    Parameters:
        device: Device for which to export the model.
            Full list of available devices can be found by running `hub.get_devices()`.
            Defaults to DEFAULT_DEVICE if not specified.
        chipset: If set, will choose a random device with this chipset.
            Overrides the `device` argument.
        components: List of sub-components of the model that will be exported.
            Each component is compiled and profiled separately.
            Defaults to all components of the CollectionModel if not specified.
        skip_profiling: If set, skips profiling of compiled model on real devices.
        skip_inferencing: If set, skips computing on-device outputs from sample data.
        skip_summary: If set, skips waiting for and summarizing results
            from profiling.
        output_dir: Directory to store generated assets (e.g. compiled model).
            Defaults to `<cwd>/build/<model_name>`.
        profile_options: Additional options to pass when submitting the profile job.
        fetch_static_assets: If true, static assets are fetched from Hugging Face, rather than re-compiling / quantizing / profiling from PyTorch.
        **additional_model_kwargs: Additional optional kwargs used to customize
            `model_cls.from_precompiled`

    Returns:
        A Mapping from component_name to a struct of:
            * A ProfileJob containing metadata about the profile job (None if profiling skipped).
    """
    if not skip_inferencing:
        raise ValueError(
            "This model does not support inferencing. Please pass --skip-inferencing"
        )
    model_name = "controlnet"
    output_path = Path(output_dir or Path.cwd() / "build" / model_name)
    if not device and not chipset:
        hub_device = hub.Device("Samsung Galaxy S24 (Family)")
    else:
        hub_device = hub.Device(
            name=device or "", attributes=f"chipset:{chipset}" if chipset else []
        )
    component_arg = components
    components = components or Model.component_class_names
    for component_name in components:
        if component_name not in Model.component_class_names:
            raise ValueError(f"Invalid component {component_name}.")
    if fetch_static_assets or not can_access_qualcomm_ai_hub():
        return export_without_hub_access(
            "controlnet",
            "ControlNet",
            hub_device.name or f"Device (Chipset {chipset})",
            skip_profiling,
            skip_inferencing,
            False,
            skip_summary,
            output_path,
            TargetRuntime.QNN_CONTEXT_BINARY,
            Precision.w8a16,
            "",
            profile_options,
            component_arg,
            is_forced_static_asset_fetch=fetch_static_assets,
        )

    target_runtime = TargetRuntime.QNN_CONTEXT_BINARY
    # 1. Initialize model
    print("Initializing model class")
    model = Model.from_precompiled()
    # 2. Saves the model asset to the output directory
    os.makedirs(output_path, exist_ok=True)
    for component_name in components:
        path = model.components[component_name].get_target_model_path()
        dst_path = output_path / os.path.basename(path)
        shutil.copyfile(src=path, dst=dst_path)
        print(f"The {component_name} model is saved here: {dst_path}")

    # 3. Upload model assets to hub
    uploaded_models: dict[str, hub.Model] = {}
    if not skip_profiling or not skip_inferencing:
        print("Uploading model assets on hub")
        path_for_uploaded_models: dict[str, hub.Model] = {}
        for component_name in components:
            path = model.components[component_name].get_target_model_path()
            if path not in path_for_uploaded_models:
                path_for_uploaded_models[path] = hub.upload_model(path)
            uploaded_models[component_name] = path_for_uploaded_models[path]

    # 4. Profiles the model performance on a real device
    profile_jobs: dict[str, hub.client.ProfileJob] = {}
    if not skip_profiling:
        profile_jobs = profile_model(
            model_name,
            hub_device,
            components,
            {
                component_name: model.components[
                    component_name
                ].get_hub_profile_options(target_runtime, profile_options)
                for component_name in components
            },
            target_runtime,
            uploaded_models,
        )

    # 5. Summarizes the results from profiling
    if not skip_summary and not skip_profiling:
        for component_name in components:
            profile_job = profile_jobs[component_name]
            assert profile_job.wait().success, "Job failed: " + profile_job.url
            profile_data: dict[str, Any] = profile_job.download_profile()
            print_profile_metrics_from_job(profile_job, profile_data)

    return {
        component_name: ExportResult(
            profile_job=profile_jobs.get(component_name, None),
        )
        for component_name in components
    }


def main():
    warnings.filterwarnings("ignore")
    supported_precision_runtimes: dict[Precision, list[TargetRuntime]] = {
        Precision.w8a16: [
            TargetRuntime.QNN_CONTEXT_BINARY,
        ],
    }

    parser = export_parser(
        model_cls=Model,
        supported_precision_runtimes=supported_precision_runtimes,
        uses_quantize_job=False,
        exporting_compiled_model=True,
    )
    args = parser.parse_args()
    validate_precision_runtime(
        supported_precision_runtimes, Precision.w8a16, args.target_runtime
    )
    export_model(**vars(args))


if __name__ == "__main__":
    main()
