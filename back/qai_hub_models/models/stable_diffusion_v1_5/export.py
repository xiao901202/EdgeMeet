# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
# THIS FILE WAS AUTO-GENERATED. DO NOT EDIT MANUALLY.


from __future__ import annotations

import os
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional, cast

import qai_hub as hub

from qai_hub_models.models.common import ExportResult, Precision, TargetRuntime
from qai_hub_models.models.stable_diffusion_v1_5 import Model
from qai_hub_models.utils.args import (
    export_parser,
    get_model_kwargs,
    validate_precision_runtime,
)
from qai_hub_models.utils.base_model import BaseModel, CollectionModel
from qai_hub_models.utils.compare import torch_inference
from qai_hub_models.utils.printing import (
    print_inference_metrics,
    print_profile_metrics_from_job,
)
from qai_hub_models.utils.qai_hub_helpers import (
    can_access_qualcomm_ai_hub,
    export_without_hub_access,
)


def compile_model(
    model: CollectionModel,
    model_name: str,
    hub_device: hub.Device,
    components: list[str],
    compile_options: str,
    target_runtime: TargetRuntime,
    output_path: Path,
) -> dict[str, hub.client.CompileJob]:
    compile_jobs: dict[str, hub.client.CompileJob] = {}
    for component_name in components:
        component = model.components[component_name]
        assert isinstance(component, BaseModel)
        input_spec = component.get_input_spec()
        # Trace the model
        source_model = component.convert_to_hub_source_model(
            target_runtime, output_path, input_spec
        )

        model_compile_options = component.get_hub_compile_options(
            target_runtime, Precision.w8a16, compile_options, hub_device
        )
        print(f"Optimizing model {component_name} to run on-device")
        submitted_compile_job = hub.submit_compile_job(
            model=source_model,
            input_specs=input_spec,
            device=hub_device,
            name=f"{model_name}_{component_name}",
            options=model_compile_options,
        )
        compile_jobs[component_name] = cast(
            hub.client.CompileJob, submitted_compile_job
        )
    return compile_jobs


