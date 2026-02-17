import os
import requests

def verify_hf_token(token):
    print(f"Verifying token: {token[:6]}...{token[-4:]}")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test 1: Check if token is valid
    whoami = requests.get("https://huggingface.co/api/whoami-v2", headers=headers)
    if whoami.status_code != 200:
        print("FAILED: Token is invalid or expired.")
        return
    print("SUCCESS: Token is valid.")
    
    # Test 2: Check access to pyannote/segmentation API
    model_url = "https://huggingface.co/api/models/pyannote/segmentation"
    resp = requests.get(model_url, headers=headers)
    
    if resp.status_code == 200:
        print("SUCCESS: You have access to model metadata.")
    elif resp.status_code == 403:
        print("FAILED: 403 Forbidden on API. You likely haven't accepted terms.")
        return
    
    # Test 3: Check access to the actual model file (The 403 culprit)
    file_url = "https://huggingface.co/pyannote/segmentation/resolve/main/pytorch_model.bin"
    file_resp = requests.head(file_url, headers=headers)
    
    if file_resp.status_code == 302 or file_resp.status_code == 200:
        print("SUCCESS: You HAVE permission to download the model file!")
    elif file_resp.status_code == 403:
        print("FAILED: 403 Forbidden on FILE DOWNLOAD.")
        print("  CRITICAL FIX: Your fine-grained token lacks 'Read access to contents of all public gated repositories'.")
        print("  Go to: https://huggingface.co/settings/tokens")
    else:
        print(f"FAILED: Unexpected status code {file_resp.status_code} on file download.")

if __name__ == "__main__":
    token = os.getenv("HF_TOKEN")
    verify_hf_token(token)
