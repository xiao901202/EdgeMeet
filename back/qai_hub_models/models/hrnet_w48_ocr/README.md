[![Qualcomm® AI Hub Models](https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/quic-logo.jpg)](../../README.md)


# [HRNet-W48-OCR: Semantic segmentation in higher resolution](https://aihub.qualcomm.com/models/hrnet_w48_ocr)

HRNet-W48-OCR is a machine learning model that can segment images from the Cityscape dataset. It has lightweight and hardware-efficient operations and thus delivers significant speedup on diverse hardware platforms

This is based on the implementation of HRNet-W48-OCR found [here](https://github.com/HRNet/HRNet-Semantic-Segmentation). This repository contains scripts for optimized on-device
export suitable to run on Qualcomm® devices. More details on model performance
accross various devices, can be found [here](https://aihub.qualcomm.com/models/hrnet_w48_ocr).

[Sign up](https://myaccount.qualcomm.com/signup) to start using Qualcomm AI Hub and run these models on a hosted Qualcomm® device.




## Example & Usage

Install the package via pip:
```bash
pip install "qai-hub-models[hrnet-w48-ocr]"
```


Once installed, run the following simple CLI demo:

```bash
python -m qai_hub_models.models.hrnet_w48_ocr.demo { --quantize w8a16 }
```
More details on the CLI tool can be found with the `--help` option. See
[demo.py](demo.py) for sample usage of the model including pre/post processing
scripts. Please refer to our [general instructions on using
models](../../../#getting-started) for more usage instructions.

## Export for on-device deployment

This repository contains export scripts that produce a model optimized for
on-device deployment. This can be run as follows:

```bash
python -m qai_hub_models.models.hrnet_w48_ocr.export { --quantize w8a16 }
```
Additional options are documented with the `--help` option.


## License
* The license for the original implementation of HRNet-W48-OCR can be found
  [here](https://github.com/HRNet/HRNet-Semantic-Segmentation/blob/HRNet-OCR/LICENSE).
* The license for the compiled assets for on-device deployment can be found [here](https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/Qualcomm+AI+Hub+Proprietary+License.pdf)


## References
* [Segmentation Transformer: Object-Contextual Representations for Semantic Segmentation](https://arxiv.org/abs/1909.11065)
* [Source Model Implementation](https://github.com/HRNet/HRNet-Semantic-Segmentation)



## Community
* Join [our AI Hub Slack community](https://aihub.qualcomm.com/community/slack) to collaborate, post questions and learn more about on-device AI.
* For questions or feedback please [reach out to us](mailto:ai-hub-support@qti.qualcomm.com).
