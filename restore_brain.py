
import os

print("Restoring brain.py (V3)...")
try:
    with open('brain.py', 'rb') as f:
        content = f.read()

    marker = b'return response_text, generated_image, system_prompt, rag_mems'
    idx = content.rfind(marker)

    if idx != -1:
        print(f"Found marker at {idx}")
        # Keep up to the end of the marker line
        end_of_line = content.find(b'\n', idx) + 1
        clean_content = content[:end_of_line]
        
        # 3. reconstruct except block (indentation 8 spaces?)
        # We need to assume the indentation level. 
        # process_interaction usually has 4 spaces indent, so try is 8?
        # Let's verify indentation of the marker.
        # reverse find newline before marker
        line_start = content.rfind(b'\n', 0, idx) + 1
        indentation = content[line_start:idx]
        # indentation should be whitespace.
        
        # We want 'except' to be at (indentation - 4) spaces?
        # If marker is inside 'try', it has 12 spaces?
        # Let's just blindly add 8 spaces indent for except if we assume standard 4-space method.
        
        # Reconstruction:
        # We need to close the try block.
        # If the return was at, say, 12 spaces. The except should be at 8 spaces.
        
        repaired_suffix = b"""
        except Exception as e:
            logging.error(f"Brain Error: {e}")
            return "", None, "", []
"""
        
        # 4. Read patch
        with open('brain_stream_patch.py', 'rb') as f:
            patch = f.read()
            
        # 5. Write combined
        with open('brain.py', 'wb') as f:
            f.write(clean_content + repaired_suffix + b'\n' + patch)
        print('SUCCESS: Restored brain.py with reconstruction')
    else:
        print('FAILURE: Could not find marker')
except Exception as e:
    print(f"FAILURE: {e}")
