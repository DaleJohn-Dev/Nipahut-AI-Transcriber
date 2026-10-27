---
license: apache-2.0
base_model: speechbrain/sepformer-whamr16k
base_model_relation: quantized
pipeline_tag: audio-to-audio
library_name: onnxruntime
language:
- en
tags:
- onnx
- onnxruntime
- sepformer
- speech-separation
- audio-source-separation
- noise-suppression
- audio-to-audio
- whamr
---

# SepFormer WHAMR 16kHz — ONNX

ONNX export of
[speechbrain/sepformer-whamr16k](https://huggingface.co/speechbrain/sepformer-whamr16k), a
SepFormer (Separation Transformer) model trained on the WHAMR dataset for speech separation
and enhancement at 16 kHz. It is not a newly trained model. This is an unofficial community
conversion; SpeechBrain is the original author.

## Source

| Field | Value |
|---|---|
| Upstream model | [speechbrain/sepformer-whamr16k](https://huggingface.co/speechbrain/sepformer-whamr16k) |
| Upstream source revision | `21a5b500c6f52fddc387c5d9e5fb13ffd6f039c5` |
| Export tool/script | `torch.onnx` export from SpeechBrain pretrained checkpoint |
| Quantization recipe | FP32 ONNX graphs (`sepformer.onnx`, bundled `osd.onnx`) |

## Files

| File | Size | Description |
|---|---|---|
| `sepformer.onnx` | ~101 MB | SepFormer separation / enhancement model |
| `osd.onnx` | ~6 MB | Overlapped-speech-detection model (bundled alongside the separator) |

## Intended Use

Speech separation / enhancement for local inference via ONNX Runtime. The model separates
speech from additive background noise and reverberation, producing cleaner audio for
downstream VAD, diarization, or ASR. The ONNX export removes the SpeechBrain framework
dependency for more portable deployment.

## Runtime Notes

- Designed for ONNX Runtime compatible runtimes.
- Expected input: 16 kHz mono audio.
- The model outputs 1 or 2 separated source streams depending on configuration.
- Validate on the target execution provider before production use.

## Precision and Packaging

Export tooling, precision, and quantization are recorded in the **Source** table above. This packaging mirror does not publish independent parity benchmarks; validate on your target execution provider before production use.

## Limitations

- Trained on English speech with WHAM! noise conditions; performance on other languages or very different noise types is not evaluated in this repo.
- Trained at 16 kHz; input audio at other sample rates must be resampled.
- Source separation is computationally expensive; expect latency on CPU.
- ONNX export fidelity relative to the SpeechBrain PyTorch model is not documented here.

## License

[Apache 2.0](https://choosealicense.com/licenses/apache-2.0/) — inherited from
`speechbrain/sepformer-whamr16k`. This packaging repo adds no new license terms.