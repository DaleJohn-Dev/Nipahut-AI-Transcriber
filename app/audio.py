"""Audio cleanup preserves the sample count and original timebase."""
import io
import numpy as np
import soundfile as sf
from scipy import signal
from PIL import Image

RATE = 16000

def decode_file(source, destination, check=lambda: None, progress=lambda p: None):
    """Stream compressed audio to PCM instead of allocating an entire decoded upload."""
    import av
    from .storage import require_space
    temporary = destination.with_suffix('.wav.part')
    count = 0
    try:
        with av.open(str(source)) as container:
            if not container.streams.audio:
                raise ValueError('This file has no audio stream.')
            duration = container.duration / av.time_base if container.duration else None
            if duration and duration > 7200:
                raise ValueError('This version supports recordings up to two hours.')
            require_space(int((duration or 600) * RATE * 2))
            resampler = av.AudioResampler(format='s16', layout='mono', rate=RATE)
            with sf.SoundFile(str(temporary), mode='w', samplerate=RATE, channels=1, format='WAV', subtype='PCM_16') as output:
                for frame in container.decode(audio=0):
                    check()
                    for converted in resampler.resample(frame):
                        block = converted.to_ndarray().reshape(-1)
                        count += len(block)
                        if count > RATE * 7200:
                            raise ValueError('This version supports recordings up to two hours.')
                        output.write(block)
                    if duration:
                        progress(min(.99, count / RATE / duration))
                for converted in resampler.resample(None):
                    block = converted.to_ndarray().reshape(-1)
                    count += len(block)
                    output.write(block)
        if count == 0:
            raise ValueError('No audio samples could be decoded.')
        check()
        temporary.replace(destination)
        return count / RATE
    finally:
        temporary.unlink(missing_ok=True)

def read_audio(path):
    audio, rate = sf.read(str(path), dtype='float32')
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if rate != RATE:
        from math import gcd
        g = gcd(rate, RATE)
        audio = signal.resample_poly(audio, RATE // g, rate // g)
    return np.ascontiguousarray(audio, dtype=np.float32)

def clean_audio(audio, opts, progress=lambda x: None, check=lambda: None):
    out = audio.copy()
    hum = opts.get('hum', 'off')
    if hum in ('50', '60'):
        for freq in range(int(hum), 1000, int(hum)):
            check()
            b, a = signal.iirnotch(freq, 30, RATE)
            out = signal.lfilter(b, a, out).astype(np.float32)
    if opts.get('denoise') or opts.get('dehiss'):
        # Bounded blocks with overlap: keep memory low on long recordings.
        chunk, overlap = RATE * 30, RATE
        accum = np.zeros(len(out), dtype=np.float32)
        weights = np.zeros(len(out), dtype=np.float32)
        for start in range(0, len(out), chunk - overlap):
            check()
            block = out[start:start + chunk]
            if len(block) < 512:
                accum[start:start + len(block)] += block
                weights[start:start + len(block)] += 1
                continue
            freqs, _, z = signal.stft(block, RATE, nperseg=512, noverlap=384)
            power = np.abs(z) ** 2
            noise = np.quantile(power, 0.15, axis=1, keepdims=True)
            strength = float(opts.get('strength', .35))
            amount = 1 + 3 * strength
            gain = np.sqrt(np.maximum(0.12, 1 - amount * noise / (power + 1e-12)))
            if not opts.get('denoise'):
                gain[freqs < 3000] = 1
            _, restored = signal.istft(z * gain, RATE, nperseg=512, noverlap=384)
            restored = restored[:len(block)]
            window = np.ones(len(block), dtype=np.float32)
            ramp = min(overlap, len(block) // 2)
            if start > 0:
                window[:ramp] = np.linspace(.001, 1, ramp)
            if start + len(block) < len(out):
                window[-ramp:] = np.linspace(1, .001, ramp)
            accum[start:start + len(block)] += restored * window
            weights[start:start + len(block)] += window
            progress(min(1, (start + len(block)) / len(out)))
        out = accum / np.maximum(weights, .001)
    if opts.get('normalize') and len(out):
        peak = float(np.max(np.abs(out)))
        if peak > 1e-5:
            out *= min(4.0, .89 / peak)
    progress(1)
    return np.clip(out, -1, 1).astype(np.float32)

def spectrogram_png(path, start=0, end=None, width=1400, height=260):
    # Read only the requested range, then build a bounded-size STFT image.
    with sf.SoundFile(str(path)) as f:
        rate = f.samplerate
        duration = len(f) / rate
        start = max(0, min(float(start), duration))
        end = min(duration, float(end) if end is not None else duration)
        end = max(start, end)
        count = max(0, int((end - start) * rate))
        # Long recordings are represented by evenly spaced windows, without resampling pitch.
        positions = np.linspace(int(start * rate), max(int(start * rate), int(end * rate) - 512), width).astype(int)
        matrix = np.zeros((257, width), dtype=np.float32)
        window = np.hanning(512)
        for i, pos in enumerate(positions):
            f.seek(min(pos, len(f)))
            block = f.read(512, dtype='float32', always_2d=True).mean(axis=1)
            if len(block) < 512:
                block = np.pad(block, (0, 512 - len(block)))
            matrix[:, i] = np.abs(np.fft.rfft(block * window))
    db = 20 * np.log10(matrix + 1e-8)
    # Fixed scale means Original/Cleaned comparisons use the same intensity scale.
    level = np.clip((db + 65) / 90, 0, 1)
    stops = np.array([[4, 8, 20], [27, 11, 62], [102, 15, 123], [210, 28, 91], [250, 101, 31], [255, 216, 76], [255, 250, 205]], dtype=float)
    indices = level * (len(stops) - 1)
    lo = indices.astype(int)
    hi = np.minimum(lo + 1, len(stops) - 1)
    frac = (indices - lo)[..., None]
    pixels = (stops[lo] * (1 - frac) + stops[hi] * frac).astype(np.uint8)
    image = Image.fromarray(pixels[::-1]).resize((width, height))
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()
