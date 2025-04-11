import asyncio
import websockets
import sounddevice as sd
import numpy as np
import queue
import json
from scipy.signal import resample

CHUNK = 256
RATE = 48000
audio_buffer = np.zeros((0, 1), dtype=np.int16)
current_speaker = None

def resample_audio(data, from_rate, to_rate):
    samples = np.frombuffer(data, dtype=np.int16)
    new_len = int(len(samples) * to_rate / from_rate)
    resampled = resample(samples, new_len).astype(np.int16)
    return resampled.reshape(-1, 1)

def audio_callback(outdata, frames, time, status):
    global audio_buffer
    if audio_buffer.shape[0] >= frames:
        outdata[:] = audio_buffer[:frames]
        audio_buffer = audio_buffer[frames:]
    else:
        outdata.fill(0)

stream = sd.OutputStream(
    samplerate=RATE,
    channels=1,
    dtype='int16',
    blocksize=CHUNK,
    callback=audio_callback
)
stream.start()

current_client = None
client_lock = asyncio.Lock()

async def handle_client(websocket):
    global current_speaker, audio_buffer, current_client

    # Acquire the lock briefly to check and potentially reject
    async with client_lock:
        if current_client is not None:
            await websocket.send("rejected")
            await websocket.close(reason="Only one client allowed at a time")
            print("Rejected additional client")
            return
        current_client = websocket

    client_sample_rate = RATE  # default fallback

    try:
        async for message in websocket:
            if isinstance(message, str):
                if message == "request":
                    if current_speaker is None:
                        current_speaker = websocket
                        await websocket.send("granted")
                        print("Speaker connected")
                    else:
                        await websocket.send("rejected")
                        websocket.close()
                        return
                else:
                    try:
                        data = json.loads(message)
                        if "rate" in data:
                            client_sample_rate = data["rate"]
                            print(f"Client sample rate: {client_sample_rate}")
                    except json.JSONDecodeError:
                        pass
                continue

            if websocket == current_speaker:
                if client_sample_rate != RATE:
                    samples = resample_audio(message, client_sample_rate, RATE)
                else:
                    samples = np.frombuffer(message, dtype=np.int16).reshape(-1, 1)

                audio_buffer = np.vstack([audio_buffer, samples])

    except Exception as e:
        print("Error:", e)
    finally:
        if websocket == current_speaker:
            current_speaker = None
            print("Speaker disconnected")
        if websocket == current_client:
            current_client = None
            print("Client disconnected")

async def main():
    async with websockets.serve(handle_client, "0.0.0.0", 2000):
        print("Server listening on ws://0.0.0.0:2000")
        await asyncio.Future()

asyncio.run(main())