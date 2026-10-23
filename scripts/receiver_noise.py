"""Explicit receiver-noise engines; legacy NumPy stream remains the default.

The Torch stream is a separate reproducible experiment protocol, not bitwise
equivalent to NumPy or across device/library versions. Neither is normalized.
"""
import numpy as np


def receiver_noise(shape,power,seed,trial,run,*,engine='numpy',device='cpu'):
    if not np.isfinite(power) or power<=0:raise ValueError('noise power must be finite and positive')
    sequence=np.random.SeedSequence([seed,trial,run])
    if engine=='numpy':
        rng=np.random.default_rng(sequence)
        return np.sqrt(power/2)*(rng.standard_normal(shape)+1j*rng.standard_normal(shape))
    if engine!='torch':raise ValueError('unknown receiver noise engine')
    import torch
    generator=torch.Generator(device=device)
    generator.manual_seed(int(sequence.generate_state(1,dtype=np.uint64)[0]))
    real=torch.randn(shape,generator=generator,device=device,dtype=torch.float64)
    imag=torch.randn(shape,generator=generator,device=device,dtype=torch.float64)
    return torch.complex(real,imag)*np.sqrt(power/2)
