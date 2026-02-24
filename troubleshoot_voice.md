# TARS Voice Interaction Troubleshooting

If TARS stops listening after being interrupted during speech and requires a `!join` command to reset, it is likely due to one of the following technical bottlenecks in the voice pipeline:

Looking at your code, the most likely culprit is #3 — the DiscordAudioSink getting detached.
Here's why I'm confident: discord-ext-voice-recv requires the sink to be actively attached to the VoiceClient to receive packets. When you interrupt the bot, vc.play() is either stopped or conflicts with the existing playback state. The library can silently drop the sink in this scenario, and nothing in your code re-attaches it. The bot isn't "frozen" — it's just not receiving any audio at all, so no packets reach VoiceSubagent, nothing hits transcription_queue, and the whole pipeline starves silently.
The tell-tale sign: after !join, the cog almost certainly calls vc.listen(sink) again, which re-attaches the sink — and everything works immediately. If it were a queue lock (#1), cooldown (#6), or stream cancellation (#9) issue, !join wouldn't fully fix it since those are state problems that persist on the existing objects.
To confirm, add a log line in DiscordAudioSink.write() — if you see it stops printing after the interruption, the sink is detached.


# Voice Interruption Troubleshooting

## Why the Bot Stops Listening After Being Interrupted

---

### 1. `AudioQueue.is_playing` Gets Stuck as `True`

When the bot is interrupted mid-speech, the `after_play` callback in `AudioQueue` may never fire (because the `VoiceClient` was stopped/disconnected abruptly). This leaves `self.is_playing = True` permanently. Since `add()` only calls `play_next()` when `is_playing` is `False`, the queue locks up and no future audio—including the bot re-engaging the mic pipeline—ever processes correctly.

---

### 2. `VoiceClient.play()` Raises an Exception That Silences the Queue

In `AudioQueue.play_next()`, if `self.vc.play()` throws (e.g., because the voice client is in a broken state after the interruption), the `except` block calls `self.play_next()` recursively before the queue can recover—potentially exhausting the queue and leaving `is_playing = False` with no listeners re-registered on the sink.

---

### 3. The `DiscordAudioSink` Is Detached When Playback Is Interrupted

`discord-ext-voice-recv` links the audio sink to the `VoiceClient`. When the bot starts playing with `vc.play()`, and that playback is abruptly cut (by another `vc.play()` call or a network hiccup), the sink can become unregistered or stop receiving packets silently. Nothing in `VoiceBridge` or `DiscordAudioSink` re-attaches the sink after a stop event.

---

### 4. `VoiceSubagent` Audio Buffer Is Not Flushed or Reset After Interruption

When the bot is interrupted, the `VoiceSubagent` for that user may have a partially filled `audio_buffer` and a stale `last_ts` timestamp. The silence monitor in `_silence_monitor_loop` checks `(current_time - agent.last_ts) > 0.6s`, but if `last_ts` was updated during the interruption event, the flush never triggers and the buffer sits full indefinitely, blocking new speech from being processed.

---

### 5. `transcription_queue` Backs Up With Stale Packets

During the bot's speech, Discord may still be receiving audio packets (including the bot's own voice looped back, or the user's interruption). These stack up in `transcription_queue`. When the user speaks after the interruption, their audio is behind a backlog of stale chunks. By the time those are processed, the perceived "silence" has already passed and the result is either dropped or ignored by the wake-word trigger logic.

---

### 6. The Cooldown Check Blocks the Resumed Interaction

`ConversationManager.check_cooldown()` uses `last_bot_message_time` to enforce an 8-second silence window. When the bot is interrupted, `last_bot_message_time` was just set for that channel. The user's follow-up voice command (or even re-trigger) hits the cooldown and is silently dropped — giving the impression the bot has stopped listening entirely.

---

### 7. `should_respond` Gatekeeper Rejects the Post-Interruption Utterance

In `process_voice_queue()`, if the interruption text doesn't contain a wake word, the brain's `should_respond()` gatekeeper is called. The recent context at that moment includes the bot's partially spoken response — which can confuse the LLM into returning `False` (i.e., "I was just speaking, no need to respond"), causing the bot to silently ignore the user until the context window clears.

---

### 8. `sentence_buffer` in `handle_interaction` Is Never Flushed

If the user interrupts the bot mid-stream, `handle_interaction` may still be running its `async for` loop yielding tokens. The `sentence_buffer` accumulates tokens but never hits a sentence-boundary character (`.`, `?`, `!`, `\n`) because the stream was cut. The final flush block at step 5 of `handle_interaction` only runs after the full stream completes — which may never happen if the coroutine is not properly cancelled.

---

### 9. No Interrupt / Stop Signal Is Sent to the `CognitiveEngine` Stream

There is no mechanism to cancel `brain.process_interaction_stream()` when a new voice input arrives. If the bot is mid-generation when interrupted, the old stream keeps running in the background, holding the `audio_queue` object and potentially conflicting with a new `AudioQueue` instance created for the new interaction.

---

### 10. `multiprocessing.Queue` Result Is Consumed by the Wrong Consumer

`transcription_engine.py` uses a `multiprocessing.Queue` (`res_q`) shared across all speakers. If the bot's own audio gets looped back through Discord (common in some server configurations), the transcription worker may produce a result attributed to the wrong `sa_id`, or a result is consumed and discarded before `process_voice_queue()` can act on it — meaning the user's real interruption result is silently dropped.

---

## Quick Fixes to Try

- **Reset `is_playing`**: Add a `reset()` method to `AudioQueue` that sets `is_playing = False` and clears the queue, called whenever `vc.stop()` is triggered.
- **Re-attach the sink**: After any `vc.stop()` / `vc.play()` sequence, verify the `DiscordAudioSink` is still registered.
- **Clear the cooldown on interrupt**: When a wake word is detected, bypass or reset `last_bot_message_time` for that channel.
- **Cancel the old stream**: Keep a reference to the running `handle_interaction` task and `task.cancel()` it when a new voice input arrives for the same guild.
- **Drain the transcription queue**: On interruption, drain stale items from `transcription_queue` before processing new audio.



### 1. Gatekeeper Deadlock (Main Voice Loop)
The `process_voice_queue` loop in `script.py` relies on the `brain.should_respond` function to decide if it should reply to what it just heard. This function uses a local LLM (Gemma via `llama-cpp-python`) as a "Gatekeeper."
*   **The Issue**: If the Gatekeeper hangs or encounters a race condition, the entire processing loop stops. New voice transcriptions pile up in the queue but are never processed.
*   **Why `!join` Helps**: It doesn't directly fix the loop, but it re-establishes the voice connection which can sometimes clear temporary network-level receiver blocks.

### 2. Transcription Queue Backlog (Whisper Worker)
TARS uses a separate process for Whisper transcription. Audio chunks are sent to this process via a `transcription_queue`.
*   **The Issue**: If Whisper becomes extremely slow or the worker process hangs, the queue fills up. When the queue is full, the `DiscordAudioSink` (the component that "hears" you) will **block** while trying to add more audio. 
*   **Result**: This freezes the voice receiver threads, making TARS essentially "deaf."

### 3. "Stopped" State in AudioQueue
When you interrupt TARS, the Barge-In logic calls `audio_queue.stop()`. This sets an internal `_stopped` flag to True to prevent any further queued sentences from playing.
*   **The Issue**: If an interaction is interrupted but the interaction task itself isn't fully cancelled, the bot might still be trying to "speak" to a stopped queue in the background. While this primarily affects output, it can cause logical desyncs where the bot thinks it's still busy.

### 4. Background Task Overlap (Barge-In Recovery)
When TARS stops speaking because you interrupted, the code in `voice_bridge.py` stops the audio, but it does **not** cancel the LLM's "thinking" task.
*   **The Issue**: The bot may still be generating a response to your *previous* message while you are already trying to give it a *new* command. If the system is under high load or the LLM is slow, this can create a "dead" period where the bot is technically busy processing a ghost interaction and ignores new input.

### 5. Receiver Thread Crash (discord-ext-voice-recv)
Barge-in triggers a sudden `vc.stop()` command.
*   **The Issue**: In some edge cases, stopping the playback while the receiver is actively handling incoming packets can cause a synchronization error in the `voice-recv` library, causing the packet receiver thread to terminate.
*   **Why `!join` Helps**: Calling `!join` re-attaches the sink and starts a fresh listening listener, which restarts the receiver threads.

---
**Recommendation**: Check the `bot.log` for "Gatekeeper error" or "Worker: Processing chunk" timestamps. If the worker timestamps stop appearing, the issue is process-level (Reason 2). If the log says "Gatekeeper Check: PASSED" but no response follows, the issue is likely Reason 1 or 4.
