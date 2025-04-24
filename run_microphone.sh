#!/bin/bash
cd "$(dirname "$0")"
source mic_venv/bin/activate
python3 receiver.py
