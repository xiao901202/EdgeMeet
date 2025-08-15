# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from inspect import signature
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest
import qai_hub as hub

from qai_hub_models.models.common import TargetRuntime
from qai_hub_models.models.llama_v2_7b_chat import Model
from qai_hub_models.models.llama_v2_7b_chat.demo import llama_2_chat_demo
from qai_hub_models.models.llama_v2_7b_chat.export import (
    BASE_NAME,
    DEFAULT_EXPORT_DEVICE,
)
from qai_hub_models.models.llama_v2_7b_chat.export import main as export_main
from qai_hub_models.utils.model_cache import CacheMode
from qai_hub_models.utils.testing import patch_qai_hub


@pytest.mark.skip("#105 move slow_cloud and slow tests to nightly.")
@pytest.mark.slow_cloud
def test_demo() -> None:
    # Run demo and verify it does not crash
    llama_2_chat_demo(is_test=True)


def _mock_from_pretrained() -> Mock:
    model = MagicMock()
    # We'll use a single compnent to mock all
    component = MagicMock()
    component.get_input_spec.return_value = {"attention_mask": [[1, 1024]]}
    component.get_output_names.return_value = ["output0", "output1"]
    component.sample_inputs.return_value = {"input0": [np.array([1.0, 2.0])]}

    model.load_model_part.return_value = component
    model.__signature__ = signature(Model.from_pretrained)
    mock_from_pretrained = Mock()
    mock_from_pretrained.__signature__ = signature(Model.from_pretrained)
    mock_from_pretrained.return_value = model
    return mock_from_pretrained


def test_cli_device_with_skips(tmp_path) -> None:
    patch_get_cache = patch(
        "qai_hub_models.utils.model_cache.get_or_create_cached_model",
        return_value=Mock(),
    )
    mock_from_pretrained = _mock_from_pretrained()
    patch_model = patch(
        "qai_hub_models.models.llama_v2_7b_chat.Model.from_pretrained",
        mock_from_pretrained,
    )

    device = hub.Device("Snapdragon X Elite CRD")
    with patch_qai_hub() as mock_hub, patch_model, patch_get_cache:
        export_main(
            [
                "--device",
                device.name,
                "--skip-inferencing",
                "--skip-profiling",
                "--output-dir",
                tmp_path.name,
            ]
        )

        # Compile is called 8 times (4 token parts, 4 prompt parts)
        assert mock_hub.submit_compile_job.call_count == 8
        call_args_list = mock_hub.submit_compile_job.call_args_list
        assert all(c.kwargs["device"].name == device.name for c in call_args_list)

        # Link 4 times
        assert mock_hub.submit_link_job.call_count == 4
        call_args_list = mock_hub.submit_link_job.call_args_list
        assert all(
            c.kwargs["name"] == f"{BASE_NAME}_Llama2_Part{i + 1}_Quantized"
            for i, c in enumerate(call_args_list)
        )

        # Skip profile and inference
        mock_hub.submit_profile_job.assert_not_called()
        mock_hub.submit_inference_job.assert_not_called()
        assert tmp_path.exists()
        assert tmp_path.is_dir()


