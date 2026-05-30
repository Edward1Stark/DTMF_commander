import numpy as np
from itertools import groupby
import DTMF1


def DTMF(signal, rate):
    """Decode a full audio signal into a string of DTMF characters.

    The signal is split into 200 ms chunks.  Each chunk passes through
    an RMS silence gate (inside DTMF1.DTMF) before any spectral work is
    done, so ambient noise or a silent room never produces phantom keys.
    """
    length = len(signal) / rate
    chunk_count = int(length / 0.2)
    if chunk_count == 0:
        chunk_count = 1

    # reshape is a no-op on a 1-D array but kept for safety
    signal = signal.reshape(signal.shape[0])
    chunks = np.array_split(signal, chunk_count)

    res = []
    for chunk in chunks:
        # ── Per-chunk RMS silence gate ────────────────────────────────
        # This is an early-exit optimisation: skip the FFT entirely for
        # chunks that are clearly silent, before DTMF1 even runs.
        chunk_f = chunk.astype(np.float64)
        rms = np.sqrt(np.mean(chunk_f ** 2))
        if rms < DTMF1.SILENCE_RMS_THRESHOLD:
            res.append('')
            continue

        res.append(DTMF1.DTMF(chunk, rate))

    # Collapse consecutive identical results (including runs of '')
    # then throw away the empty strings.
    grouped_res = [key for key, _ in groupby(res) if key != '']
    result = ''.join(grouped_res)

    return result