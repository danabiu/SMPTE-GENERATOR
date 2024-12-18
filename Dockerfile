# Base Image
FROM python:3.9-slim

# Configuración de la carpeta de trabajo
WORKDIR /app

# Copiar los archivos necesarios
COPY . /app

# Instalar dependencias
RUN pip install --no-cache-dir flask timecode

# Crear carpeta temporal
RUN mkdir temp

# Exponer el puerto que usa Flask
EXPOSE 5000

# Comando para ejecutar la aplicación
CMD ["python", "app.py"]