def test_cli_chipset_with_options(tmp_path) -> None:
    patch_get_cache = patch(
        "qai_hub_models.utils.model_cache.get_or_create_cached_model",
        return_value=Mock(),
    )
    mock_from_pretrained = _mock_from_pretrained()
    mock_model = mock_from_pretrained.return_value
    patch_model = patch(
        "qai_hub_models.models.llama_v2_7b_chat.Model.from_pretrained",
        return_value=mock_model,
    )

    chipset = "qualcomm-snapdragon-x-elite"
    device = hub.get_devices(attributes=f"chipset:{chipset}")[0]
    with patch_qai_hub() as mock_hub, patch_model, patch_get_cache:
        export_main(
            [
                "--chipset",
                chipset,
                "--output-dir",
                tmp_path.name,
                "--target-runtime",
                "qnn_context_binary",
                "--compile-options",
                "compile_extra",
                "--profile-options",
                "profile_extra",
            ]
        )

        # Compile is called 8 times (4 token parts, 4 prompt parts)
        assert mock_hub.submit_compile_job.call_count == 8
        assert all(
            c.kwargs["device"] == device
            for c in mock_hub.submit_compile_job.call_args_list
        )

        # Link 4 times
        assert mock_hub.submit_link_job.call_count == 4
        assert all(
            c.kwargs["name"] == f"{BASE_NAME}_Llama2_Part{i + 1}_Quantized"
            for i, c in enumerate(mock_hub.submit_link_job.call_args_list)
        )
        mock_comp = mock_model.load_model_part.return_value

        assert all(
            c.args[0] == TargetRuntime.QNN_CONTEXT_BINARY
            for c in mock_comp.get_hub_compile_options.call_args_list
        )
        assert all(
            c.args[2] == "compile_extra"
            for c in mock_comp.get_hub_compile_options.call_args_list
        )

        # Profile 8 times
        assert mock_hub.submit_profile_job.call_count == 8
        call_args_list = mock_hub.submit_profile_job.call_args_list
        assert all(c.kwargs["device"] == device for c in call_args_list)
        assert all(
            c.args[1] == "profile_extra"
            for c in mock_comp.get_hub_profile_options.call_args_list
        )

        # Inference 8 times
        assert mock_hub.submit_inference_job.call_count == 8
        call_args_list = mock_hub.submit_inference_job.call_args_list
        assert all(c.kwargs["device"] == device for c in call_args_list)

        assert tmp_path.exists()
        assert tmp_path.is_dir()


def test_cli_default_device_select_component(tmp_path) -> None:
    mock_get_cache = Mock()
    patch_get_cache = patch(
        "qai_hub_models.utils.model_cache.get_or_create_cached_model", mock_get_cache
    )
    mock_from_pretrained = _mock_from_pretrained()
    patch_model = patch(
        "qai_hub_models.models.llama_v2_7b_chat.Model.from_pretrained",
        mock_from_pretrained,
    )

    device = hub.Device(DEFAULT_EXPORT_DEVICE)
    with patch_qai_hub() as mock_hub, patch_model, patch_get_cache:
        export_main(
            [
                "--output-dir",
                tmp_path.name,
                "--max-position-embeddings",
                "128",
                "--model-cache-mode",
                "overwrite",
                "--components",
                "Llama2_Part2_Quantized",
                "Llama2_Part4_Quantized",
            ]
        )

        mock_from_pretrained.assert_called_with(max_position_embeddings=128)

        assert mock_hub.submit_compile_job.call_count == 4
        assert mock_hub.submit_link_job.call_count == 2
        assert mock_hub.submit_profile_job.call_count == 4
        assert mock_hub.submit_inference_job.call_count == 4

        # Check names
        for mock in [
            mock_hub.submit_compile_job,
            mock_hub.submit_profile_job,
            mock_hub.submit_inference_job,
        ]:
            cc = mock.call_args_list
            assert cc[0].kwargs["name"] == f"{BASE_NAME}_PromptProcessor_2"
            assert cc[1].kwargs["name"] == f"{BASE_NAME}_TokenGenerator_2"
            assert cc[2].kwargs["name"] == f"{BASE_NAME}_PromptProcessor_4"
            assert cc[3].kwargs["name"] == f"{BASE_NAME}_TokenGenerator_4"

        cc = mock_hub.submit_link_job.call_args_list
        assert cc[0].kwargs["name"] == f"{BASE_NAME}_Llama2_Part2_Quantized"
        assert cc[1].kwargs["name"] == f"{BASE_NAME}_Llama2_Part4_Quantized"

        # Check cache
        for i, c in enumerate(mock_get_cache.call_args_list):
            assert c.kwargs["model_name"] == BASE_NAME
            assert c.kwargs["cache_mode"] == CacheMode.OVERWRITE
            # Mock assumes seq len is always 1 (not correct for prompts)
            assert c.kwargs["additional_keys"] == {
                "context_length": "1024",
                "sequence_length": "1",
            }

        call_args_list = mock_hub.submit_compile_job.call_args_list
        assert all(c.kwargs["device"].name == device.name for c in call_args_list)

        assert tmp_path.exists()
        assert tmp_path.is_dir()
