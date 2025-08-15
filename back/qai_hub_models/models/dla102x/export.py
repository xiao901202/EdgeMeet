# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
# THIS FILE WAS AUTO-GENERATED. DO NOT EDIT MANUALLY.


from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any, Optional, cast

import qai_hub as hub
import torch

from qai_hub_models.models.common import ExportResult, Precision, TargetRuntime
from qai_hub_models.models.dla102x import Model
from qai_hub_models.utils import quantization as quantization_utils
from qai_hub_models.utils.args import (
    export_parser,
    get_input_spec_kwargs,
    get_model_kwargs,
    validate_precision_runtime,
)
from qai_hub_models.utils.base_model import BaseModel
from qai_hub_models.utils.compare import torch_inference
from qai_hub_models.utils.input_spec import InputSpec, make_torch_inputs
from qai_hub_models.utils.printing import (
    print_inference_metrics,
    print_profile_metrics_from_job,
)
from qai_hub_models.utils.qai_hub_helpers import (
    can_access_qualcomm_ai_hub,
    export_without_hub_access,
)


def quantize_model(
    precision: Precision,
    model: BaseModel,
    model_name: str,
    hub_device: hub.Device,
    input_spec: InputSpec,
    num_calibration_samples: int | None,
) -> hub.client.QuantizeJob | None:
    quantize_job = None
    if precision != Precision.float:
        source_model = torch.jit.trace(model.to("cpu"), make_torch_inputs(input_spec))
        print(f"Quantizing model {model_name}.")
        onnx_compile_job = hub.submit_compile_job(
            model=source_model,
            input_specs=input_spec,
            device=hub_device,
            name=model_name,
            options="--target_runtime onnx",
        )

        if not precision.activations_type or not precision.weights_type:
            raise ValueError(
                "Quantization is only supported if both weights and activations are quantized."
            )

        calibration_data = quantization_utils.get_calibration_data(
            model, input_spec, num_calibration_samples
        )
        quantize_job = hub.submit_quantize_job(
            model=onnx_compile_job.get_target_model(),
            calibration_data=calibration_data,
            activations_dtype=precision.activations_type,
            weights_dtype=precision.weights_type,
            name=model_name,
            options=model.get_hub_quantize_options(precision),
        )
    return quantize_job


def compile_model(
    model: BaseModel,
    model_name: str,
    hub_device: hub.Device,
    input_spec: InputSpec,
    compile_options: str,
    target_runtime: TargetRuntime,
    precision: Precision,
    quantize_job: hub.client.QuantizeJob | None,
) -> hub.client.CompileJob:
    if quantize_job:
        source_model = quantize_job.get_target_model()
    else:
        # Trace the model
        source_model = torch.jit.trace(model.to("cpu"), make_torch_inputs(input_spec))

    model_compile_options = model.get_hub_compile_options(
        target_runtime, precision, compile_options, hub_device
    )
    print(f"Optimizing model {model_name} to run on-device")
    submitted_compile_job = hub.submit_compile_job(
        model=source_model,
        input_specs=input_spec,
        device=hub_device,
        name=model_name,
        options=model_compile_options,
    )
    compile_job = cast(hub.client.CompileJob, submitted_compile_job)
    return compile_job


def profile_model(
    model_name: str,
    hub_device: hub.Device,
    profile_options: str,
    target_runtime: TargetRuntime,
    compile_job: hub.client.CompileJob,
) -> hub.client.ProfileJob:
    print(f"Profiling model {model_name} on a hosted device.")
    submitted_profile_job = hub.submit_profile_job(
        model=compile_job.get_target_model(),
        device=hub_device,
        name=model_name,
        options=profile_options,
    )
    profile_job = cast(hub.client.ProfileJob, submitted_profile_job)
    return profile_job


def inference_model(
    model: BaseModel,
    model_name: str,
    hub_device: hub.Device,
    input_spec: InputSpec,
    profile_options: str,
    target_runtime: TargetRuntime,
    compile_job: hub.client.CompileJob,
) -> hub.client.InferenceJob:
    profile_options_all = model.get_hub_profile_options(target_runtime, profile_options)
    print(f"Running inference for {model_name} on a hosted device with example inputs.")
    sample_inputs = model.sample_inputs(
        input_spec, use_channel_last_format=target_runtime.channel_last_native_execution
    )
    submitted_inference_job = hub.submit_inference_job(
        model=compile_job.get_target_model(),
        inputs=sample_inputs,
        device=hub_device,
        name=model_name,
        options=profile_options_all,
    )
    inference_job = cast(hub.client.InferenceJob, submitted_inference_job)
    return inference_job


def download_model(
    output_path: Path,
    compile_job: hub.client.CompileJob,
    model_name: str,
) -> None:
    os.makedirs(output_path, exist_ok=True)
    target_model = compile_job.get_target_model()
    assert target_model is not None
    target_model.download(str(output_path / model_name))


