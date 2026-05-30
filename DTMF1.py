from scipy.io import wavfile as wav
import numpy as np
import os
import random
import itertools


keymap = [
    ['0', 941, 1336],
    ['*', 941, 1209],
    ['#', 941, 1477],

    ['1', 697, 1209],
    ['2', 697, 1336],
    ['3', 697, 1477],

    ['4', 770, 1209],
    ['5', 770, 1336],
    ['6', 770, 1477],

    ['7', 852, 1209],
    ['8', 852, 1336],
    ['9', 852, 1477],

    ['A', 697, 1633],
    ['B', 770, 1633],
    ['C', 852, 1633],
    ['D', 941, 1633]
]

# Minimum RMS energy a chunk must have to be considered non-silent.
# For 16-bit PCM audio this is a good starting point; lower it if
# you miss real tones, raise it if silence still leaks through.
SILENCE_RMS_THRESHOLD = 300

# Maximum combined Hz distance between a candidate pair of FFT peaks
# and the nearest DTMF key pair.  Real DTMF tones are exact, so a
# genuinely pressed key will score near 0.  Noise rarely lands this
# close to a valid pair — tighten further if false positives persist.
FREQ_MATCH_THRESHOLD = 5


def findNearest(f1, f2, threshold):
    """Return the DTMF key whose row/column frequencies are closest to
    (f1, f2), but only if the total distance is strictly below *threshold*.
    Returns ('', threshold) when nothing qualifies."""
    answer = ''
    best = threshold          # only accept a match strictly better than this
    for key in keymap:
        dist1 = np.abs(f1 - key[1]) + np.abs(f2 - key[2])
        dist2 = np.abs(f1 - key[2]) + np.abs(f2 - key[1])
        dist = float(np.min([dist1, dist2]))
        if dist < best:
            best = dist
            answer = key[0]
    return answer, best


def DTMF(signal, rate):
    """Decode a single chunk of audio into a DTMF character (or '' if
    the chunk is silent or does not contain a recognisable DTMF tone)."""

    # ── 1. Silence gate ──────────────────────────────────────────────
    # Convert to float so squaring never overflows for int16 input.
    signal_f = signal.astype(np.float64)
    rms = np.sqrt(np.mean(signal_f ** 2))
    if rms < SILENCE_RMS_THRESHOLD:
        return ''

    # ── 2. Spectrum ───────────────────────────────────────────────────
    DTFT = np.fft.fft(signal_f)[range(int(len(signal_f) / 2))]
    DTFT_abs = np.abs(DTFT)

    # Additional amplitude gate: even after the RMS check, reject if
    # the single loudest spectral bin is below a meaningful level.
    if np.max(DTFT_abs) < 1000:
        return ''

    # ── 3. Pick the 7 loudest bins ────────────────────────────────────
    high_amp = np.sort(DTFT_abs)[-7:]

    high_f = np.array([])
    for f in high_amp:
        # np.where may return multiple indices for equal amplitudes;
        # take only the first to keep the count predictable.
        indices = np.where(DTFT_abs == f)[0]
        high_f = np.append(high_f, indices[0])

    if high_f.shape[0] != 7:
        return ''

    # Convert bin indices → Hz
    sec = rate / len(signal_f)
    high_f = high_f * sec

    # ── 4. Find the best-matching frequency pair ──────────────────────
    result = ''
    best_dist = FREQ_MATCH_THRESHOLD   # reject anything ≥ this

    for a, b in itertools.combinations(high_f, 2):
        candidate, dist = findNearest(a, b, best_dist)
        if dist < best_dist:
            best_dist = dist
            result = candidate

    return result