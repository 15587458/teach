"""Генерация озвучки через локальный RHVoice: build/voice/NN.wav (44.1 kHz mono)."""
import os
import subprocess
import sys

from script import LINES, VOICES

OUT = os.path.join(os.path.dirname(__file__), "build", "voice")


def main():
    os.makedirs(OUT, exist_ok=True)
    for i, ln in enumerate(LINES):
        v = VOICES[ln["speaker"]]
        raw = os.path.join(OUT, f"{i:02d}_raw.wav")
        dst = os.path.join(OUT, f"{i:02d}.wav")
        subprocess.run(
            ["RHVoice-test", "-p", v["voice"], "-r", str(v["rate"]), "-t", str(v["pitch"]), "-o", raw],
            input=ln["tts"].encode(), check=True)
        # чистка: срезать тишину по краям, лёгкая компрессия и «тёплый» эквалайзер
        af = ("silenceremove=start_periods=1:start_threshold=-45dB,"
              "areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
              "highpass=f=70,equalizer=f=200:t=q:w=1:g=2,equalizer=f=4000:t=q:w=1.5:g=2.5,"
              "acompressor=threshold=-18dB:ratio=3:attack=5:release=80,loudnorm=I=-15:TP=-1.5")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", af,
                        "-ar", "44100", "-ac", "1", dst], check=True)
        os.remove(raw)
        sys.stdout.write(f"{i:02d} {ln['speaker']:5s} ok\n")


if __name__ == "__main__":
    main()
