# Lola

Lola is an audio-visual interactive installation that transcribes English speech and uses spoken words as the main input for generating musical sequences and visual patterns.

The project is an experimental work that uses ideas from psycholinguistics, music theory, and music psychology to transform live speech into rhythmic note sequences, and visual trails.

## Installation

Preferably using **Python 3.13**, create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```
Install the required dependencies:
```bash
pip install -r requirements.txt
```

Then run the application:

```bash
python serve.py
```


By default, it listens to the microphone, transcribes English speech, generates rhythmic note sequences, plays them locally with the built-in simple sine synthesizer, and sends OSC messages to the visual system.

## MIDI / OSC Output Mode

It can also run in MIDI/OSC-only mode. In this mode, local audio playback is disabled and the generated notes are sent over OSC instead.

    python serve.py --midi-out-only

The default MIDI-style OSC target is:

    127.0.0.1:9001/midi

The OSC message format is:

    /midi voice note velocity duration

Example:

    /midi 1 69 100 0.225

Where:

    voice     = rhythm voice number, starting from 1
    note      = MIDI note number, 0-127
    velocity  = MIDI-style velocity, 1-127
    duration  = note duration in seconds

You can customise the OSC target:

    python serve.py --midi-out-only --midi-osc-host 127.0.0.1 --midi-osc-port 9001 

## Control Panel

`serve.py` starts a local HTTP server on port 8000.

Open the control panel at:
```
http://127.0.0.1:8000/
```

The control panel is intended to update audio and visual parameters through a REST endpoint. This is currently mocked in the frontend and still under development.

## Future Tasks
* Implement the backend parameter update endpoint.
* Connect the control panel to live audio parameters.
* Connect the control panel to live visual parameters.
* Add support for switching between OSC-only output and local synthesis.
* Improve presets for different installation modes and performance contexts.
