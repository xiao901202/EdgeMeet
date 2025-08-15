# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

import os
import re
import shutil
import time
import zipfile
from os import PathLike
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import onnx
import qai_hub as hub
import torch
from qai_hub.client import APIException, DatasetEntries, Device, UserError

from qai_hub_models.configs.perf_yaml import QAIHMModelPerf
from qai_hub_models.models.common import Precision, TargetRuntime
from qai_hub_models.scorecard.device import ScorecardDevice
from qai_hub_models.utils.asset_loaders import ASSET_CONFIG, qaihm_temp_dir
from qai_hub_models.utils.huggingface import fetch_huggingface_target_model
from qai_hub_models.utils.onnx_helpers import (
    torch_onnx_export_with_large_model_size_check,
)
from qai_hub_models.utils.printing import print_profile_metrics
from qai_hub_models.utils.transpose_channel import (  # noqa: F401
    transpose_channel_first_to_last,
)


def can_access_qualcomm_ai_hub():
    try:
        hub.get_devices()
    except APIException:
        return False
    except UserError:
        return False
    return True


_AIHUB_URL = "https://aihub.qualcomm.com"
_AIHUB_NAME = "Qualcomm® AI Hub"
_WARNING_DASH = "=" * 114


def export_without_hub_access(
    model_id: str,
    model_display_name: str,
    device: str,
    skip_profiling: bool,
    skip_inferencing: bool,
    skip_downloading: bool,
    skip_summary: bool,
    output_path: str | Path,
    target_runtime: TargetRuntime,
    precision: Precision,
    compile_options: str,
    profile_options: str,
    components: Optional[list[str]] = None,
    is_forced_static_asset_fetch: bool = False,
) -> list[str]:
    if not is_forced_static_asset_fetch:
        print(_WARNING_DASH)
        print(
            f"Unable to find a valid API token for {_AIHUB_NAME}. Using results from a previous job run on the same device.\n"
            f"To get access to the complete experience, please sign-up for access at {_AIHUB_URL}."
        )
        print(_WARNING_DASH)

    if compile_options or profile_options:
        raise RuntimeError(
            f"Jobs with `compile_options` or `profile_options` can only be run with {_AIHUB_NAME} access."
        )

    parsed_perf = None
    perf_yaml_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "models",
        model_id,
        "perf.yaml",
    )
    if os.path.exists(perf_yaml_path):
        parsed_perf = QAIHMModelPerf.from_yaml(perf_yaml_path).precisions[precision]

    if not components:
        if parsed_perf:
            components = list(parsed_perf.components.keys())
        else:
            components = [model_display_name]

    if not skip_profiling and not skip_summary:
        if parsed_perf is not None:
            print("\n--- Profiling Results ---")
            for component in components:
                print(f"{component}")
                model_perf = parsed_perf.components[component]

                # Device families aren't stored in perf yamls. Replace with the original device name.
                device_name = device.replace(" (Family)", "")
                device_perf = model_perf.performance_metrics.get(
                    ScorecardDevice.get(device_name)
                )
                if not device_perf:
                    break

                runtime_perf = None
                for path, path_runtime_perf in device_perf.items():
                    if path.runtime == target_runtime:
                        runtime_perf = path_runtime_perf
                        break

                if not runtime_perf:
                    break

                print_profile_metrics(
                    device_name,
                    target_runtime,
                    runtime_perf,
                    can_access_qualcomm_ai_hub=False,
                )
                print("")
        else:
            if is_forced_static_asset_fetch:
                print(
                    f"Cannot obtain results for device {device} with runtime {target_runtime.name} without using AI Hub.\n"
                    f"Run without the --fetch-static-assets flag to target this device."
                )
            else:
                print(
                    f"Cannot obtain results for device {device} with runtime {target_runtime.name} without an API token.\n"
                    f"Please sign-up for {_AIHUB_NAME} to run this configuration on hosted devices."
                )

    if not skip_inferencing and not skip_summary:
        print("\n--- Skipping on-device numerical validation. ---")
        if is_forced_static_asset_fetch:
            print("Run without the --fetch-static-assets flag to run validation.")
        else:
            print(
                f"Please sign-up for {_AIHUB_NAME} to perform numerical validation on hosted devices."
            )

    paths: list[str] = []
    if not skip_downloading:
        print(
            f"\n--- Downloading model(s) from Hugging Face: {ASSET_CONFIG.get_hugging_face_url(model_display_name)} ---"
        )
    else:
        print(
            f"\n--- Model(s) can be downloaded from Hugging Face: {ASSET_CONFIG.get_hugging_face_url(model_display_name)} ---"
        )
    try:
        paths, urls = fetch_huggingface_target_model(
            model_display_name,
            components,
            precision,
            output_path,
            target_runtime,
            download=not skip_downloading,
        )
        paths_str = "\n    ".join(paths)
        urls_str = "\n    ".join(urls)

        print(f"Deployable Model URLs:\n    {urls_str}")
        if paths:
            print("")
            print(f"Deployable model(s) saved to:\n    {paths_str}")
    except Exception as e:
        print(f"Model fetch failure: {e}")

    return paths


