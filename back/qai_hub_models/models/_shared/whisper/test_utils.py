# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

import numpy as np
import torch
import whisper

from qai_hub_models.models._shared.whisper.app import WhisperApp, log_mel_spectrogram
from qai_hub_models.models._shared.whisper.demo import load_demo_audio
from qai_hub_models.models._shared.whisper.model import MEAN_DECODE_LEN, Whisper


def load_sample_audio_input(app: WhisperApp) -> tuple[np.ndarray, np.ndarray, int]:
    audio, sample_rate = load_demo_audio()
    assert app.mel_filter is not None
    return (
        audio,
        log_mel_spectrogram(
            app.mel_filter, audio, app.max_audio_samples, app.n_fft, app.hop_length
        ),
        sample_rate,
    )


def run_test_wrapper_numerics(model_cls: type[Whisper], whisper_version):
    """
    Test that wrapper classes, excluding the
    app, predict logits (without post
    processing) that matches with the
    original model's.
    """
    model = model_cls.from_source_model(whisper.load_model(whisper_version))
    app = WhisperApp(
        model.encoder,
        model.decoder,
        num_decoder_blocks=model.num_decoder_blocks,
        num_decoder_heads=model.num_decoder_heads,
        attention_dim=model.attention_dim,
        mean_decode_len=model.mean_decode_len,
    )

    # Load inputs
    _, mel_input, _ = load_sample_audio_input(app)

    # OpenAI
    with torch.no_grad():
        model = whisper.load_model(whisper_version)
        mel_input = torch.from_numpy(mel_input)
        audio_features = model.encoder(mel_input)

        tokens = torch.LongTensor([[50257]])
        logits_orig = model.decoder(tokens, audio_features).detach().numpy()

    # QAIHM
    encoder = app.encoder.base_model
    decoder = app.decoder.base_model
    k_cache_cross, v_cache_cross = encoder(mel_input)
    sample_len = MEAN_DECODE_LEN

    k_cache_self = torch.zeros(
        (
            decoder.num_blocks,
            decoder.num_heads,
            decoder.attention_dim // decoder.num_heads,
            sample_len,
        ),
        dtype=torch.float32,
    )
    v_cache_self = torch.zeros(
        (
            decoder.num_blocks,
            decoder.num_heads,
            sample_len,
            decoder.attention_dim // decoder.num_heads,
        ),
        dtype=torch.float32,
    )
    index = torch.zeros([1, 1], dtype=torch.int32)
    index[0, 0] = 0
    with torch.no_grad():
        decoder_out = decoder(
            tokens, index, k_cache_cross, v_cache_cross, k_cache_self, v_cache_self
        )
        logits = decoder_out[0].detach().numpy()

    np.testing.assert_allclose(logits_orig, logits, rtol=5e-3)


def run_test_transcribe(model_cls: type[Whisper], whisper_version):
    """
    Test that WhisperApp produces end to end transcription results that
    matches with the original model
    """
    model = model_cls.from_source_model(whisper.load_model(whisper_version))
    app = WhisperApp(
        model.encoder,
        model.decoder,
        num_decoder_blocks=model.num_decoder_blocks,
        num_decoder_heads=model.num_decoder_heads,
        attention_dim=model.attention_dim,
        mean_decode_len=model.mean_decode_len,
    )
    audio, mel_input, sample_rate = load_sample_audio_input(app)

    # Run inference with OpenAI whisper
    with torch.no_grad():
        model = whisper.load_model(whisper_version)
        options = whisper.DecodingOptions(
            language="en", without_timestamps=False, fp16=False
        )
        results = model.decode(torch.from_numpy(mel_input).float(), options)
        assert isinstance(results, list)
        text_orig = results[0].text

    # Perform transcription
    transcription = app.transcribe(audio, sample_rate)
    assert transcription == text_orig
