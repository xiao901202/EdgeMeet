# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from pathlib import Path


def get_default_aimet_config() -> str:
    path = Path(__file__).parent / "default_config.json"
    return str(path.resolve())


def get_default_per_tensor_aimet_config() -> str:
    path = Path(__file__).parent / "default_per_tensor_config.json"
    return str(path.resolve())


def get_default_per_tensor_v73_aimet_config() -> str:
    path = Path(__file__).parent / "default_per_tensor_config_v73.json"
    return str(path.resolve())


def get_default_per_tensor_v69_aimet_config() -> str:
    path = Path(__file__).parent / "default_per_tensor_config_v69.json"
    return str(path.resolve())


def get_aimet_config_path(name: str) -> str:
    path = Path(__file__).parent / f"{name}.json"
    return str(path.resolve())
