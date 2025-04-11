1. sudo apt install -y caddy libportaudio2 libopenblas0
2. python3 -m venv mic_venv
3. source mic_venv/bin/activate
4. pip install websockets sounddevice numpy scipy
5. sudo nano /etc/caddy/Caddyfile
6. sudo systemctl enable caddy --now
7. python3 receiver.py