def tensor_to_numpy(tensor: torch.Tensor) -> np.ndarray:
    return tensor.cpu().detach().numpy()


def get_hub_endpoint():
    # The deployment endpoint is the subdomain of AIHub that is used by the config.
    # e.g. for blah endpoint, returns https://blah.aihub.qualcomm.com
    return hub.hub._global_client.config.api_url


def export_torch_to_onnx_zip(
    torch_model: torch.nn.Module,
    f: str | PathLike,
    example_input: tuple[torch.Tensor, ...] | list[torch.Tensor],
    input_names: list[str] | None = None,
    output_names: list[str] | None = None,
    onnx_transforms: Optional[Callable[[onnx.ModelProto], onnx.ModelProto]] = None,
    skip_zip: bool = False,
    torch_export_kwargs=None,
) -> str:
    """
    Export a torch model to ONNX, possibly as zip if model size exceeds 2GB,
    to conform to the input spec of AI Hub. Export as regular ONNX file if
    <2GB.

    Parameters:
      torch_model: The torch.nn.Module to export.
      f: The base filename. For models <2GB, this must end in ".onnx".
         For models >=2GB with skip_zip True, this must NOT end in ".onnx" (treated as a directory name).
         Otherwise, for models >=2GB with skip_zip False, the final output will be f+".zip".
      example_input: A tuple of example input tensors for the export.
      input_names: Optional list of input names.
      output_names: Optional list of output names.
      onnx_transforms: If defined, run this on the exported ONNX before packaging.
      skip_zip: True to suppress zipping even for models >2GB.

    Returns:
      The path to the exported file (either a .onnx file, a .onnx.zip file,
      or a directory if skip_zip is True and model size is >2GB).
    """
    f = Path(f)
    if isinstance(example_input, list):
        example_input = tuple(example_input)

    # Estimate total weight size (parameters and buffers) in bytes.
    # state_dict includes buffers etc, while model.parameters include only learnable params.
    total_bytes = 0
    for tensor in torch_model.state_dict().values():
        # Some tensors may not have a defined element_size() (e.g. non-numeric); skip them.
        if hasattr(tensor, "numel") and hasattr(tensor, "element_size"):
            total_bytes += tensor.numel() * tensor.element_size()
    threshold_bytes = 2 * 1024**3  # 2GB threshold

    torch_export_kwargs = torch_export_kwargs or {}

    if not f.name.endswith(".onnx"):
        f = f.with_suffix(".onnx")
    if total_bytes < threshold_bytes:
        # For models under 2GB, export as a single ONNX file.
        start_time = time.time()
        torch_onnx_export_with_large_model_size_check(
            torch_model,
            example_input,
            str(f),
            input_names=input_names,
            output_names=output_names,
            **torch_export_kwargs,
        )
        export_time = time.time() - start_time
        print(f"ONNX exported to {f} in {export_time:.1f} seconds")
        return str(f)
    else:
        # Export with external data using two temporary directories.
        with qaihm_temp_dir() as tmpdir1, qaihm_temp_dir() as tmpdir2:
            tmpdir1 = Path(tmpdir1)
            tmpdir2 = Path(tmpdir2)
            export_path = (
                tmpdir1 / f.with_suffix(".onnx").name
            )  # use .onnx extension for export

            start_time = time.time()
            torch_onnx_export_with_large_model_size_check(
                torch_model,
                example_input,
                str(export_path),
                input_names=input_names,
                output_names=output_names,
                **torch_export_kwargs,
            )
            export_time = time.time() - start_time
            print(f"torch.onnx.export finished in {export_time:.1f} seconds")

            onnx_model = onnx.load(str(export_path))

            if onnx_transforms is not None:
                transform_start_time = time.time()
                print("Running onnx to onnx transforms...")
                onnx_model = onnx_transforms(onnx_model)
                transform_time = time.time() - transform_start_time
                print(f"ONNX transform finished in {transform_time:.1f} seconds")

            save_start_time = time.time()
            # .onnx and .data must have the same base name per hub requirement
            export_path2 = tmpdir2 / "model.onnx"
            onnx.save_model(
                onnx_model,
                str(export_path2),
                save_as_external_data=True,
                all_tensors_to_one_file=True,
                # Weight file name must end with .data per Hub requirement
                location="model.data",
                convert_attribute=True,
            )
            save_time = time.time() - save_start_time
            print(f"onnx.save_model finished in {save_time:.1f} seconds")

            if skip_zip:
                # Instead of creating a zip, create a directory.
                out_dir = (
                    f  # f is expected to be a directory name already (without .onnx)
                )
                out_dir.mkdir(parents=True, exist_ok=True)

                # Copy the ONNX file to the directory.
                shutil.copy(export_path2, out_dir / "model.onnx")
                # Copy the external data file to the directory.
                external_data_path = export_path2.parent / "model.data"
                shutil.copy(external_data_path, out_dir / "model.data")

                print(f"ONNX with external data saved to directory {out_dir}")
                return str(out_dir)
            else:
                # Package the files into a zip.
                zip_start_time = time.time()
                zip_path = f.with_name(f.name + ".zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for file_path in tmpdir2.iterdir():
                        # In the zip, files are placed under a folder named after the base name.
                        arcname = f.with_suffix("").name + "/" + file_path.name
                        zip_file.write(file_path, arcname=arcname)
                zip_time = time.time() - zip_start_time
                print(f"zipping onnx finished in {zip_time:.1f} seconds")
                print(f"ONNX with external data saved to {zip_path}")
                return str(zip_path)


def make_hub_dataset_entries(
    tensors_tuple: tuple[
        torch.Tensor
        | np.ndarray
        | list[torch.Tensor | np.ndarray]
        | tuple[torch.Tensor | np.ndarray],
        ...,
    ],
    input_names: list[str],
    channel_last_input: Optional[list[str]] = None,
) -> DatasetEntries:
    """
    Given input tensor(s) in either numpy or torch format,
        convert to hub DatasetEntries format.

    Parameters:
        tensors: Tensor data in numpy or torch.Tensor format.
        input_names: List of input names.
        channel_last_input: Comma-separated list of input names to transpose channel.
    """
    dataset = {}
    assert len(tensors_tuple) == len(
        input_names
    ), "Number of elements in tensors_tuple must match number of inputs"
    for name, inputs in zip(input_names, tensors_tuple):
        input_seq = inputs if isinstance(inputs, (list, tuple)) else [inputs]

        converted_inputs = []
        for curr_input in input_seq:
            if isinstance(curr_input, torch.Tensor):
                curr_input = tensor_to_numpy(curr_input)
            assert isinstance(curr_input, np.ndarray)
            if curr_input.dtype == np.int64:
                curr_input = curr_input.astype(np.int32)
            if curr_input.dtype == np.float64:
                curr_input = curr_input.astype(np.float32)
            converted_inputs.append(curr_input)
        dataset[name] = converted_inputs

    # Transpose dataset I/O if necessary to fit with the on-device model format
    if channel_last_input:
        dataset = transpose_channel_first_to_last(channel_last_input, dataset)
    return dataset


def ensure_v73_or_later(target_runtime: TargetRuntime, device: Device) -> None | str:
    if not target_runtime.is_aot_compiled:
        return "AIMET model currently runs on precompiled targets"
    hex_attrs = [attr for attr in device.attributes if attr.startswith("hexagon:")]
    if len(hex_attrs) != 1:
        return f"Unable to determine hexagon version for {device.name}"
    hex_str = hex_attrs[0]
    # Extract hexagon version
    match = re.search(r"\d+", hex_str)
    hex_version = None
    if match:
        hex_version = int(match.group())
    else:
        return f"Unable to determine hexagon version for {device.name}"
    if hex_version < 73:
        return (
            "AIMET-ONNX requires hexagon v73 or above for Stable "
            "Diffusion VaeDecoder. "
        )
    return None
