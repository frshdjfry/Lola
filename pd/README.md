# granular26

granular26 is a granular synthesiser based on jaffasplaffa's [granular21](https://github.com/jaffasplaffa/Pure-data-patches/tree/master) patch.

## How to use

Open `main.pd` in Pure Data.
This has four copies of the granular26 synth, each of which corresponds
to a voice.
Messages received over OSC are distributed to the four synth copies.

*In order to get sound*, you must:
1. Create a directory `samples` under the `granular26` directory.
2. Fill it with up to 12 samples called `sample1.wav`, `sample2.wav`, ...,
`sample12.wav`.
The samples must be mono PCM in the WAV format, and, importantly, the sample
rate must be the same as the sample rate in your Pure Data settings
(commonly 48kHz).
3. Select a sample at the top of each synth you wish to use.
A representation of the sample as a waveform should appear at the left.
4. Tune the sample(s) by selecting the correct octave and note.
5. Adjust the amplitude levels in the top left of the main patch.
6. Send OSC messages in the format detailed in the main README.
If you have done all the above, you should hear sound from the synthesisers.
