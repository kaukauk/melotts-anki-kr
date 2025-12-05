#!/usr/bin/env python3
"""
Test script for Korean TTS using MeloTTS
"""
from melo.api import TTS

# Korean example sentence
text = "오늘 어머니하고 마트에서 가구 두 개를 봤어요. 침대는 비싸서 안 샀어요, 그런데 가방을 선반 위에 올리다가 떨어뜨려서 주웠어요."

# Speed is adjustable
speed = 1.0
device = 'cpu'  # or 'cuda' if available

print(f"Initializing Korean TTS model...")
model = TTS(language='KR', device=device)
speaker_ids = model.hps.data.spk2id

print(f"Available speakers: {list(speaker_ids.keys())}")
print(f"Using speaker: KR (ID: {speaker_ids['KR']})")
print(f"Text to synthesize: {text}")

output_path = 'korean_output.wav'
print(f"Generating speech...")
model.tts_to_file(text, speaker_ids['KR'], output_path, speed=speed)

print(f"✓ Successfully generated audio file: {output_path}")

