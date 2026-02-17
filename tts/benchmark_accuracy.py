import os
import csv
import time
import numpy as np
from faster_whisper import WhisperModel
import difflib

# --- CONFIGURATION (Mirroring main.py) ---
WHISPER_MODEL = "distil-small.en"
COMPUTE_TYPE = "int8"
METADATA_PATH = "testdata/metadata.csv"
WAV_DIR = "testdata/wav"
LIMIT = 50  # Number of clips to test

def calculate_wer(reference, hypothesis):
    """Simple Word Error Rate approximation using difflib."""
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()
    
    if not ref_words:
        return 1.0 if hyp_words else 0.0
    
    s = difflib.SequenceMatcher(None, ref_words, hyp_words)
    return 1.0 - s.ratio()

def run_benchmark():
    print(f"Loading Whisper model: {WHISPER_MODEL}...")
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type=COMPUTE_TYPE)
    
    results = []
    
    print(f"Reading metadata from {METADATA_PATH}...")
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter='|')
        data = list(reader)
    
    total_wer = 0
    count = 0
    
    print(f"Starting benchmark on first {LIMIT} clips...")
    
    for row in data[:LIMIT]:
        if not row: continue
        clip_id, ground_truth = row[0], row[1]
        wav_path = os.path.join(WAV_DIR, f"{clip_id}.wav")
        
        if not os.path.exists(wav_path):
            continue
            
        start_time = time.time()
        # Testing beam_size=1 for speed
        segments, info = model.transcribe(
            wav_path, 
            beam_size=1, 
            language="en",
            initial_prompt="This is a technical meeting."
        )
        
        transcription = " ".join([s.text for s in segments]).strip()
        duration = time.time() - start_time
        
        wer = calculate_wer(ground_truth, transcription)
        total_wer += wer
        count += 1
        
        results.append({
            "clip_id": clip_id,
            "ground_truth": ground_truth,
            "transcription": transcription,
            "wer": wer,
            "latency": duration
        })

    # Write results to file
    with open("benchmark_results.md", "w", encoding="utf-8") as f:
        f.write("# Transcription Benchmark Results\n\n")
        
        if count > 0:
            avg_wer = total_wer / count
            avg_latency = sum(r['latency'] for r in results) / count
            
            f.write(f"## Summary Statistics\n")
            f.write(f"- **Avg WER:** {avg_wer:.2%}\n")
            f.write(f"- **Avg Latency/Clip:** {avg_latency:.2f}s\n")
            f.write(f"- **Total Clips:** {count}\n\n")
            
            f.write("## Success Examples (WER < 10%)\n")
            successes = [r for r in results if r['wer'] < 0.1]
            for r in successes[:10]:
                f.write(f"### {r['clip_id']} (WER: {r['wer']:.2%})\n")
                f.write(f"- **GT:** {r['ground_truth']}\n")
                f.write(f"- **TS:** {r['transcription']}\n\n")

            f.write("## Failure Cases (WER > 50%)\n")
            failures = [r for r in results if r['wer'] > 0.5]
            failures.sort(key=lambda x: x['wer'], reverse=True)
            for r in failures[:10]:
                f.write(f"### {r['clip_id']} (WER: {r['wer']:.2%})\n")
                f.write(f"- **GT:** {r['ground_truth']}\n")
                f.write(f"- **TS:** {r['transcription']}\n\n")
        else:
            f.write("No clips were processed.\n")

    print(f"Benchmark complete. Results written to benchmark_results.md")

if __name__ == "__main__":
    run_benchmark()
