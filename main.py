import os
import io
import wave
import json
import numpy
import requests

from vosk import Model, KaldiRecognizer
from flask import Flask, jsonify, request
from scipy.signal import welch

# Tested on vosk-model-small-en-us-0.15 (https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip)
model_path = "vosk-model-small-en-us-0.15"
if not os.path.exists(model_path):
    raise FileNotFoundError("Model not found")

model = Model(model_path)

app = Flask(__name__)

@app.route("/asr", methods=["POST"])
def asr():
    global model

    bytes = io.BytesIO()
    # curl -X POST -F "file=@/home/ouki/foo.wav" http://127.0.0.1:5000/asr
    if request.files.__len__() > 0:
        bytes = request.files.get("file").stream
    # curl -X POST -H "Content-Type: text/plain" -d "url" https://127.0.0.1:5000/asr
    elif request.data.decode().strip().startswith("http"):
        bytes = io.BytesIO(requests.get(request.data).content)
    else:
        return jsonify({ "error": "Supported only file or url" })
    
    words = []
    with wave.open(bytes, 'rb') as wf:
        framerate = wf.getframerate()

        rec = KaldiRecognizer(model, framerate)
        rec.SetWords(True)

        audio_buffer = []

        while True:
            data = wf.readframes(4000)
            if data.__len__() == 0:
                break

            audio_buffer.append(numpy.frombuffer(data, dtype=numpy.int16))

            if rec.AcceptWaveform(data):
                words.append(json.loads(rec.Result()))
        
        words.append(json.loads(rec.FinalResult()))
        audio_buffer = numpy.concatenate(audio_buffer)

    result = []

    receiver_duration = 0
    transmitter_duration = 0

    for i in range(0, words.__len__()):
        res = words[i]

        if not "result" in res:
            continue

        duration = 0
        words_audio = []
        for word in res["result"]:
            start = word["start"]
            end = word["end"]

            duration += (start - end)
            words_audio = audio_buffer[int(start * framerate):int(end * framerate)]

        freq, power = welch(words_audio, framerate)
        arg_max = numpy.argmax(power)

        m_freq = numpy.mean(freq[arg_max])
        d_freq = freq[arg_max]

        result.append(json.dumps({
            "source": "receiver" if i % 2 == 0 else "transmitter",
            "text": res["text"],
            "duration": duration,
            "raised_voice": bool(m_freq > 300),
            "gender": "female" if d_freq < 300 else "male"
        }))

        if i % 2 == 0:
            receiver_duration += duration
        else:
            transmitter_duration += duration

    return jsonify({ 
        "dialog": result, 
        "result_duration": {
            "receiver": receiver_duration,
            "transmitter": transmitter_duration
        } 
    })

if __name__ == "__main__":
    app.run("127.0.0.1", 5000)