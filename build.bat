@echo off
REM Build cục bộ trên Windows (cần ffmpeg.exe đặt cạnh file này)
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --windowed --name VideoTranslator --collect-all customtkinter --collect-all sherpa_onnx main.py
copy /Y ffmpeg.exe dist\VideoTranslator\ffmpeg.exe