def export_model(
    device: Optional[str] = None,
    chipset: Optional[str] = None,
    precision: Precision = Precision.float,
    num_calibration_samples: int | None = None,
    skip_compiling: bool = False,
    skip_profiling: bool = False,
    skip_inferencing: bool = False,
    skip_downloading: bool = False,
    skip_summary: bool = False,
    output_dir: Optional[str] = None,
    target_runtime: TargetRuntime = TargetRuntime.TFLITE,
    compile_options: str = "",
    profile_options: str = "",
    fetch_static_assets: bool = False,
    **additional_model_kwargs,
) -> ExportResult | list[str]:
    """
    This function executes the following recipe:

        1. Instantiates a PyTorch model and converts it to a traced TorchScript format
        2. Converts the PyTorch model to ONNX and quantizes the ONNX model.
        3. Compiles the model to an asset that can be run on device
        4. Profiles the model performance on a real device
        5. Inferences the model on sample inputs
        6. Downloads the model asset to the local directory
        7. Summarizes the results from profiling and inference

    Each of the last 5 steps can be optionally skipped using the input options.

    Parameters:
        device: Device for which to export the model.
            Full list of available devices can be found by running `hub.get_devices()`.
            Defaults to DEFAULT_DEVICE if not specified.
        chipset: If set, will choose a random device with this chipset.
            Overrides the `device` argument.
        precision: The precision to which this model should be quantized.
            Quantization is skipped if the precision is float.
        num_calibration_samples: The number of calibration data samples
            to use for quantization. If not set, uses the default number
            specified by the dataset. If model doesn't have a calibration dataset
            specified, this must be None.
        skip_compiling: If set, skips compiling model to format that can run on device.
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
            `model_cls.from_pretrained` and `model.get_input_spec`

    Returns:
        A struct of:
            * A CompileJob object containing metadata about the compile job submitted to hub (None if compiling skipped).
            * An InferenceJob containing metadata about the inference job (None if inferencing skipped).
            * A ProfileJob containing metadata about the profile job (None if profiling skipped).
            * A QuantizeJob object containing metadata about the quantize job submitted to hub
    """
    model_name = "dla102x"
    output_path = Path(output_dir or Path.cwd() / "build" / model_name)
    if not device and not chipset:
        hub_device = hub.Device("Samsung Galaxy S24 (Family)")
    else:
        hub_device = hub.Device(
            name=device or "", attributes=f"chipset:{chipset}" if chipset else []
        )
    if fetch_static_assets or not can_access_qualcomm_ai_hub():
        return export_without_hub_access(
            "dla102x",
            "DLA-102-X",
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
            is_forced_static_asset_fetch=fetch_static_assets,
        )

    # 1. Instantiates a PyTorch model and converts it to a traced TorchScript format
    model = Model.from_pretrained(
        **get_model_kwargs(Model, dict(**additional_model_kwargs, precision=precision))
    )
    input_spec = model.get_input_spec(
        **get_input_spec_kwargs(model, additional_model_kwargs)
    )

    # 2. Converts the PyTorch model to ONNX and quantizes the ONNX model.
    quantize_job = quantize_model(
        precision,
        model,
        model_name,
        hub_device,
        input_spec,
        num_calibration_samples,
    )
    if precision != Precision.float and skip_compiling:
        return ExportResult(quantize_job=quantize_job)

    # 3. Compiles the model to an asset that can be run on device
    compile_job = compile_model(
        model,
        model_name,
        hub_device,
        input_spec,
        compile_options,
        target_runtime,
        precision,
        quantize_job,
    )

    # 4. Profiles the model performance on a real device
    profile_job: Optional[hub.client.ProfileJob] = None
    if not skip_profiling:
        profile_job = profile_model(
            model_name,
            hub_device,
            model.get_hub_profile_options(target_runtime, profile_options),
            target_runtime,
            compile_job,
        )

    # 5. Inferences the model on sample inputs
    inference_job: Optional[hub.client.InferenceJob] = None
    if not skip_inferencing:
        inference_job = inference_model(
            model,
            model_name,
            hub_device,
            input_spec,
            profile_options,
            target_runtime,
            compile_job,
        )

    # 6. Downloads the model asset to the local directory
    if not skip_downloading:
        download_model(output_path, compile_job, model_name)

    # 7. Summarizes the results from profiling and inference
    if not skip_summary and profile_job is not None:
        assert profile_job.wait().success, "Job failed: " + profile_job.url
        profile_data: dict[str, Any] = profile_job.download_profile()
        print_profile_metrics_from_job(profile_job, profile_data)

    if not skip_summary and inference_job is not None:
        sample_inputs = model.sample_inputs(input_spec, use_channel_last_format=False)
        torch_out = torch_inference(
            model,
            sample_inputs,
            return_channel_last_output=target_runtime.channel_last_native_execution,
        )
        assert inference_job.wait().success, "Job failed: " + inference_job.url
        inference_result = inference_job.download_output_data()
        assert inference_result is not None

        print_inference_metrics(
            inference_job, inference_result, torch_out, model.get_output_names()
        )

    return ExportResult(
        compile_job=compile_job,
        inference_job=inference_job,
        profile_job=profile_job,
        quantize_job=quantize_job,
    )


def main():
    warnings.filterwarnings("ignore")
    supported_precision_runtimes: dict[Precision, list[TargetRuntime]] = {
        Precision.float: [
            TargetRuntime.TFLITE,
            TargetRuntime.QNN_DLC,
            TargetRuntime.QNN_CONTEXT_BINARY,
            TargetRuntime.ONNX,
            TargetRuntime.PRECOMPILED_QNN_ONNX,
        ],
    }

    parser = export_parser(
        model_cls=Model,
        supported_precision_runtimes=supported_precision_runtimes,
    )
    args = parser.parse_args()
    validate_precision_runtime(
        supported_precision_runtimes, args.precision, args.target_runtime
    )
    export_model(**vars(args))


if __name__ == "__main__":
    main()
