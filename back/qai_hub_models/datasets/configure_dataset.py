# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
import argparse

from qai_hub_models.datasets.carvana import CarvanaDataset
from qai_hub_models.datasets.celebahq import CelebAHQDataset
from qai_hub_models.datasets.cityscapes import CityscapesDataset
from qai_hub_models.datasets.face_attrib_dataset import FaceAttribDataset
from qai_hub_models.datasets.face_det_lite import FaceDetLiteDataset
from qai_hub_models.datasets.foot_track_dataset import FootTrackDataset
from qai_hub_models.datasets.gear_guard_dataset import GearGuardDataset
from qai_hub_models.datasets.human_faces import HumanFacesDataset
from qai_hub_models.datasets.nyuv2 import NyUv2Dataset

SUPPORTED_DATASETS = [
    "nyuv2",
    "foot_track_dataset",
    "gear_guard_dataset",
    "face_attrib_dataset",
    "cityscapes",
    "human_faces",
    "carvana",
    "celebahq",
    "face_det_lite",
]


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Script to configure a dataset that needs to be downloaded "
        "externally. Instructions on how to use this script are typically printed "
        "when trying to quantize or evalute a model that requires one of these datasets."
    )
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        choices=SUPPORTED_DATASETS,
        help="Which dataset to configure.",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        type=str,
        required=True,
        help="The local filepaths needed to setup this dataset.",
    )
    return parser


def configure_dataset(dataset: str, files: list[str]) -> None:
    if dataset == "nyuv2":
        NyUv2Dataset(source_dataset_file=files[0])
    elif dataset == "foot_track_dataset":
        FootTrackDataset(input_data_zip=files[0])
    elif dataset == "gear_guard_dataset":
        GearGuardDataset(input_data_zip=files[0])
    elif dataset == "face_attrib_dataset":
        FaceAttribDataset(input_data_zip=files[0])
    elif dataset == "cityscapes":
        CityscapesDataset(input_images_zip=files[0], input_gt_zip=files[1])
    elif dataset == "human_faces":
        HumanFacesDataset(input_data_zip=files[0])
    elif dataset == "carvana":
        CarvanaDataset(input_images_zip=files[0], input_gt_zip=files[1])
    elif dataset == "celebahq":
        CelebAHQDataset(input_images_zip=files[0])
    elif dataset == "face_det_lite":
        FaceDetLiteDataset(input_data_zip=files[0])
    else:
        raise ValueError(f"Invalid dataset {dataset}")


def main():
    args = get_parser().parse_args()
    configure_dataset(args.dataset, args.files)


if __name__ == "__main__":
    main()
