import io
import logging
from flask import Flask, request, send_file, jsonify
import subprocess
import os
import click
from tools import cint, ltc_encode
from timecode import Timecode

app = Flask(__name__)

# Configuración de logging
logging.basicConfig(level=logging.INFO)

# Carpeta para archivos temporales generados
TEMP_FOLDER = "temp"
os.makedirs(TEMP_FOLDER, exist_ok=True)

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
    header += cint(rate * bits * channels / 8, 4)
    header += cint(bits * channels / 8, 2)
    header += cint(bits, 2)
    header += b'data'
    header += cint(data_length, 4)
    return header

def make_ltc_wave(fps, start, duration, rate, bits, output):
    fps = float(fps)
    duration = float(duration)
    fmt = 'pcm_u8'

    on_val = 255
    off_val = 0
    if bits == 16:
        fmt = 'pcm_s16le'
        on_val = 32767
        off_val = -32768
    elif bits == 32 or bits == 64:
        if bits == 32:
            fmt = 'pcm_f32le'
        else:
            fmt = 'pcm_f64le'
        on_val = 1.0
        off_val = 0.0

    total_samples = int(rate * duration)
    bytes_per_sample = bits // 8
    total_bytes = total_samples * bytes_per_sample

    tc = Timecode(fps, start)
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
            if next_is_up:
                double_pulse_data += '11'
            else:
                double_pulse_data += '00'
            next_is_up = not next_is_up
        else:
            double_pulse_data += '10' if next_is_up else '01'

    data = MyByteArray(total_bytes)
    for sample_num in range(total_samples):
        ratio = sample_num / total_samples
        double_pulse_position = len(double_pulse_data) * ratio
        dpp_intpart = int(double_pulse_position)
        this_val = int(double_pulse_data[dpp_intpart])

        sample = on_val if this_val == 1 else off_val

        sample_bytes = sample.to_bytes(bytes_per_sample, 'little', signed=bits > 8)
        for byte in sample_bytes:
            data.add(byte)


    write_wave_file(output, data.buffer, rate=rate, bits=bits)

@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generador LTC</title>
    <style>
        :root {
            --color-primary: #FF5001;
            --color-primary-hover: #FF6B2B;
            --color-bg: #121212;
            --color-surface: #1E1E1E;
            --color-text: #FFFFFF;
            --color-text-secondary: #A0A0A0;
            --color-error: #FF453A;
            --color-success: #32D74B;
            --spacing-unit: 1rem;
            --border-radius: 8px;
            --transition-speed: 0.2s;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: var(--color-bg);
            color: var(--color-text);
            line-height: 1.5;
            min-height: 100vh;
        }

        h1 {
            text-align: center;
            color: var(--color-primary);
            margin-top: calc(var(--spacing-unit) * 2);
        }

        form {
            max-width: 400px;
            margin: var(--spacing-unit) auto;
            padding: var(--spacing-unit);
            background-color: var(--color-surface);
            border-radius: var(--border-radius);
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.3);
        }

        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: var(--color-primary);
        }

        input, select, button {
            width: 100%;
            padding: 0.75rem;
            margin-bottom: var(--spacing-unit);
            border: 1px solid var(--color-text-secondary);
            border-radius: var(--border-radius);
            background-color: var(--color-bg);
            color: var(--color-text);
            font-size: 1rem;
        }

        input:focus, select:focus {
            outline: none;
            border-color: var(--color-primary);
            box-shadow: 0 0 0 2px var(--color-primary-hover);
        }

        button {
            background-color: var(--color-primary);
            color: var(--color-text);
            border: none;
            font-size: 1rem;
            cursor: pointer;
            transition: background-color var(--transition-speed);
        }

        button:hover {
            background-color: var(--color-primary-hover);
        }

        #status {
            text-align: center;
            font-weight: bold;
            margin-top: var(--spacing-unit);
            color: var(--color-success);
        }
    </style>
</head>
<body>
    <h1>Generador LTC</h1>
    <form id="ltcForm">
        <label for="frameRate">Frame Rate:</label>
        <select id="frameRate">
            <option value="24">24</option>
            <option value="25">25</option>
            <option value="23.976">23.976</option>
            <option value="29.97">29.97</option>
            <option value="30">30</option>
        </select>

        <label for="sampleRate">Sample Rate:</label>
        <select id="sampleRate">
            <option value="44100">44100 Hz</option>
            <option value="48000">48000 Hz</option>
        </select>

        <label for="bitDepth">Bit Depth:</label>
        <select id="bitDepth">
            <option value="8">8-bit</option>
            <option value="16">16-bit</option>
        </select>

        <label for="duration">Duración (minutos, máx 30):</label>
        <input type="number" id="duration" min="1" max="30" value="1">

        <label for="startTime">Start Timecode (HH:MM:SS:FF):</label>
        <input type="text" id="startTime" value="00:00:00:00">

        <button type="submit">Generar LTC</button>
    </form>
    <div id="status"></div>

    <script>
        document.getElementById('ltcForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const status = document.getElementById('status');
            status.textContent = 'Generando...';

            const data = {
                frameRate: document.getElementById('frameRate').value,
                sampleRate: document.getElementById('sampleRate').value,
                bitDepth: document.getElementById('bitDepth').value,
                duration: document.getElementById('duration').value,
                startTime: document.getElementById('startTime').value
            };

            if (!data.frameRate || !data.sampleRate || !data.bitDepth || !data.duration || !data.startTime) {
                status.textContent = 'Error: Todos los campos son obligatorios.';
                return;
            }

            try {
                const response = await fetch('/generate_ltc', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'ltc_generated.wav';
                    a.click();
                    status.textContent = '¡Archivo LTC generado correctamente!';
                    window.URL.revokeObjectURL(url);
                } else {
                    const errorData = await response.json();
                    status.textContent = 'Error: ' + errorData.error;
                }
            } catch (error) {
                status.textContent = 'Error al enviar la solicitud: ' + error.message;
            }
        });
    </script>
</body>
</html>

    '''

@app.route('/generate_ltc', methods=['POST'])
def generate_ltc():
    try:
        data = request.get_json()
        frame_rate = str(data.get('frameRate'))
        sample_rate = str(data.get('sampleRate'))
        bit_depth = str(data.get('bitDepth'))
        duration = str(float(data.get('duration')) * 60)
        start_time = data.get('startTime')

        if not all([frame_rate, sample_rate, bit_depth, duration, start_time]):
            raise ValueError("Parámetros incompletos o nulos.")

        output_file = os.path.join(TEMP_FOLDER, "ltc_generated.wav")

        make_ltc_wave(frame_rate, start_time, duration, int(sample_rate), int(bit_depth), output_file)

        if not os.path.exists(output_file):
            raise FileNotFoundError("El archivo generado no se encuentra en la ruta esperada.")

        return send_file(output_file, mimetype='audio/wav', as_attachment=True)

    except subprocess.CalledProcessError as e:
        logging.error(f"Error al ejecutar generate_ltc.py: {e}")
        return jsonify({'error': 'Error al generar el archivo LTC.'}), 500
    except ValueError as ve:
        logging.error(f"Parámetro inválido: {str(ve)}")
        return jsonify({'error': f'Parámetro inválido: {str(ve)}'}), 400
    except FileNotFoundError as fnfe:
        logging.error(str(fnfe))
        return jsonify({'error': str(fnfe)}), 500
    except Exception as e:
        logging.error(f"Error inesperado: {str(e)}")
        return jsonify({'error': f'Error inesperado: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
