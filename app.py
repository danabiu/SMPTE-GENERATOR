#!/usr/bin/env python3
from flask import Flask, request, send_file, jsonify
from tools import cint, ltc_encode
from timecode import Timecode
import numpy as np
from scipy.io import wavfile
import io

app = Flask(__name__)

class MyByteArray:
    def __init__(self, size):
        self.buffer = bytearray(size)
        self.cursor = 0

    def add(self, byte):
        self.buffer[self.cursor] = byte
        self.cursor += 1

def write_wave_file(file_name, data, rate=48000, bits=8):
    header = gen_wave_header(data, rate=rate, bits=bits)
    with open(file_name, 'wb') as f:
        f.write(header)
        f.write(data)

def gen_wave_header(data, rate=48000, bits=8, channels=1):
    header_length = 44  # fixed header length
    data_length = len(data)
    file_length = header_length + data_length
    header = b'RIFF'                              # ascii RIFF
    header += cint(file_length, 4)                # file size data
    header += b'WAVE'                             # ascii WAVE
    header += b'fmt '                             # includes trailing space
    header += cint(16, 4)                         # length of format data (16)
    header += cint(1, 2)                          # type of format (1 is PCM)
    header += cint(channels, 2)                   # number of channels
    header += cint(rate, 4)                       # sample rate
    header += cint(rate * bits * channels / 8, 4) # byte rate
    header += cint(bits * channels / 8, 2)        # block align
    header += cint(bits, 2)                       # bits per sample
    header += b'data'                             # marks the beginning of the data section
    header += cint(data_length, 4)                # size of the data section
    return header

@app.route('/generate_ltc', methods=['POST'])
def generate_ltc():
    data = request.json
    fps = float(data['frameRate'])
    start_time = data['startTime']
    duration = int(data['duration']) * 60  # Convert to seconds
    rate = int(data['sampleRate'])
    bits = int(data['bitDepth'])

    on_val = 255 if bits == 8 else 32767
    off_val = 0 if bits == 8 else -32768

    total_samples = int(rate * duration)
    bytes_per_sample = bits // 8
    total_bytes = total_samples * bytes_per_sample

    tc = Timecode(fps, start_time)
    tc_encoded = []
    for i in range(int(duration * fps) + 1):
        e = ltc_encode(tc, as_string=True)
        tc_encoded.append(e)
        tc.next()
    
    tc_encoded = ''.join(tc_encoded)

    double_pulse_data = ''
    next_is_up = True
    for byte_char in tc_encoded:
        if byte_char == '0':
            double_pulse_data += '11' if next_is_up else '00'
            next_is_up = not next_is_up
        else:
            double_pulse_data += '10' if next_is_up else '01'

    data = MyByteArray(total_bytes)
    for sample_num in range(total_samples):
        ratio = sample_num / total_samples
        dpp_intpart = int(len(double_pulse_data) * ratio)
        this_val = int(double_pulse_data[dpp_intpart])

        sample = on_val if this_val == 1 else off_val
        sample_bytes = sample.to_bytes(bytes_per_sample, 'little', signed=bits > 8)
        for byte in sample_bytes:
            data.add(byte)

    wave_file_name = 'ltc_generated.wav'
    write_wave_file(wave_file_name, data.buffer, rate=rate, bits=bits)

    byte_io = io.BytesIO()
    byte_io.write(data.buffer)
    byte_io.seek(0)

    return send_file(byte_io, as_attachment=True, download_name=wave_file_name, mimetype='audio/wav')

if __name__ == '__main__':
    app.run(debug=True)
