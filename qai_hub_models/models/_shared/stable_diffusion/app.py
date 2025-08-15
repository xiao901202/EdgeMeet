# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

from typing import Any, Optional

import diffusers
import torch
from diffusers.models.embeddings import get_timestep_embedding
from transformers import CLIPTokenizer

from qai_hub_models.models.protocols import ExecutableModelProtocol
from qai_hub_models.utils.inference import OnDeviceModel

OUT_H, OUT_W = 512, 512


class StableDiffusionApp:
    """
    StableDiffusionApp represents the application code needed to string
    together the various neural networks that make up the Stable Diffusion
    algorithm. This code is written in Python and uses PyTorch and is meant to
    serve as a reference implementation for application in other languages and
    for other platforms.

    Please run the app via `demo.py`.

    References
    ----------
    * https://arxiv.org/abs/2112.10752
    * https://github.com/apple/ml-stable-diffusion
    """

    def __init__(
        self,
        text_encoder: ExecutableModelProtocol,
        vae_decoder: ExecutableModelProtocol,
        unet: ExecutableModelProtocol,
        tokenizer: CLIPTokenizer | Any,
        scheduler: diffusers.DPMSolverMultistepScheduler,
        channel_last_latent: bool,
        host_device: torch.device = torch.device("cpu"),
        time_embedding: Optional[diffusers.embeddings.TimeEmbedding] = None,  # type: ignore[name-defined]
    ):
        """
        Initializes StableDiffusionApp with required neural networks for end-to-end pipeline.

        Parameters
        ----------
        text_encoder:
            Encoder input text
        vae_decoder:
            Decoder to decode latent space into output image
        unet:
            Denoises image in latent space
        tokenizer:
            Tokenizer for input text.
            Output of Tokenizer is fed to text_encoder.
            One can experiments with different tokenizers available based on Clip-ViT.
        scheduler:
            Solver for diffusion steps.
            Updates latent space during each iteration.
        channel_last_latent:
            True if unet outputs latent of shape like (1, 64, 64, 4). False
            for (1, 4, 64, 64)
        time_embedding:
            Projects time-step into embedding used during denoising in latent space.
            Optional; if this is None, then the time embedding should be baked into the unet model.
        """

        self.text_encoder = text_encoder
        self.unet = unet
        self.vae_decoder = vae_decoder
        self.tokenizer = tokenizer
        self.scheduler = scheduler
        self.channel_last_latent = channel_last_latent
        self.host_device = host_device
        self.time_embedding = time_embedding.to(host_device) if time_embedding else None

    def _encode_text_prompt(self, prompt: str) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Takes a text prompt and returns a tensor with its text embedding.

        Parameters
        ----------
        prompt: The text prompt to encode.

        Returns
        -------
        cond_embedding

        uncond_embedding

        Note that uncond_embedding is the same for any prompt (since it's not
        conditioned on the prompt). So in deploymenet this should be
        cached instead of computed every time. We compute it here for better
        clarity.
        """
        with torch.no_grad():
            # Tokenize input prompt
            text_input = self.tokenizer(
                prompt,
                padding="max_length",
                max_length=self.tokenizer.model_max_length,
                return_tensors="pt",
            )

            # Tokenize empty prompt
            max_length = text_input.input_ids.shape[-1]
            uncond_input = self.tokenizer(
                [""],
                padding="max_length",
                max_length=max_length,
                return_tensors="pt",
            )

            # Embed using the text encoder neural network
            # Encode input and empty prompt in one go
            print(f"\nExtracting embeddings (inference on TextEncoder)\n{'-' * 50}")
            if isinstance(self.text_encoder, OnDeviceModel):
                # Batch data into one inference job
                embeddings = self.text_encoder(
                    [
                        text_input.input_ids.int(),
                        uncond_input.input_ids.int(),
                    ]
                )
                assert isinstance(embeddings, torch.Tensor)
                cond_embeddings, uncond_embeddings = torch.split(embeddings, 1, 0)
            else:
                cond_embeddings = self.text_encoder(
                    text_input.input_ids.type(torch.int32)
                )
                uncond_embeddings = self.text_encoder(
                    uncond_input.input_ids.type(torch.int32)
                )
            return cond_embeddings, uncond_embeddings

    def predict(self, *args, **kwargs):
        # See generate_image.
        return self.generate_image(*args, **kwargs)

    def generate_image(
        self,
        prompt: str,
        num_steps: int = 50,
        seed: int = 0,
        guidance_scale: float = 7.5,
    ) -> torch.Tensor:
        """
        Generate an image using the PyTorch reference neural networks. This
        code can be used as a reference for how to glue together the neural
        networks in an application. Note that this code relies on a tokenizer
        and scheduler from the HuggingFace's diffusers library, so those would
        have to be ported to the application as well.

        Parameters
        ----------
        prompt:
            The text prompt to generate an image from.
        num_steps:
            The number of steps to run the diffusion process for. Higher value
            may lead to better image quality.
        seed:
            The seed to use for the random number generator.
        guidance_scale:
            Classifier-free guidance is a method that allows us to control how
            strongly the image generation is guided by the prompt. This is done
            by always processing two samples at once: an unconditional (using a
            text embedding of an empty prompt) and a conditional (using a text
            embedding of the provided prompt). Given the noise prediction of
            both of these, we linearly interpolate between them based on the
            guidance_scale. A guidance scale of 0 is the same as using an empty
            prompt. A guidance scale of 1 turns off classifier-free guidance
            and is computationally less expensive since it only processes one
            sample at a time. Intuitively you may think the rest of guidance
            scales are between 0 and 1, but it is common to use a scale greater
            than 1 as a method of amplifying the prompt's influence on the
            image, pushing it further away from the unconditional sample.

        Returns
        -------
        torch.Tensor
            The generated image in RGB scaled in [0, 1] with tensor shape
            (OUT_H, OUT_W, 3). The height and the width may depend on the
            underlying Stable Diffusion version, but is typically 512x512.
        """

        # Encode text prompt
        cond_embeddings, uncond_embeddings = self._encode_text_prompt(prompt)

        latents = run_diffusion_steps_on_latents(
            unet=self.unet,
            scheduler=self.scheduler,
            cond_embeddings=cond_embeddings,
            uncond_embeddings=uncond_embeddings,
            num_steps=num_steps,
            seed=seed,
            guidance_scale=guidance_scale,
            channel_last_latent=self.channel_last_latent,
            host_device=self.host_device,
            time_embedding=self.time_embedding,
        )
        # Decode generated image from latent space
        if self.channel_last_latent:
            latents = _make_channel_last_torch(latents).to(self.host_device)
        image = self.vae_decoder(latents)
        return image.to("cpu")  # move to cpu in case it was run on gpu


def get_time_embedding(
    time_embedding: diffusers.embeddings.TimeEmbedding, timestep: int  # type: ignore[name-defined]
) -> torch.Tensor:
    """
    Since these time embeddings aren't dependent on prompt, they can be
    pre-computed (for a pre-defined set of timesteps) in deployment and
    skip these computation. We include them in demo for better clarity.
    """
    timestep_tensor = torch.tensor([timestep])
    # TODO: pull 320 from UNet block output dim
    t_emb = get_timestep_embedding(timestep_tensor, 320, True, 0)
    emb = time_embedding(t_emb)

    return emb


def run_diffusion_steps_on_latents(
    unet: ExecutableModelProtocol,
    scheduler: diffusers.DPMSolverMultistepScheduler,
    cond_embeddings: torch.Tensor,
    uncond_embeddings: torch.Tensor | None = None,
    num_steps: int = 20,
    seed: int = 0,
    guidance_scale: float = 7.5,
    channel_last_latent: bool = False,
    return_all_steps: bool = False,
    host_device: torch.device = torch.device("cpu"),
    time_embedding: Optional[diffusers.embeddings.TimeEmbedding] = None,  # type: ignore[name-defined]
) -> torch.Tensor | tuple[torch.Tensor, dict[str, list[torch.Tensor]]]:
    """
    Runs the diffusion steps on latents to generate the final latent sample.

    When guidance_scale is nonzero, classifier-free guidance is applied by computing
    both conditional and unconditional noise predictions. In that case, `uncond_embeddings`
    must be provided. If guidance_scale is 0, no guidance is applied and only the conditional
    branch is used.

    Parameters
    ----------
    unet:
        The denoising network.
    scheduler:
        The scheduler controlling the diffusion process.
    cond_embeddings:
        Conditional text embeddings.
    uncond_embeddings:
        Unconditional text embeddings. This is required if guidance_scale != 0.
    num_steps:
        Number of diffusion steps.
    seed:
        Seed for random number generation.
    guidance_scale:
        Scale for classifier-free guidance. If nonzero, both conditional and unconditional
        noise predictions are computed.
    channel_last_latent:
        True if the unet outputs latents in channel-last format.
    return_all_steps:
        If True, returns intermediate latents and time embeddings for calibration.
    time_embedding:
        Projects time-step into embedding used during denoising in latent space.
        Optional; if this is None, then the time embedding should be baked into the unet model.

    Returns
    -------
    torch.Tensor
        Final latent sample.
    dict[str, list[torch.Tensor]]
        Intermediate inputs (only if return_all_steps is True).
    """
    with torch.no_grad():
        scheduler.set_timesteps(num_steps)  # type: ignore[attr-defined]

        # Initialize latent tensor
        latents_shape = (1, 4, OUT_H // 8, OUT_W // 8)
        generator = torch.manual_seed(seed)
        latents = torch.randn(latents_shape, generator=generator, device=host_device)
        latents = latents * scheduler.init_noise_sigma  # type: ignore[attr-defined]

        # Time input
        time_input_name = "time_embed" if time_embedding else "timestep"

        # For calibration purposes, store intermediate inputs if needed
        unet_inputs: dict[str, list[torch.Tensor]] = {"latent": [], time_input_name: []}

        for i, t in enumerate(scheduler.timesteps):  # type: ignore[attr-defined]
            print(f"\nStep: {i + 1}\n{'-' * 10}")

            if time_embedding:
                time_input = get_time_embedding(time_embedding, t).to(host_device)
            else:
                time_input = torch.as_tensor([[t]], dtype=torch.float32).to(host_device)

            latent_model_input = scheduler.scale_model_input(latents, t)  # type: ignore[attr-defined]
            if channel_last_latent:
                latent_model_input = _make_channel_last_torch(latent_model_input).to(
                    host_device
                )
            unet_inputs["latent"].append(latent_model_input)
            unet_inputs[time_input_name].append(time_input)

            # Check if guidance should be applied.
            if guidance_scale != 0:
                if uncond_embeddings is None:
                    raise ValueError(
                        "uncond_embeddings must be provided when guidance_scale is nonzero"
                    )
                # Use both conditional and unconditional embeddings.
                if isinstance(unet, OnDeviceModel):
                    # Batch data into one inference job.
                    noise = unet(
                        [latent_model_input, latent_model_input],
                        [time_input, time_input],
                        [cond_embeddings, uncond_embeddings],
                    )
                    noise_cond, noise_uncond = torch.split(noise, 1, 0)
                else:
                    noise_cond = unet(latent_model_input, time_input, cond_embeddings)
                    noise_uncond = unet(
                        latent_model_input, time_input, uncond_embeddings
                    )
                noise_pred = noise_uncond + guidance_scale * (noise_cond - noise_uncond)
            else:
                # No guidance: only process conditional embeddings.
                if isinstance(unet, OnDeviceModel):
                    noise_pred = unet(
                        [latent_model_input], [time_input], [cond_embeddings]
                    )
                else:
                    noise_pred = unet(latent_model_input, time_input, cond_embeddings)

            if channel_last_latent:
                noise_pred = _make_channel_first_torch(noise_pred).to(host_device)
            latents = scheduler.step(noise_pred, t, latents).prev_sample  # type: ignore[attr-defined]

        if return_all_steps:
            return latents, unet_inputs
        return latents


# Helper method to go back and forth from channel-first to channel-last
def _make_channel_last_torch(input_tensor):
    return torch.permute(input_tensor, [0, 2, 3, 1])


def _make_channel_first_torch(input_tensor):
    return torch.permute(torch.Tensor(input_tensor), [0, 3, 1, 2])
