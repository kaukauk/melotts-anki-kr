#!/usr/bin/env python3
"""
Test script for Korean TTS using MeloTTS - OFFLINE VERSION
Uses local model files instead of downloading from HuggingFace
"""
from melo.api import TTS
import os

# Korean example sentence
text = "안녕하세요! 오늘은 날씨가 정말 좋네요."

# Speed is adjustable
speed = 1.0
device = 'cpu'  # or 'cuda' if available

# Paths to local model files
# Option 1: Use the MeloTTS-Korean folder
korean_model_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'MeloTTS-Korean')
config_path = os.path.join(korean_model_dir, 'config.json')
ckpt_path = os.path.join(korean_model_dir, 'checkpoint.pth')

print(f"Initializing Korean TTS model (OFFLINE MODE)...")
print(f"Using config: {config_path}")
print(f"Using checkpoint: {ckpt_path}")

# Initialize with local paths
model = TTS(
    language='KR', 
    device=device,
    config_path=config_path,
    ckpt_path=ckpt_path,
    use_hf=False  # Disable HuggingFace downloads
)

speaker_ids = model.hps.data.spk2id

print(f"Available speakers: {list(speaker_ids.keys())}")
print(f"Using speaker: KR (ID: {speaker_ids['KR']})")
print(f"Text to synthesize: {text}")

output_path = 'korean_output_offline.wav'
print(f"Generating speech...")
model.tts_to_file(text, speaker_ids['KR'], output_path, speed=speed)

print(f"✓ Successfully generated audio file: {output_path}")

