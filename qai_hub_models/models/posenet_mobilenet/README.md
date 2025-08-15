[![Qualcomm® AI Hub Models](https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/quic-logo.jpg)](../../README.md)


# [Posenet-Mobilenet: Perform accurate human pose estimation](https://aihub.qualcomm.com/models/posenet_mobilenet)

Posenet performs pose estimation on human images.

This is based on the implementation of Posenet-Mobilenet found [here](https://github.com/rwightman/posenet-pytorch). This repository contains scripts for optimized on-device
export suitable to run on Qualcomm® devices. More details on model performance
accross various devices, can be found [here](https://aihub.qualcomm.com/models/posenet_mobilenet).

[Sign up](https://myaccount.qualcomm.com/signup) to start using Qualcomm AI Hub and run these models on a hosted Qualcomm® device.




## Example & Usage

Install the package via pip:
```bash
pip install "qai-hub-models[posenet-mobilenet]"
```


Once installed, run the following simple CLI demo:

```bash
python -m qai_hub_models.models.posenet_mobilenet.demo { --quantize w8a8 }
```
More details on the CLI tool can be found with the `--help` option. See
[demo.py](demo.py) for sample usage of the model including pre/post processing
scripts. Please refer to our [general instructions on using
models](../../../#getting-started) for more usage instructions.

## Export for on-device deployment

This repository contains export scripts that produce a model optimized for
on-device deployment. This can be run as follows:

```bash
python -m qai_hub_models.models.posenet_mobilenet.export { --quantize w8a8 }
```
Additional options are documented with the `--help` option.


## License
* The license for the original implementation of Posenet-Mobilenet can be found
  [here](https://github.com/rwightman/posenet-pytorch/blob/master/LICENSE.txt).
* The license for the compiled assets for on-device deployment can be found [here](https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/Qualcomm+AI+Hub+Proprietary+License.pdf)


## References
* [PersonLab: Person Pose Estimation and Instance Segmentation with a Bottom-Up, Part-Based, Geometric Embedding Model](https://arxiv.org/abs/1803.08225)
* [Source Model Implementation](https://github.com/rwightman/posenet-pytorch)



## Community
* Join [our AI Hub Slack community](https://aihub.qualcomm.com/community/slack) to collaborate, post questions and learn more about on-device AI.
* For questions or feedback please [reach out to us](mailto:ai-hub-support@qti.qualcomm.com).
