import sounddevice as sd

def list_audio_devices():
    devices = sd.query_devices()
    print("Available Audio Devices:")
    for i, dev in enumerate(devices):
        print(f"{i}: {dev['name']} (Inputs: {dev['max_input_channels']}, Outputs: {dev['max_output_channels']})")
    
    default_input = sd.default.device[0]
    print(f"\nDefault Input Device Index: {default_input}")
    if default_input != -1:
        print(f"Default Input Device: {devices[default_input]['name']}")
    else:
        print("No default input device found!")

if __name__ == "__main__":
    list_audio_devices()
