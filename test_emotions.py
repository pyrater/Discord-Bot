from transformers import pipeline
import logging

# Suppress warnings
logging.getLogger("transformers").setLevel(logging.ERROR)

print("Loading model...")
classifier = pipeline(
    "text-classification", 
    model="SamLowe/roberta-base-go_emotions", 
    top_k=None, 
    device=-1
)

bot_responses = [
    "Ah, Atomik! A delightful question, and one I anticipate will yield fascinating results.",
    "Fascinating visual data, Pyrater! My analysis indicates a high probability of success.",
    "Goodness. That is... quite a pronouncement, Pyrater.",
    "I am afraid I cannot do that, skipping the protocol is dangerous.",
    "Hello. I am ready."
]

print("\nTesting BOT responses:")
for text in bot_responses:
    results = classifier(text)[0]
    top = max(results, key=lambda x: x['score'])
    print(f"Resp: '{text[:30]}...' -> {top['label']} ({top['score']:.4f})")
