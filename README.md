# Raspberry Pi LAN Microphone Server Setup

Turn your Raspberry Pi into a wireless LAN microphone hub! This guide sets up:
- A secure HTTPS web page for mic streaming
- A WebSocket server that receives and plays the audio
- Access via `https://mic.local` on your network

---

## ✅ Hardware Requirements
- Raspberry Pi 3, 4, or 5 (Pi Zero 2 W may work with small CHUNK sizes)
- Speaker or audio out (3.5mm jack or HDMI)
- Wi-Fi or Ethernet connection

---

## 📦 Step 1: Install System Packages

### (Optional) Enable SSH Access:
To remotely access your Raspberry Pi via SSH:
```bash
sudo apt install -y openssh-server
sudo systemctl enable ssh --now
```

### Required Packages:
```bash
sudo apt update
sudo apt install -y python3-pip caddy avahi-daemon libportaudio2 libopenblas0
```

---

## 🐍 Step 2: Install Python Dependencies
```bash
# Create and activate virtual environment
python3 -m venv mic_venv
source mic_venv/bin/activate

# Install Python packages
pip install websockets sounddevice numpy scipy
```

---

## 🌍 Step 3: Enable mDNS with Avahi
```bash
sudo systemctl enable avahi-daemon --now
```

Since your Pi is already named `mic`, it will automatically respond to `mic.local` via mDNS. No additional Avahi service files are required.

---

## 🌐 Step 4: Create and Configure Your Caddyfile
```bash
sudo nano /etc/caddy/Caddyfile
```
Paste this:
```caddyfile
https://mic.local:443 {
    root * /home/pi/Microphone
    file_server
    tls internal

    @ws {
        path /ws*
    }
    reverse_proxy @ws localhost:2000
}
```

Make sure your HTML/JS client is in `/home/pi/Microphone`

Start Caddy:
```bash
sudo caddy run --config /etc/caddy/Caddyfile
```

---

## 🔊 Step 5: Create the Audio Receiver Script
Save this as `receiver.py`:
```python
import asyncio
import websockets
import sounddevice as sd
import numpy as np
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

clients = set()


async def handle_client(websocket):
    global current_speaker, audio_buffer
    clients.add(websocket)
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
        clients.remove(websocket)
        if websocket == current_speaker:
            current_speaker = None
            print("Speaker disconnected")


async def main():
    async with websockets.serve(handle_client, "0.0.0.0", 2000):
        print("Server listening on ws://0.0.0.0:2000")
        await asyncio.Future()


asyncio.run(main())
```
Run it:
```bash
python3 receiver.py
```

---

## 📱 Step 6: Access from a Phone
1. Connect the phone to the same Wi-Fi network
2. Open browser and go to: `https://mic.local`
3. Accept the HTTPS warning if prompted
4. Tap to allow mic access
5. Speak and hear audio from the Pi!

---

## 💻 Step 7: Add the HTML Client
Save this as `/home/pi/Microphone/index.html`:

```html
<!DOCTYPE html>
<html>
<head>
  <title>Mic Stream</title>
  <style>
    body {
      font-family: sans-serif;
      text-align: center;
      margin-top: 10vh;
    }

    #mic-button {
      font-size: 2em;
      padding: 1em 2em;
      border: none;
      border-radius: 1em;
      cursor: pointer;
      background-color: red;
      color: white;
    }

    #mic-button.connected {
      background-color: green;
    }
  </style>
</head>
<body>
  <h2>Tap to Speak</h2>
  <button id="mic-button" onclick="toggleMic()">Start Mic</button>

  <script>
    let isSpeaker = false;
    let socket = null;
    let stream = null;
    let audioContext = null;
    let processor = null;

    async function toggleMic() {
      const button = document.getElementById("mic-button");

      if (isSpeaker) {
        console.log("Stopping mic...");
        socket?.close();
        processor?.disconnect();
        stream?.getTracks().forEach(track => track.stop());
        audioContext?.close();

        isSpeaker = false;
        button.classList.remove("connected");
        button.textContent = "Start Mic";
        return;
      }

      console.log("Connecting to mic...");

      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioContext = new AudioContext();
        const source = audioContext.createMediaStreamSource(stream);
        processor = audioContext.createScriptProcessor(256, 1, 1);

        socket = new WebSocket("wss://mic.local/ws");
        socket.binaryType = "arraybuffer";

        socket.onopen = () => {
          socket.send("request");
        };

        socket.onmessage = (event) => {
          if (event.data === "granted") {
            isSpeaker = true;
            button.classList.add("connected");
            button.textContent = "Mic Connected";
            console.log("WebSocket open");

            socket.send(JSON.stringify({
              type: "config",
              sampleRate: audioContext.sampleRate,
              rate: audioContext.sampleRate
            }));

            source.connect(processor);
            processor.connect(audioContext.destination);

            processor.onaudioprocess = (e) => {
              const input = e.inputBuffer.getChannelData(0);
              const buffer = new Int16Array(input.length);
              for (let i = 0; i < input.length; i++) {
                buffer[i] = input[i] * 0x7FFF;
              }
              if (isSpeaker && socket?.readyState === WebSocket.OPEN) {
                socket.send(buffer);
              }
            };
          } else {
            console.log("Mic already in use. Closing connection.");
            socket.close();
            stream.getTracks().forEach(track => track.stop());
            audioContext.close();
          }
        };

        socket.onclose = () => {
          console.log("WebSocket closed");
          isSpeaker = false;
          button.classList.remove("connected");
          button.textContent = "Start Mic";
        };
      } catch (e) {
        console.error("Failed to get microphone:", e);
        button.classList.remove("connected");
        button.textContent = "Mic Failed";
      }
    }
  </script>
</body>
</html>
```

---

## 🧠 Optional: Run on Boot with systemd
(Ask if you'd like to set this up!)

---

## 🎉 You're Done!
You now have a fully functional Raspberry Pi LAN microphone receiver, accessible from phones over HTTPS with `mic.local` 🎤⚡