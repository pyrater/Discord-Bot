import torch
import numpy as np
import soundfile as sf
import os

# Create a dummy audio file (5 seconds of white noise)
if not os.path.exists("test_audio.wav"):
    sr = 16000
    noise = np.random.uniform(-0.1, 0.1, sr * 5)
    sf.write("test_audio.wav", noise, sr)

print("Dummy audio created.")
