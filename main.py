import webview
import app as flask_app
import threading
import sys
import os
import time

def run_flask():
    flask_app.app.run(host='127.0.0.1', port=5000)

def load_main_window():
    time.sleep(3)
    if splash_window:
        splash_window.destroy()
    webview.create_window(
        'Minty Project APP',
        'http://127.0.0.1:5000',
        width=1280,
        height=720,
        resizable=True,
        min_size=(1024, 600)
    )

if __name__ == '__main__':
    flask_app.init_db()
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    if getattr(sys, 'frozen', False):
        splash_path = os.path.join(..., 'splash_base64.html')
    else:
        splash_path = os.path.join(..., 'splash_base64.html')

    splash_window = webview.create_window(
        'Memuat Aplikasi...', 
        splash_path, 
        width=450, 
        height=350, 
        frameless=True,
        on_top=True   
    )
    
    webview.start(load_main_window)
