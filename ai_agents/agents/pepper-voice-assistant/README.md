# Pepper Voice Assistant

A complete voice assistant integrated with the Pepper robot (from [Softbank Robotics](https://www.softbank.jp/en/robot/)).
This voice assistant includes real-time conversation capabilities using Agora RTC, OpenAI ASR, OpenAI LLM, and ElevenLabs TTS.

## Features

- **Chained Model Real-time Voice Interaction**: Complete voice conversation pipeline with STT → LLM → TTS processing
- **Turn Taking**: Capability to switch between conversation partners based on context using pre-existing solutions (This could be e.g. using Ten Turn Detection or other solutions).
- **Backchannel Generation**: Producing backchannels based on context. Deciding when and what kind of backchannel should be produced (using different methods: MaAI and rule-based)

## Prerequisites

### Required Environment Variables

1. **Agora Account**: Get credentials from [Agora Console](https://console.agora.io/)
   - `AGORA_APP_ID` - Your Agora App ID (required)

2. **OpenAI Account**: Get credentials from [OpenAI Platform](https://platform.openai.com/)
   - `OPENAI_API_KEY` - Your OpenAI API key (required)

3. **ElevenLabs Account**: Get credentials from [ElevenLabs](https://elevenlabs.io/)
   - `ELEVENLABS_TTS_KEY` - Your ElevenLabs API key (required)

### Optional Environment Variables

- `AGORA_APP_CERTIFICATE` - Agora App Certificate (optional)
- `OPENAI_MODEL` - OpenAI model name (optional, defaults to configured model)
- `OPENAI_PROXY_URL` - Proxy URL for OpenAI API (optional)

## Setup

### 1. Set Environment Variables

Add to your `.env` file:

```bash
# Agora (required for audio streaming)
AGORA_APP_ID=your_agora_app_id_here
AGORA_APP_CERTIFICATE=your_agora_certificate_here

# OpenAI (required for language model)
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4
OPENAI_PROXY_URL=your_proxy_url_here

# ElevenLabs (required for text-to-speech)
ELEVENLABS_TTS_KEY=your_elevenlabs_api_key_here
```

### 2. Run docker container

Run the docker container with the modules to run the full framework.

```bash
cd ai_agents
docker compose up -d
docker exec -it ten_agent_dev bash
```

### 3. Install Dependencies

```bash
cd agents/pepper-voice-assistant
task install
```

This installs Python dependencies and frontend components.
Look at [Common Problems](#common-problems) if you're having problems with the installation.

### 4. Run the Voice Assistant

```bash
task run
```

The voice assistant starts with all capabilities enabled.

### 4. Access the Application

- **Frontend**: http://localhost:3000
- **API Server**: http://localhost:8080
- **TMAN Designer**: http://localhost:49483

## Configuration

The voice assistant is configured in `tenapp/property.json`:

```json
{
  "ten": {
    "predefined_graphs": [
      {
        "name": "voice_assistant",
        "auto_start": true,
        "graph": {
          "nodes": [
            {
              "type": "extension",
              "name": "agora_rtc",
              "addon": "agora_rtc",
              "extension_group": "default",
              "property": {
                "app_id": "${env:AGORA_APP_ID}",
                "app_certificate": "${env:AGORA_APP_CERTIFICATE|}",
                "channel": "ten_agent_test",
                "stream_id": 1234,
                "remote_stream_id": 123,
                "subscribe_audio": true,
                "publish_audio": true,
                "publish_data": true,
                "enable_agora_asr": false
              }
            },
            {
              "type": "extension",
              "name": "stt",
              "addon": "openai_asr_python",
              "extension_group": "stt",
              "property": {
                "params": {
                  "api_key": "${env:OPENAI_API_KEY}"
                }
              }
            },
            {
              "type": "extension",
              "name": "llm",
              "addon": "openai_llm2_python",
              "extension_group": "chatgpt",
              "property": {
                "base_url": "https://api.openai.com/v1",
                "api_key": "${env:OPENAI_API_KEY}",
                "frequency_penalty": 0.9,
                "model": "${env:OPENAI_MODEL}",
                "max_tokens": 512,
                "prompt": "",
                "proxy_url": "${env:OPENAI_PROXY_URL|}",
                "greeting": "Hi there, how is your day going?",
                "max_memory_length": 10
              }
            },
            {
              "type": "extension",
              "name": "tts",
              "addon": "elevenlabs_tts2_python",
              "extension_group": "tts",
              "property": {
                "dump": false,
                "dump_path": "./",
                "params": {
                  "key": "${env:ELEVENLABS_TTS_KEY}",
                  "model_id": "eleven_multilingual_v2",
                  "voice_id": "${env:ELEVENLABS_VOICE_ID|13xVmcINNP7cvNio2oxh}",
                  "output_format": "pcm_16000"
                }
              }
            }
          ]
        }
      }
    ]
  }
}
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `AGORA_APP_ID` | string | - | Your Agora App ID (required) |
| `AGORA_APP_CERTIFICATE` | string | - | Your Agora App Certificate (optional) |
| `OPENAI_API_KEY` | string | - | OpenAI API key (required) |
| `OPENAI_MODEL` | string | gpt-4o | OpenAI model name (optional) |
| `OPENAI_PROXY_URL` | string | - | Proxy URL for OpenAI API (optional) |
| `ELEVENLABS_TTS_KEY` | string | - | ElevenLabs API key (required) |


## Customization

The voice assistant uses a modular design that allows you to easily replace STT, LLM, or TTS modules with other providers using TMAN Designer.

Access the visual designer at http://localhost:49483 to customize your voice agent. For detailed usage instructions, see the [TMAN Designer documentation](https://theten.ai/docs/ten_agent/customize_agent/tman-designer).

## Release as Docker image

**Note**: The following commands need to be executed outside of any Docker container.

### Build image

```bash
cd ai_agents
docker build -f agents/pepper-voice-assistant/Dockerfile -t pepper-voice-assistant-app .
```

### Run

```bash
docker run --rm -it --env-file .env -p 8080:8080 -p 3000:3000 pepper-voice-assistant-app
```

### Access

- Frontend: http://localhost:3000
- API Server: http://localhost:8080

## Learn More

- [Agora RTC Documentation](https://docs.agora.io/en/rtc/overview/product-overview)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [ElevenLabs API Documentation](https://docs.elevenlabs.io/)
- [TEN Framework Documentation](https://doc.theten.ai)

## COMMON PROBLEMS

1. **Installing MaAI fails**
<br>
MaAI needs PyAudio to be able to run, which runs on portaudio. This specific package needs to be installed separately, which can be done using the following command:
```
sudo apt-get portaudio19-dev
```
If this doesn't work, you should probably first update apt-get, which can be done using this command:
```
sudo apt-get update
```
