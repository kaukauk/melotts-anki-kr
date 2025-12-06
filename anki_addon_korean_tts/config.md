# Korean TTS Configuration

## Server Settings

- **server_url**: URL of the remote MeloTTS server (e.g., `http://tts-server.your-tailnet.ts.net:8000`)
- **remote_enabled**: Enable or disable remote TTS generation
- **api_key**: Optional API key for server authentication (leave empty if not needed)

## Network Settings

- **connect_timeout_secs**: Connection timeout in seconds (default: 3.0)
- **read_timeout_secs**: Read timeout in seconds for long TTS generation (default: 60.0)

## Performance Settings

- **remote_batch_size**: Number of items to send per batch request to the server (default: 16)
- **tts_speed**: Numeric TTS speed multiplier for remote calls (0.1–2.0, where 1.0 is normal speed)

## Advanced Settings

- **melotts_extra_path**: Optional additional path to search for MeloTTS library (leave empty unless you have a custom installation)


