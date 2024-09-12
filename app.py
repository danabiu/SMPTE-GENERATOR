from flask import Flask, request, send_file, jsonify
import numpy as np
from scipy.io import wavfile
import io

app = Flask(__name__)

@app.route('/generate_ltc', methods=['POST'])
def generate_ltc():
    data = request.json
    frame_rate = float(data['frameRate'])
    sample_rate = int(data['sampleRate'])
    bit_depth = int(data['bitDepth'])
    duration = int(data['duration']) * 60  # Convertir a segundos
    start_time = data['startTime']  # No lo usamos en este ejemplo

    # Lógica para generar LTC (similar al ejemplo anterior)
    frequency = 2400
    bit_frequency = 9600

    def generate_ltc_bit(bit):
        t = np.linspace(0, 1 / bit_frequency, int(sample_rate / bit_frequency), endpoint=False)
        if bit == 1:
            return np.sin(2 * np.pi * frequency * t)
        else:
            return np.zeros_like(t)

    def generate_ltc_frame(timecode):
        frame = []
        for bit in timecode:
            frame.append(generate_ltc_bit(bit))
        return np.concatenate(frame)

    def generate_timecode(frame_number):
        return [int(x) for x in format(frame_number % 256, '08b')]

    samples = []
    for frame_number in range(int(frame_rate * duration)):
        timecode = generate_timecode(frame_number)
        samples.append(generate_ltc_frame(timecode))

    signal = np.concatenate(samples)
    signal = signal / np.max(np.abs(signal))

    byte_io = io.BytesIO()
    wavfile.write(byte_io, sample_rate, signal.astype(np.float32))
    byte_io.seek(0)

    return send_file(byte_io, as_attachment=True, download_name='ltc.wav', mimetype='audio/wav')

if __name__ == '__main__':
    app.run(debug=True)
