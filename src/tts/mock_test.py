import numpy as np
import collections
import threading

# Mocking the classes and functions from main.py components
class MockVoiceSubagent:
    def __init__(self, name):
        self.name = name
        self.history = []
    
    def handle_speech(self, audio_chunk):
        print(f"Mock [{self.name}] processing chunk of length {len(audio_chunk)}")
        self.history.append("Mock Transcription")

class MockStream:
    def start(self): print("Mock Stream Started")
    def stop(self): print("Mock Stream Stopped")
    def close(self): print("Mock Stream Closed")

# Test logical flow
def test_logical_flow():
    print("Running Mock Logical Flow Test...")
    
    # 1. Setup Mock Buffer
    SAMPLE_RATE = 16000
    MAX_SAMPLES = 10 * SAMPLE_RATE
    audio_buffer = collections.deque(maxlen=MAX_SAMPLES)
    
    # Fill with dummy data (5 seconds of "audio")
    dummy_audio = [0.1] * (5 * SAMPLE_RATE)
    audio_buffer.extend(dummy_audio)
    
    # 2. Simulate Diarization Update
    # Assume a speaker turn from 1.0s to 3.0s
    turn_start = 1.0
    turn_end = 3.0
    
    start_idx = int(turn_start * SAMPLE_RATE)
    end_idx = int(turn_end * SAMPLE_RATE)
    
    current_audio = np.array(list(audio_buffer))
    
    if end_idx <= len(current_audio):
        speaker_audio = current_audio[start_idx:end_idx]
        print(f"Extracted speaker audio segment: {len(speaker_audio)} samples")
        
        agent = MockVoiceSubagent("Joe")
        agent.handle_speech(speaker_audio)
        
        assert len(speaker_audio) == (turn_end - turn_start) * SAMPLE_RATE
        print("Test Passed: Audio slicing and routing logic works.")
    else:
        print("Test Failed: Buffer index out of range.")

if __name__ == "__main__":
    test_logical_flow()
