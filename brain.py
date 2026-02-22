import os
import re
import time
import asyncio
import logging
import json
import random
import httpx
from datetime import datetime
from llama_cpp import Llama
import math
import sys
import subprocess
import base64
from bot_config import settings
# Force environment cleanup for search
try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        logging.error("🧠 Brain: Search dependencies (ddgs/duckduckgo_search) missing.")
        DDGS = None

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("🧠 Brain: Installing missing dependency 'beautifulsoup4' & 'requests'...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4", "requests"])
    import requests
    from bs4 import BeautifulSoup

try:
    from PIL import Image
    import io
except ImportError:
    print("🧠 Brain: Installing missing dependency 'Pillow'...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image
    import io

class CognitiveEngine:
    def __init__(self, memory_engine, llm_client, model_name, comfy_url, local_llm_path="/app/models/google_gemma-3-270m-it-Q8_0.gguf", lazy_load=False):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.memory_engine = memory_engine
        self.ai_client = llm_client
        self.model_name = model_name
        self.comfy_url = comfy_url
        
        # Local "Fast" LLM for Gatekeeper
        self.gatekeeper = None
        if not lazy_load:
            try:
                logging.info("🧠 Brain: Loading Gatekeeper (Gemma)...")
                
                # Resolve model path
                if not os.path.isabs(local_llm_path):
                    resolved_model_path = os.path.join(self.base_dir, local_llm_path)
                else:
                    resolved_model_path = local_llm_path
                    
                self.gatekeeper = Llama(
                    model_path=resolved_model_path,
                    n_ctx=2048, n_threads=4, verbose=False
                )
            except Exception as e:
                logging.warning(f"🧠 Brain: Gatekeeper load failed ({e}). Conversational mode optimized.")
                self.gatekeeper = None

        # Circuit Breakers state
        self.breakers = {
            "comfy": {"failures": 0, "next_try": 0},
            "llm": {"failures": 0, "next_try": 0}
        }
        
        # Load Persona
        try:
            p_path = os.path.join(self.base_dir, "chars", "TARS.json")
            logging.info(f"🧠 Brain: Loading Persona from {p_path}")
            with open(p_path, "r", encoding="utf-8") as f:
                self.persona = json.load(f)
        except Exception as e:
            logging.error(f"❌ Failed to load Persona: {e}")
            self.persona = {}

    def count_tokens(self, text):
        return self.memory_engine.count_tokens(text)

    async def decide_context(self, system_base, user_msg, rag_memories, short_term_history, max_tokens=settings.MAX_TOKENS):
        """
        Intelligently assembles context within token limits.
        Returns: (final_history_list, final_memories_list)
        """
        # 1. Base Cost
        base_tokens = self.count_tokens(system_base) + self.count_tokens(user_msg)
        available = max_tokens - base_tokens
        
        if available < 50: return [], []

        final_history = []
        final_memories = []
        
        # 2. Priority 1: Last 5 Messages (Short Term)
        processed_history = list(reversed(short_term_history)) 
        priority_history = processed_history[:5]
        remaining_history = processed_history[5:]
        
        for msg in priority_history:
             t = self.count_tokens(msg)
             if available >= t:
                 final_history.insert(0, msg)
                 available -= t
             else: break 
                 
        # 3. Priority 2: RAG Memories (Top 3)
        for mem in rag_memories[:3]:
             formatted_mem = f"- {mem}"
             t = self.count_tokens(formatted_mem)
             if available >= t:
                 final_memories.append(formatted_mem)
                 available -= t
        
        # 4. Priority 3: Older History
        if available > 50:
             for msg in remaining_history:
                  t = self.count_tokens(msg)
                  if available >= t:
                      final_history.insert(0, msg)
                      available -= t
                      
        return final_history, final_memories

    async def build_full_system_prompt(self, user_facts, vibe_str, memory_str, history_str):
        """Constructs the final huge string for the LLM."""
        facts_block = "\n".join([f"- {f}" for f in user_facts])
        persona_block = self.persona.get('char_persona', 'You are a helpful assistant.')
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M %p")
        
        return (
            f"### SYSTEM PERSONA ###\n{persona_block}\n"
            f"### INTERACTION CONTEXT ###\n[Current Time: {now_str}] [Current Vibe: {vibe_str}]\n"
            f"### KNOWN FACTS ###\n{facts_block}\n"
            f"### RETRIEVED MEMORIES ###\n{memory_str}\n"
            f"### RECENT HISTORY ###\n{history_str}\n"
            "### INSTRUCTIONS ###\n"
            "1. Stay in character (Tars).\n"
            "2. Reply naturally to the user.\n"
            "3. **COMMAND PROTOCOL**: You are an agent. To perform actions, you must use the `ACTION:` syntax. Do not hide these in code blocks.\n"
            "   - Draw Image: `ACTION: generate_image(prompt='description')`\n"
            "   - Search Web: `ACTION: search_web(query='search term')`\n"
            "   - Read Page: `ACTION: browse_web(url='http://...')`\n"
            "   - Dictionary: `ACTION: urban_dictionary(term='slang')`\n"
            "   - Roll Dice: `ACTION: roll_dice(dice_str='2d20')`\n"
            "   - Calculate: `ACTION: calculator(expression='2+2')`\n"
            "   - Reminder: `ACTION: set_reminder(minutes=5, message='do thing')`\n"
            "4. When using an ACTION, you may provide a brief intro, but the ACTION must be on its own line.\n"
            "5. Do NOT include 'Generating...' metadata. Just the action.\n"
            "6. **IMPORTANT**: If the user provides an image, DO NOT generate a new image unless EXPLICITLY instructed to 'mix', 'edit', 'change', or 'redraw' it. Typically, just comment on the image provided."
        )

    def get_tools_schema(self):
        """Returns the function calling schema for the LLM."""
        return [
            {
                "type": "function", "function": {
                    "name": "generate_image", "description": "Draw or Edit an AI image.", 
                    "parameters": {"type": "object", "properties": {"description": {"type": "string"}}, "required": ["description"]}
                }
            },
            {
                "type": "function", "function": {
                    "name": "browse_web", "description": "Visit a URL to get its content.", 
                    "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
                }
            },
            {
                "type": "function", "function": {
                    "name": "search_web", "description": "Search DuckDuckGo for a query.", 
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
                }
            },
            {
                "type": "function", "function": {
                    "name": "urban_dictionary", "description": "Look up a slang term.", 
                    "parameters": {"type": "object", "properties": {"term": {"type": "string"}}, "required": ["term"]}
                }
            },
            {
                "type": "function", "function": {
                    "name": "roll_dice", "description": "Roll RPG dice (e.g. 2d20).", 
                    "parameters": {"type": "object", "properties": {"dice_str": {"type": "string"}}, "required": ["dice_str"]}
                }
            },
            {
                "type": "function", "function": {
                    "name": "calculator", "description": "Evaluate a math expression.", 
                    "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}
                }
            },
            {
                "type": "function", "function": {
                    "name": "set_reminder", "description": "Set a reminder for X minutes.", 
                    "parameters": {"type": "object", "properties": {"minutes": {"type": "number"}, "message": {"type": "string"}}, "required": ["minutes", "message"]}
                }
            }
        ]

    def _encode_image(self, image_bytes):
        """Helper to encode bytes to base64 string."""
        return base64.b64encode(image_bytes).decode('utf-8')

    async def call_comfyui(self, prompt, input_image_bytes=None):
        """
        Sends a prompt to ComfyUI and waits for the image.
        """
        if not self.comfy_url: return "ComfyUI URL not configured."
        
        try:
            workflow = {}
            # Try to find a template
            tpl_path = os.path.join(self.base_dir, "SD-API.json")
            if input_image_bytes and os.path.exists(os.path.join(self.base_dir, "SD-IMG2IMG.json")):
                 tpl_path = os.path.join(self.base_dir, "SD-IMG2IMG.json")
            
            if os.path.exists(tpl_path):
                with open(tpl_path, "r") as f:
                    workflow = json.load(f)
            else:
                return "Error: SD-API.json template not found."

            # Fast Fallback: Tars usually expects Node 6=Positive (or 3 in this template), Node 11=Seed
            if "3" in workflow and "inputs" in workflow["3"]:
                workflow["3"]["inputs"]["text"] = prompt
            
            if "11" in workflow and "inputs" in workflow["11"]:
                 workflow["11"]["inputs"]["noise_seed"] = random.randint(1, 999999999999999)
            elif "3" in workflow and "inputs" in workflow["3"] and "seed" in workflow["3"]["inputs"]:
                 # Fallback for old templates if they existed
                 workflow["3"]["inputs"]["seed"] = random.randint(1, 999999999)

            # --- IMG2IMG UPLOAD ---
            if input_image_bytes:
                # 1. Upload Image
                files = {'image': ('input.png', input_image_bytes, 'image/png')}
                data = {'overwrite': 'true'}
                async with httpx.AsyncClient() as client:
                    up_resp = await client.post(f"{self.comfy_url}/upload/image", files=files, data=data)
                    if up_resp.status_code == 200:
                        # 2. Update LoadImage Node (Node 12 in SD-IMG2IMG.json)
                        # We use the filename returned or just 'input.png' if overwrite=true
                        uploaded_name = up_resp.json().get("name", "input.png")
                        
                        if "12" in workflow and "inputs" in workflow["12"]:
                            workflow["12"]["inputs"]["image"] = uploaded_name
                        else:
                            # Try to find any LoadImage node
                            for k, v in workflow.items():
                                if v.get("class_type") == "LoadImage":
                                    v["inputs"]["image"] = uploaded_name
                                    break
                    else:
                        return f"Img2Img Upload Failed: {up_resp.text}"

            # Send to Comfy
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{self.comfy_url}/prompt", json={"prompt": workflow})
                if resp.status_code != 200:
                    return f"ComfyUI Error: {resp.text}"
                
                prompt_id = resp.json().get("prompt_id")
                
                # Poll for result
                for _ in range(30): # 30 seconds max wait
                    await asyncio.sleep(1)
                    hist_resp = await client.get(f"{self.comfy_url}/history/{prompt_id}")
                    if hist_resp.status_code == 200 and hist_resp.json():
                        history = hist_resp.json()[prompt_id]
                        outputs = history.get("outputs", {})
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                img_info = node_output["images"][0]
                                fname = img_info.get("filename")
                                subfolder = img_info.get("subfolder", "")
                                type_ = img_info.get("type", "output")
                                
                                # Fetch Image
                                img_resp = await client.get(f"{self.comfy_url}/view", params={"filename": fname, "subfolder": subfolder, "type": type_})
                                return img_resp.content # Return bytes
                        
                        break
            
            return "Image generation timed out."

        except Exception as e:
            return f"ComfyUI Failure: {e}"

    # --- TOOLS IMPLEMENTATION ---
    def safe_calc(self, expression):
        try:
            # Very restrictive char set
            if not all(c in "0123456789+-*/(). pi" for c in expression): return "Invalid chars"
            return str(eval(expression, {"__builtins__": None}, {"pi": math.pi}))
        except: return "Math Error"

    def roll_dice(self, dice_str):
        try:
            parts = dice_str.lower().split('d')
            num = int(parts[0]) if parts[0] else 1
            sides = int(parts[1])
            rolls = [random.randint(1, sides) for _ in range(num)]
            return f"{rolls} (Total: {sum(rolls)})"
        except: return "Invalid dice format (use NdN)"

    async def urban_dict(self, term):
        try:
            loop = asyncio.get_event_loop()
            def fetch():
                return requests.get(f"https://api.urbandictionary.com/v0/define?term={term}", timeout=5).json()
            
            data = await loop.run_in_executor(None, fetch)
            if data['list']:
                d = data['list'][0]
                # Clean internal links [word] -> word
                deg = d['definition'].replace("[", "").replace("]", "")
                ex = d['example'].replace("[", "").replace("]", "")
                return f"{deg}\nExample: {ex}"
            return "No definition found."
        except: return "API Error"
        
    async def web_search(self, query):
        lib_name = "ddgs" if "ddgs" in sys.modules else "duckduckgo_search"
        logging.info(f"🔎 Brain: Web Search ({lib_name}) triggered for '{query}'")
        if not DDGS:
            return "Search disabled: search library not found."
            
        try:
            loop = asyncio.get_event_loop()
            def search(backend=None):
                with DDGS() as ddgs:
                    # Try with default backend first, then 'html' if it fails
                    return list(ddgs.text(query, max_results=8, backend=backend) if backend else ddgs.text(query, max_results=8))
            
            results = await loop.run_in_executor(None, search)
            
            # Fallback to 'html' backend if empty
            if not results:
                logging.info(f"🔎 Brain: No results with default backend, trying 'html'...")
                results = await loop.run_in_executor(None, search, "html")

            if not results:
                logging.warning(f"🔎 Brain: Search returned 0 results for '{query}'")
                return f"No results. (Lib: {lib_name}, Query: '{query}')\nDuckDuckGo might be throttling this IP or the query is too specific."
            
            logging.info(f"🔎 Brain: Found {len(results)} results.")
            return "\n".join([f"- {r['title']}: {r['href']} ({r['body']})" for r in results])
        except Exception as e: 
            logging.error(f"🔎 Brain: Search failed: {e}")
            return f"Search failed ({lib_name}): {e}"

    async def browse_web(self, url):
        """Visits a URL and returns a summary of the text."""
        try:
            # clean url
            url = url.strip('<>')
            
            # Synchronous request in thread
            loop = asyncio.get_event_loop()
            def fetch():
                 headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                 r = requests.get(url, headers=headers, timeout=10)
                 return r.text
            
            html = await loop.run_in_executor(None, fetch)
            soup = BeautifulSoup(html, 'html.parser')
            
            # Kill script and style elements
            for script in soup(["script", "style"]):
                script.extract()    

            text = soup.get_text()
            # break into lines and remove leading and trailing space on each
            lines = (line.strip() for line in text.splitlines())
            # break multi-headlines into a line each
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            # drop blank lines
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return text[:2000] + "..." if len(text) > 2000 else text
            
        except Exception as e:
            return f"Error browsing {url}: {e}"

    def sanitize_response(self, text):
        """Removes ACTION blocks and tool tags for clean memory/history."""
        if not text: return ""
        # Remove ACTION:... blocks
        text = re.sub(r'(?:\[|`+)?\s*ACTION:\s*\w+\(.*?\)\s*(?:\]|`+)?', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Remove "Used tool" tags
        text = re.sub(r'📂 \*\*Used \w+\*\*\n?', '', text)
        # Remove any leading/trailing tool headers from older versions
        text = re.sub(r'^\[Tool Result:.*\]$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        return text.strip()

    async def execute_tool(self, fn_name, args, input_image_bytes=None):
        """Executes the mapped tool function."""
        try:
            if fn_name == "generate_image":
                desc = args.get("prompt") or args.get("description")
                if desc: return await self.call_comfyui(desc, input_image_bytes)
            
            elif fn_name == "search_web":
                return await self.web_search(args.get("query"))
            
            elif fn_name == "browse_web":
                return await self.browse_web(args.get("url"))
                
            elif fn_name == "urban_dictionary":
                return await self.urban_dict(args.get("term"))
                
            elif fn_name == "roll_dice":
                return self.roll_dice(args.get("dice_str"))
                
            elif fn_name == "calculator":
                return self.safe_calc(args.get("expression"))
                
            elif fn_name == "set_reminder":
                 # Reminders are handled by callback in script.py, but we need to return the data signal
                 # For now, we return a special string that script.py could parse, OR better:
                 # We simply return the text confirmation and let the parsing logic below handle the callback if we had passed it.
                 # Wait, 'process_interaction' has the callback. We can use it if we refactor.
                 # For simplicity in this text-based flows, we might need to handle reminder differently or pass it out.
                 return f"[REMINDER SET] {args.get('minutes')} min: {args.get('message')}"
                 
            return f"Error: Tool '{fn_name}' not found."
        except Exception as e:
            return f"Error executing {fn_name}: {e}"

    async def should_respond(self, message_text, is_direct, recent_history=""):
        """
        Decides if the bot should reply.
        is_direct: True if DM, Mention, or Reply.
        recent_history: String of recent chat context to help decision.
        """
        if is_direct: return True
        
        # Trigger words check (Whole words only)
        # Regex \b matches word boundaries
        #if re.search(r'\b(tars|brain|bot)\b', message_text, re.IGNORECASE):
            #return True
            
        # Gatekeeper LLM Check
        if self.gatekeeper:
            prompt = f"""<start_of_turn>user
Is the user speaking directly TO Tars?
Previous: {recent_history}
Message: "{message_text}"
Directly addressed to Tars? YES/NO:<end_of_turn>
<start_of_turn>model
"""
            try:
                # Synchronous call in thread
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, lambda: self.gatekeeper(prompt, max_tokens=2, temperature=0.0, stop=["<end_of_turn>", "\\n"]))
                return response['choices'][0]['text'].strip().upper().startswith("YES")
            except Exception as e:
                logging.warning(f"Gatekeeper error: {e}")
                return False
        return False

    async def process_interaction(self, user_id, username, user_text, channel_id="DM", guild_id="DM", conversation_history=[], input_image_bytes=None, reminder_callback=None):
        """
        Centralized logic for processing a user turn.
        Returns: (text_response, image_bytes_or_none, system_prompt, rag_mems)
        """
        # TIMING START
        t_start = time.time()
        
        # 1. GATHER DATA
        vibe_str = await self.memory_engine.get_tars_vibe(user_id)
        user_facts = await self.memory_engine.get_facts(user_id, guild_id)
        t_gather = time.time()
        
        # 2. RETRIEVE MEMORIES
        # Search ALL user memories in this guild (Cross-User Context)
        rag_mems = self.memory_engine.search_memories(user_text, guild_id, user_id=user_id, n_results=5)
        
        # Rerank Memories
        # if rag_mems:
        #     try:
        #         reranked = await self.memory_engine.rerank_memories(user_text, rag_mems, self.ai_client, self.model_name)
        #         rag_mems = reranked
        #     except Exception as e:
        #         logging.warning(f"Rerank failed: {e}")

        # Dreams
        dream_results = self.memory_engine.collection.query(
            query_texts=[user_text],
            where={"$and": [{"user_id": "SYSTEM_DREAM"}, {"guild_id": str(guild_id)}]},
            n_results=2
        )
        dream_mems = dream_results.get('documents', [[]])[0]
        t_rag = time.time()

        # 3. CONSTRUCT CONTEXT
        base_prompt = await self.build_full_system_prompt([], vibe_str, "", "")
        
        hist_list, mem_list = await self.decide_context(
            base_prompt, 
            user_text, 
            rag_mems,
            conversation_history
        )
        
        combined_memories = mem_list + [f"[Dream Context] {dm}" for dm in dream_mems]
        system_prompt = await self.build_full_system_prompt(
            user_facts, 
            vibe_str, 
            "\n".join(combined_memories), 
            "\n".join(hist_list)
        )
        t_prompt = time.time()
        
        # 4. PREPARE PAYLOAD
        message_payload = [{"type": "text", "text": f"{username}: {user_text}"}]
        if input_image_bytes:
             # Offload CPU-heavy image processing
             loop = asyncio.get_event_loop()
             b64_img = await loop.run_in_executor(None, self._encode_image, input_image_bytes)
             
             message_payload.append({
                 "type": "image_url", 
                 "image_url": {"url": f"data:image/png;base64,{b64_img}"}
             })

        # 5. CALL LLM
        response_text = ""
        generated_image = None
        
        try:
            completion = await self.ai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message_payload}
                ],
                # REMOVED NATIVE TOOLS -> tools=self.get_tools_schema(),
                temperature=0.88,
                max_tokens=settings.MAX_GENERATION,
                timeout=30
            )
            msg = completion.choices[0].message
            response_text = msg.content or ""
            
            # --- FORMAL COMMAND PARSER ---
            # Regex to find ACTION: tool_name(args)
            # Support wrapping in [] or ``` or `` or just lines
            # (?:\[|`+)? matches optional starting [ or one or more backticks
            # ACTION:\s*(\w+)\((.*?)\) matches the command
            # \s*(?:\]|`+)? matches optional closing ] or one or more backticks
            cmd_match = re.search(r'(?:\[|`+)?\s*ACTION:\s*(\w+)\((.*?)\)\s*(?:\]|`+)?', response_text, re.DOTALL)
            if cmd_match:
                fn_name = cmd_match.group(1)
                args_str = cmd_match.group(2)
                logging.info(f"🦾 Command Detected: {fn_name}({args_str})")
                
                # CLEANUP: Remove the ACTION line from the visible response immediately
                response_text = response_text.replace(cmd_match.group(0), "").strip()
                
                # Naive Argument Parser (Key-Value or Single String)
                args = {}
                # Try simple key='value' parse (supporting quotes OR unquoted nums)
                kv_matches = re.findall(r'(\w+)\s*=\s*(?:["\']([^"\']*)["\']|([^,\s)]+))', args_str)
                if kv_matches:
                    for k, v_quoted, v_unquoted in kv_matches:
                        args[k] = v_quoted if v_quoted else v_unquoted
                else:
                    # Fallback for single-arg tools (like search, draw)
                    # Use the first likely parameter name based on tool
                    defaults = {
                        "generate_image": "prompt",
                        "search_web": "query", 
                        "browse_web": "url",
                        "urban_dictionary": "term",
                        "roll_dice": "dice_str",
                        "calculator": "expression"
                    }
                    if fn_name in defaults:
                        args[defaults[fn_name]] = args_str.strip('"\' ')
                
                # Execute
                result = await self.execute_tool(fn_name, args, input_image_bytes)
                
                # Special Cases
                if fn_name == "generate_image" and isinstance(result, bytes):
                    generated_image = result
                elif fn_name == "set_reminder" and reminder_callback:
                    try:
                        mins = float(args.get("minutes", 0))
                        note = args.get("message", "Reminder")
                        response_text += f"\n(⏰ Reminder set for {mins}m)"
                        asyncio.create_task(reminder_callback(mins, note))
                    except: pass
                else:
                    # REFINED OUTPUT HANDLING: Notification + Reasoning Pass
                    logging.info(f"🦾 Tool Result for {fn_name}. Generating final summary...")
                    
                    internal_messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message_payload},
                        {"role": "assistant", "content": msg.content},
                        {"role": "user", "content": f"TOOL RESULT for {fn_name}:\n{result}\n\nBased on this result, provide the final answer to the user. Do not include the tool command block."}
                    ]
                    
                    try:
                        final_completion = await self.ai_client.chat.completions.create(
                            model=self.model_name,
                            messages=internal_messages,
                            temperature=0.7,
                            max_tokens=settings.MAX_GENERATION
                        )
                        final_answer = final_completion.choices[0].message.content or ""
                        response_text = f"📂 **Used {fn_name}**\n\n" + final_answer
                    except Exception as e:
                        logging.error(f"Reasoning error: {e}")
                        response_text += f"\n\n📂 **{fn_name} Used**\n(Error summarizing: {e})"
            
            # Cleanup any leftover "ACTION:" lines if regex missed slightly
            response_text = re.sub(r'(?i)^ACTION:.*$', '', response_text, flags=re.MULTILINE)
            response_text = re.sub(r'\n{3,}', '\n\n', response_text).strip()
        except Exception as e:
            logging.error(f"Brain Process Error: {e}")
            response_text = "I tripped over my own neurons..."
            
        t_end = time.time()
        
        # Final Cleanup for memory storage (sanitize)
        clean_text_for_memory = self.sanitize_response(response_text)
        
        return response_text, generated_image, system_prompt, rag_mems, clean_text_for_memory


    async def process_interaction_stream(self, user_id, username, user_text, channel_id="DM", guild_id="DM", conversation_history=[], input_image_bytes=None, reminder_callback=None):
        """
        Streamed version of process_interaction. 
        Yields: ("text", "token_str") or ("tool_result", result_obj) or ("meta", metadata_dict)
        """
        t_start = time.time()
        
        # 1. GATHER (Same as before)
        vibe_str = await self.memory_engine.get_tars_vibe(user_id)
        user_facts = await self.memory_engine.get_facts(user_id, guild_id)
        
        # 2. RETRIEVE (Same as before)
        # Search ALL user memories in this guild (Cross-User Context)
        rag_mems = self.memory_engine.search_memories(user_text, guild_id, user_id=user_id, n_results=5)
        
        dream_results = self.memory_engine.collection.query(
            query_texts=[user_text],
            where={"$and": [{"user_id": "SYSTEM_DREAM"}, {"guild_id": str(guild_id)}]},
            n_results=2
        )
        dream_mems = dream_results.get('documents', [[]])[0]

        # 3. CONTEXT (Same but faster context construction preferred?)
        # 2b. RETRIEVE KNOWLEDGE
        know_docs = self.memory_engine.search_knowledge(user_text, n_results=2)
        
        base_prompt = await self.build_full_system_prompt([], vibe_str, "", "")
        hist_list, mem_list = await self.decide_context(
            base_prompt, user_text, rag_mems, conversation_history
        )
        combined_memories = mem_list + [f"[Dream Context] {dm}" for dm in dream_mems]
        
        # Add Knowledge to Memories or System Prompt?
        # Let's append to memories with a tag
        if know_docs:
            combined_memories.extend([f"[TECHNICAL KNOWLEDGE] {k}" for k in know_docs])

        system_prompt = await self.build_full_system_prompt(
            user_facts, vibe_str, "\n".join(combined_memories), "\n".join(hist_list)
        )
        
        # Yield Metadata immediately so client knows we started
        yield ("meta", {"system_prompt": system_prompt, "memories": rag_mems})
        
        # 4. PAYLOAD
        message_payload = [{"type": "text", "text": f"{username}: {user_text}"}]
        if input_image_bytes:
             loop = asyncio.get_event_loop()
             b64_img = await loop.run_in_executor(None, self._encode_image, input_image_bytes)
             message_payload.append({
                 "type": "image_url", 
                 "image_url": {"url": f"data:image/png;base64,{b64_img}"}
             })

        # 5. STREAMING CALL
        full_response_buffer = ""
        
        try:
            stream = await self.ai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message_payload}
                ],
                temperature=0.88,
                max_tokens=settings.MAX_GENERATION, # Reset to standard output limit
                timeout=45,
                stream=True # ENABLE STREAMING
            )
            logging.info(f"🧠 Streaming with max_tokens={settings.MAX_GENERATION}...")
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_response_buffer += token
                    
                    # Yield text token
                    yield ("text", token)

            # --- POST-STREAM TOOL CHECK ---
            # Streaming + Tools is hard because we need the full text to safely Regex.
            # We process tools AFTER the full stream (Visual latency is fine, Audio latency is the concern)
            # Actually, for tool use (like draw), we usually want to hide the "ACTION:..." text.
            # In streaming, we might leak "ACTION:" to the user. 
            # Strategy: If "ACTION:" appears in buffer, we should probably have suppressed it?
            # For simplicity in V1 Streaming: We let it stream everything. Tool parsing happens at end.
            
            cmd_match = re.search(r'(?:\[|`+)?\s*ACTION:\s*(\w+)\((.*?)\)\s*(?:\]|`+)?', full_response_buffer, re.DOTALL)
            if cmd_match:
                fn_name = cmd_match.group(1)
                args_str = cmd_match.group(2)
                logging.info(f"🦾 Command Detected (Stream End): {fn_name}({args_str})")
                
                # Cleanup buffer purely for internal logic (client already saw it)
                # Ideally we would intercept this during stream, but that adds 500ms latency.
                # User will see "ACTION: ..." then get the result. Acceptable for speed.
                
                args = {}
                kv_matches = re.findall(r'(\w+)\s*=\s*(?:["\']([^"\']*)["\']|([^,\s)]+))', args_str)
                if kv_matches:
                    for k, v_quoted, v_unquoted in kv_matches:
                        args[k] = v_quoted if v_quoted else v_unquoted
                else:
                    defaults = {
                        "generate_image": "prompt", "search_web": "query", "browse_web": "url",
                        "urban_dictionary": "term", "roll_dice": "dice_str", "calculator": "expression"
                    }
                    if fn_name in defaults:
                        args[defaults[fn_name]] = args_str.strip('"\' ')
                
                # Execute Tool
                result = await self.execute_tool(fn_name, args, input_image_bytes)
                
                # Handle Special Cases
                if fn_name == "generate_image" and isinstance(result, bytes):
                    yield ("image", result)
                elif fn_name == "set_reminder" and reminder_callback:
                    try:
                        mins = float(args.get("minutes", 0))
                        note = args.get("message", "Reminder")
                        yield ("text", f"\n(⏰ Reminder set for {mins}m)")
                        asyncio.create_task(reminder_callback(mins, note))
                    except: pass
                else:
                    # REFINED OUTPUT HANDLING: Notification + Streaming Reasoning
                    yield ("text", f"\n\n📂 **Used {fn_name}**\n\n")
                    
                    internal_messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message_payload},
                        {"role": "assistant", "content": self.sanitize_response(full_response_buffer)},
                        {"role": "user", "content": f"TOOL RESULT for {fn_name}:\n{result}\n\nBased on this, provided the final answer."}
                    ]
                    
                    try:
                        reasoning_stream = await self.ai_client.chat.completions.create(
                            model=self.model_name,
                            messages=internal_messages,
                            temperature=0.7,
                            max_tokens=settings.MAX_GENERATION,
                            stream=True
                        )
                        final_clean_buffer = ""
                        async for r_chunk in reasoning_stream:
                            if r_chunk.choices and r_chunk.choices[0].delta.content:
                                r_token = r_chunk.choices[0].delta.content
                                final_clean_buffer += r_token
                                yield ("text", r_token)
                        
                        # Add final metadata for memory capture
                        yield ("meta", {"clean_response": self.sanitize_response(full_response_buffer) + "\n" + final_clean_buffer})
                    except Exception as e:
                        yield ("text", f"\n(Error summarizing {fn_name}: {e})")

        except Exception as e:
            logging.error(f"Stream Error: {e}")
            yield ("text", f" [Error: {e}]")