def profile_model(
    model_name: str,
    hub_device: hub.Device,
    components: list[str],
    profile_options: dict[str, str],
    target_runtime: TargetRuntime,
    compile_jobs: dict[str, hub.client.CompileJob],
) -> dict[str, hub.client.ProfileJob]:
    profile_jobs: dict[str, hub.client.ProfileJob] = {}
    for component_name in components:
        print(f"Profiling model {component_name} on a hosted device.")
        submitted_profile_job = hub.submit_profile_job(
            model=compile_jobs[component_name].get_target_model(),
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
    compile_jobs: dict[str, hub.client.CompileJob],
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
            model=compile_jobs[component_name].get_target_model(),
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
    precision: Precision = Precision.w8a16,
    skip_profiling: bool = False,
    skip_inferencing: bool = False,
    skip_downloading: bool = False,
    skip_summary: bool = False,
    output_dir: Optional[str] = None,
    target_runtime: TargetRuntime = TargetRuntime.QNN_CONTEXT_BINARY,
    compile_options: str = "",
    profile_options: str = "",
    fetch_static_assets: bool = False,
    **additional_model_kwargs,
) -> Mapping[str, ExportResult] | list[str]:
    """
    This function executes the following recipe:

        1. Instantiates a PyTorch model and converts it to a traced TorchScript format
        2. Compiles the model to an asset that can be run on device
        3. Profiles the model performance on a real device
        4. Inferences the model on sample inputs
        5. Downloads the model asset to the local directory
        6. Summarizes the results from profiling and inference

    Each of the last 4 steps can be optionally skipped using the input options.

    Parameters:
        device: Device for which to export the model.
            Full list of available devices can be found by running `hub.get_devices()`.
            Defaults to DEFAULT_DEVICE if not specified.
        chipset: If set, will choose a random device with this chipset.
            Overrides the `device` argument.
        components: List of sub-components of the model that will be exported.
            Each component is compiled and profiled separately.
            Defaults to all components of the CollectionModel if not specified.
        precision: The precision to which this model should be quantized.
            Quantization is skipped if the precision is float.
        skip_profiling: If set, skips profiling of compiled model on real devices.
        skip_inferencing: If set, skips computing on-device outputs from sample data.
        skip_downloading: If set, skips downloading of compiled model.
        skip_summary: If set, skips waiting for and summarizing results
            from profiling and inference.
        output_dir: Directory to store generated assets (e.g. compiled model).
            Defaults to `<cwd>/build/<model_name>`.
        target_runtime: Which on-device runtime to target. Default is TFLite.
        compile_options: Additional options to pass when submitting the compile job.
        profile_options: Additional options to pass when submitting the profile job.
        fetch_static_assets: If true, static assets are fetched from Hugging Face, rather than re-compiling / quantizing / profiling from PyTorch.
        **additional_model_kwargs: Additional optional kwargs used to customize
            `model_cls.from_pretrained`

    Returns:
        A Mapping from component_name to a struct of:
            * A CompileJob object containing metadata about the compile job submitted to hub.
            * An InferenceJob containing metadata about the inference job (None if inferencing skipped).
            * A ProfileJob containing metadata about the profile job (None if profiling skipped).
    """
    model_name = "stable_diffusion_v1_5"
    output_path = Path(output_dir or Path.cwd() / "build" / model_name)
    if not device and not chipset:
        hub_device = hub.Device("Samsung Galaxy S24 (Family)")
    else:
        hub_device = hub.Device(
            name=device or "", attributes=f"chipset:{chipset}" if chipset else []
        )
    assert precision in [
        Precision.w8a16,
    ], f"Precision {str(precision)} is not supported by {model_name}"
    component_arg = components
    components = components or Model.component_class_names
    for component_name in components:
        if component_name not in Model.component_class_names:
            raise ValueError(f"Invalid component {component_name}.")
    if fetch_static_assets or not can_access_qualcomm_ai_hub():
        return export_without_hub_access(
            "stable_diffusion_v1_5",
            "Stable-Diffusion-v1.5",
            hub_device.name or f"Device (Chipset {chipset})",
            skip_profiling,
            skip_inferencing,
            skip_downloading,
            skip_summary,
            output_path,
            target_runtime,
            precision,
            compile_options,
            profile_options,
            component_arg,
            is_forced_static_asset_fetch=fetch_static_assets,
        )

    # 1. Instantiates a PyTorch model and converts it to a traced TorchScript format
    model = Model.from_pretrained(
        **get_model_kwargs(Model, dict(**additional_model_kwargs, precision=precision))
    )

    # 2. Compiles the model to an asset that can be run on device
    compile_jobs = compile_model(
        model,
        model_name,
        hub_device,
        components,
        compile_options,
        target_runtime,
        output_path,
    )

    # 3. Profiles the model performance on a real device
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
            compile_jobs,
        )

    # 4. Inferences the model on sample inputs
    inference_jobs: dict[str, hub.client.InferenceJob] = {}
    if not skip_inferencing:
        inference_jobs = inference_model(
            model,
            model_name,
            hub_device,
            components,
            profile_options,
            target_runtime,
            compile_jobs,
        )

    # 5. Downloads the model asset to the local directory
    if not skip_downloading:
        download_model(output_path, compile_jobs)

    # 6. Summarizes the results from profiling and inference
    if not skip_summary and not skip_profiling:
        for component_name in components:
            profile_job = profile_jobs[component_name]
            assert profile_job.wait().success, "Job failed: " + profile_job.url
            profile_data: dict[str, Any] = profile_job.download_profile()
            print_profile_metrics_from_job(profile_job, profile_data)

    if not skip_summary and not skip_inferencing:
        for component_name in components:
            component = model.components[component_name]
            assert isinstance(component, BaseModel)
            inference_job = inference_jobs[component_name]
            sample_inputs = component.sample_inputs(use_channel_last_format=False)
            torch_out = torch_inference(
                component,
                sample_inputs,
                return_channel_last_output=target_runtime.channel_last_native_execution,
            )
            assert inference_job.wait().success, "Job failed: " + inference_job.url
            inference_result = inference_job.download_output_data()
            assert inference_result is not None

            print_inference_metrics(
                inference_job, inference_result, torch_out, component.get_output_names()
            )

    return {
        component_name: ExportResult(
            compile_job=compile_jobs[component_name],
            inference_job=inference_jobs.get(component_name, None),
            profile_job=profile_jobs.get(component_name, None),
        )
        for component_name in components
    }


def main():
    warnings.filterwarnings("ignore")
    supported_precision_runtimes: dict[Precision, list[TargetRuntime]] = {
        Precision.w8a16: [
            TargetRuntime.QNN_CONTEXT_BINARY,
            TargetRuntime.PRECOMPILED_QNN_ONNX,
        ],
    }

    parser = export_parser(
        model_cls=Model,
        supported_precision_runtimes=supported_precision_runtimes,
        uses_quantize_job=False,
    )
    args = parser.parse_args()
    validate_precision_runtime(
        supported_precision_runtimes, args.precision, args.target_runtime
    )
    export_model(**vars(args))


if __name__ == "__main__":
    main()
