import os
import io
from flask import Flask, request, send_file, jsonify
import logging
from tools import cint, ltc_encode
from timecode import Timecode

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)

class MyByteArray:
    def __init__(self, size):
        self.buffer = bytearray(size)
        self.cursor = 0

    def add(self, byte):
        self.buffer[self.cursor] = byte
        self.cursor += 1

def write_wave_file(data, rate=48000, bits=8):
    header = gen_wave_header(data, rate=rate, bits=bits)
    return header + data

def gen_wave_header(data, rate=48000, bits=8, channels=1):
    header_length = 4+4+4+4+4+2+2+4+4+2+2+4+4
    data_length = len(data)
    file_length = header_length + data_length
    header = b''
    header += b'RIFF'
    header += cint(file_length, 4)
    header += b'WAVE'
    header += b'fmt '
    header += cint(16, 4)
    header += cint(1, 2)
    header += cint(channels, 2)
    header += cint(rate, 4)
    header += cint(rate * bits * channels // 8, 4)
    header += cint(bits * channels // 8, 2)
    header += cint(bits, 2)
    header += b'data'
    header += cint(data_length, 4)
    return header

def make_ltc_wave(fps, start, duration, rate, bits):
    fps = float(fps)
    duration = float(duration)

    on_val = 255
    off_val = 0
    if bits == 16:
        on_val = 32767  # Valor máximo para 16 bits
        off_val = -32768  # Valor mínimo para 16 bits
    elif bits == 8:
        on_val = 255  # Valor máximo para 8 bits
        off_val = 0  # Valor mínimo para 8 bits
    elif bits == 32:
        on_val = 1.0  # Máximo para flotantes
        off_val = 0.0

    total_samples = int(rate * duration)
    bytes_per_sample = bits // 8
    total_bytes = total_samples * bytes_per_sample

    # Generación de la codificación LTC (ya tienes este código)
    tc = Timecode(fps, start)
    tc_encoded = [ltc_encode(tc, as_string=True) for _ in range(int(duration * fps) + 1)]
    tc_encoded = ''.join(tc_encoded)

    double_pulse_data = ''
    next_is_up = True
    for byte_char in tc_encoded:
        if byte_char == '0':
            double_pulse_data += '11' if next_is_up else '00'
            next_is_up = not next_is_up
        else:
            double_pulse_data += '10' if next_is_up else '01'

    # Creación del buffer de datos de audio
    data = MyByteArray(total_bytes)
    for sample_num in range(total_samples):
        ratio = sample_num / total_samples
        double_pulse_position = len(double_pulse_data) * ratio
        dpp_intpart = int(double_pulse_position)
        this_val = int(double_pulse_data[dpp_intpart])

        sample = on_val if this_val == 1 else off_val

        # RIFF wav usa little-endian
        sample_bytes = sample.to_bytes(bytes_per_sample, 'little', signed=bits > 8)
        for byte in sample_bytes:
            data.add(byte)

    wav_data = write_wave_file(data.buffer, rate=rate, bits=bits)
    return wav_data


@app.route('/generate_ltc', methods=['POST'])
def generate_ltc():
    try:
        data = request.get_json()

        frame_rate = float(data.get('frameRate', 30))
        sample_rate = int(data.get('sampleRate', 44100))
        bit_depth = int(data.get('bitDepth', 16))
        duration = int(data.get('duration', 10)) * 60  # Convertir minutos a segundos
        start_time = data.get('startTime', '00:01:00:00')

        logging.info(f"Generating LTC with Frame Rate: {frame_rate}, Sample Rate: {sample_rate}, "
                     f"Bit Depth: {bit_depth}, Duration: {duration} seconds, Start Time: {start_time}")

        # Generar archivo LTC .wav en memoria
        wav_data = make_ltc_wave(frame_rate, start_time, duration, sample_rate, bit_depth)

        # Devolver el archivo generado como descarga .wav
        return send_file(
            io.BytesIO(wav_data),
            mimetype='audio/wav',
            as_attachment=True,
            download_name='ltc_generated.wav'
        )

    except Exception as e:
        logging.error(f"Error during LTC generation: {str(e)}")
        return jsonify({'error': 'Failed to generate LTC. Please check input parameters.'}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
