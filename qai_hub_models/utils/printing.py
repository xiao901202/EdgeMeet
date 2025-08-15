# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterable
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import Any, Optional, TypeVar, Union

import numpy as np
import qai_hub as hub
from prettytable import PrettyTable
from qai_hub.public_rest_api import DatasetEntries
from tabulate import tabulate

from qai_hub_models.configs.devices_and_chipsets_yaml import (
    DeviceDetailsYaml,
    DevicesAndChipsetsYaml,
    ScorecardDevice,
)
from qai_hub_models.configs.perf_yaml import QAIHMModelPerf
from qai_hub_models.utils.base_model import TargetRuntime
from qai_hub_models.utils.compare import METRICS_FUNCTIONS, generate_comparison_metrics

_INFO_DASH = "-" * 60


def print_with_box(data: list[str]) -> None:
    """
    Print input list with box around it as follows
    +-----------------------------+
    | list data 1                 |
    | list data 2 that is longest |
    | data                        |
    +-----------------------------+
    """
    size = max(len(line) for line in data)
    size += 2
    print("+" + "-" * size + "+")
    for line in data:
        print("| {:<{}} |".format(line, size - 2))
    print("+" + "-" * size + "+")


def print_inference_metrics(
    inference_job: Optional[hub.InferenceJob],
    inference_result: DatasetEntries,
    torch_out: list[np.ndarray],
    output_names: Optional[list[str]] = None,
    outputs_to_skip: Optional[list[int]] = None,
    metrics: str = "psnr",
) -> None:
    if output_names is None:
        output_names = list(inference_result.keys())
    inference_data = [
        np.concatenate(inference_result[out_name], axis=0) for out_name in output_names
    ]
    df_eval = generate_comparison_metrics(
        torch_out, inference_data, names=output_names, metrics=metrics
    )
    for output_idx in outputs_to_skip or []:
        if output_idx < len(output_names):
            df_eval = df_eval.drop(output_names[output_idx])

    def custom_float_format(x):
        if isinstance(x, float):
            return f"{x:.4g}"
        return x

    formatted_df = df_eval.applymap(
        custom_float_format
    )  # pyright: ignore[reportCallIssue]

    print(
        "\nComparing on-device vs. local-cpu inference"
        + (f" for {inference_job.name.title()}." if inference_job is not None else "")
    )
    print(tabulate(formatted_df, headers="keys", tablefmt="grid"))
    print()

    # Print explainers for each eval metric
    for m in df_eval.columns.drop("shape"):
        print(f"- {m}:", METRICS_FUNCTIONS[m][1])

    if inference_job is not None:
        last_line = f"More details: {inference_job.url}"
        print()
        print(last_line)


def print_profile_metrics_from_job(
    profile_job: hub.ProfileJob,
    profile_data: dict[str, Any],
):
    compute_unit_counts = Counter(
        [
            op.get("compute_unit", "UNK").lower()
            for op in profile_data["execution_detail"]
        ]
    )
    execution_summary = profile_data["execution_summary"]
    low_mem_bytes, high_mem_bytes = execution_summary["inference_memory_peak_range"]
    print(f"\n{_INFO_DASH}")
    print(f"Performance results on-device for {profile_job.name.title()}.")
    print(_INFO_DASH)

    runtime = TargetRuntime.from_hub_model_type(profile_job.model.model_type)
    perf_details = QAIHMModelPerf.PerformanceDetails(
        job_id=profile_job.job_id,
        inference_time_milliseconds=execution_summary["estimated_inference_time"]
        / 1000,
        estimated_peak_memory_range_mb=QAIHMModelPerf.PerformanceDetails.PeakMemoryRangeMB.from_bytes(
            low_mem_bytes, high_mem_bytes
        ),
        layer_counts=QAIHMModelPerf.PerformanceDetails.LayerCounts.from_layers(
            npu=compute_unit_counts.get("npu", 0),
            gpu=compute_unit_counts.get("gpu", 0),
            cpu=compute_unit_counts.get("cpu", 0),
        ),
    )

    print_profile_metrics(profile_job.device.name, runtime, perf_details)
    print(_INFO_DASH)
    last_line = f"More details: {profile_job.url}\n"
    print(last_line)


def get_profile_metrics(
    device_name: str,
    runtime: TargetRuntime,
    perf_details: QAIHMModelPerf.PerformanceDetails,
    can_access_qualcomm_ai_hub: bool = True,
) -> str:
    if not can_access_qualcomm_ai_hub:
        device_name = device_name.removesuffix(" (Family)")
        device_info = DevicesAndChipsetsYaml.load().devices[device_name]
    else:
        device_info = DeviceDetailsYaml.from_device(
            ScorecardDevice.get(device_name, return_unregistered=True)
        )

    rows = [
        ["Device", f"{device_name} ({device_info.os})"],
        ["Runtime", runtime.name],
    ]

    if perf_details.tokens_per_second:
        assert perf_details.time_to_first_token_range_milliseconds
        rows.extend(
            [
                [
                    "Response Rate (Tokens/Second)",
                    str(perf_details.tokens_per_second),
                ],
                [
                    "Time to First Token (Seconds)",
                    f"min={perf_details.time_to_first_token_range_milliseconds.min / 1000}, max={perf_details.time_to_first_token_range_milliseconds.max / 100}",
                ],
            ]
        )
    else:
        assert perf_details.inference_time_milliseconds
        assert perf_details.estimated_peak_memory_range_mb
        assert perf_details.layer_counts
        inf_time_ms = perf_details.inference_time_milliseconds
        mem_min = perf_details.estimated_peak_memory_range_mb.min
        mem_max = perf_details.estimated_peak_memory_range_mb.max
        compute_units = [
            f"{unit} ({num_ops} ops)"
            for unit, num_ops in [
                ("npu", perf_details.layer_counts.npu),
                ("gpu", perf_details.layer_counts.gpu),
                ("cpu", perf_details.layer_counts.cpu),
            ]
        ]

        rows.extend(
            [
                [
                    "Estimated inference time (ms)",
                    "<0.1" if inf_time_ms < 0.1 else f"{inf_time_ms:.1f}",
                ],
                ["Estimated peak memory usage (MB)", f"[{mem_min}, {mem_max}]"],
                ["Total # Ops", str(perf_details.layer_counts.total)],
                ["Compute Unit(s)", " ".join(compute_units)],
            ]
        )

    table = PrettyTable(align="l", header=False, border=False, padding_width=0)
    for row in rows:
        table.add_row([row[0], f": {row[1]}"])
    return table.get_string()


def print_profile_metrics(
    device_name: str,
    runtime: TargetRuntime,
    perf_details: QAIHMModelPerf.PerformanceDetails,
    can_access_qualcomm_ai_hub: bool = True,
):
    print(
        get_profile_metrics(
            device_name, runtime, perf_details, can_access_qualcomm_ai_hub
        )
    )


DemoJobT = TypeVar("DemoJobT", hub.CompileJob, hub.LinkJob)


def print_on_target_demo_cmd(
    compile_job: Union[DemoJobT, Iterable[DemoJobT]],
    model_folder: Path,
    device: hub.Device,
) -> None:
    """
    Outputs a command that will run a model's demo script via inference job.
    """
    model_folder = model_folder.resolve()
    if not isinstance(compile_job, Iterable):
        compile_job = [compile_job]

    target_model_id = []
    for job in compile_job:
        assert job.wait().success
        target_model = job.get_target_model()
        assert target_model is not None
        target_model_id.append(target_model.model_id)

    target_model_id_str = ",".join(target_model_id)
    print(
        f"\nRun compiled model{'s' if len(target_model_id) > 1 else ''} on a hosted device on sample data using:"
    )
    print(
        f"python {model_folder / 'demo.py'} "
        "--eval-mode on-device "
        f"--hub-model-id {target_model_id_str} ",
        end="",
    )
    if device.attributes:
        print(f"--chipset {device.attributes[len('chipset:'):]}\n")
    else:
        print(f'--device "{device.name}"\n')


def print_mmcv_import_failure_and_exit(e: ImportError, model_id: str, mm_variant: str):
    print(
        f"""
------

ImportError: {str(e)}

{mm_variant} failed to import. You probably have the wrong variant of MMCV installed.
This can happen if you `pip install qai-hub-models[{model_id}]` without providing an index for pip to use to find MMCV.

To fix this, install the variant of MMCV compatible with your torch version:
    1. pip uninstall mmcv # You need to manually uninstall first. This is important.
    2. Follow instructions at https://mmcv.readthedocs.io/en/latest/get_started/installation.html#install-with-pip

------
"""
    )
    exit(1)


def print_file_tree_changes(
    base_dir: str,
    files_unmodified: list[str],
    files_added: list[str] = [],
    files_removed: list[str] = [],
) -> list[str]:
    """
    Given a set of absolute paths, prints the file tree with modifications highlighted.

    Parameters:
        base_dir: str
            The "top level" directory in which all files live.

        files_unmodified: list[str]
            ABSOLUTE paths to files in base_dir that are not modified.

        files_added: list[str]
            ABSOLUTE paths to files in base_dir that will be added.

        files_unmodified: list[str]
            ABSOLUTE paths to files in base_dir that will be removed.

    Returns:
        list[str]
            Output lines (return value mainly used for unit testing)

    Raises:
        AssertionError
            If any file path is not contained within base_dir.
    """
    changed = len(files_added) > 0 or len(files_removed) > 0
    outlines = [f"--- File Tree {'Changes' if changed else ' (Unchanged)'} ---"]

    # Get all files
    all_files_set = set(files_unmodified)
    all_files_set.update(files_removed)
    all_files_set.update(files_added)
    all_files = sorted(all_files_set)

    # Collect starting level
    if base_dir.endswith("/"):
        base_dir = base_dir[:-1]
    base_level = base_dir.count(os.sep)
    last_level = base_level
    last_folder = None
    outlines.append(base_dir)

    for file in all_files:
        assert file.startswith(base_dir)

        level = file.count(os.sep)
        indent = file.count(os.sep) - base_level - 1
        folder = os.path.dirname(file)

        # If the level increases, or the folder name changes at the same level,
        # this is a new folder. Print the folder name.
        if (
            level > last_level or (level == last_level and last_folder != folder)
        ) and folder != base_dir:
            outlines.append("")
            outlines.append(f"{' ' * 4 * (indent)}{os.path.basename(folder)}/")
        elif level == last_level - 1:
            # pop back to previous folder, presumably to list more regular files
            outlines.append("")

        last_folder = folder
        last_level = level

        # Print file
        addl_info = ""
        added = file in files_added
        removed = file in files_removed
        if added and removed:
            addl_info = "-+ "
        elif added:
            addl_info = "+ "
        elif removed:
            addl_info = "- "
        outlines.append(f"{' ' * 4 * (indent + 1)}{addl_info}{os.path.basename(file)}")

    for line in outlines:
        print(line)

    return outlines


@contextmanager
def suppress_stdout():
    """A context manager that redirects stdout to devnull"""
    with open(os.devnull, "w") as fnull:
        with redirect_stdout(fnull) as out:
            yield out
