import socket
import threading
import os
import time

# Konfigurasi Server
PROXY_HOST = '0.0.0.0'
PROXY_PORT = 8080  # Wajib port 8080 sesuai ketentuan 
WEB_SERVER_HOST = '127.0.0.1' # Ganti dengan IP Web Server (Laptop A) jika beda perangkat
WEB_SERVER_PORT = 8000
CACHE_DIR = './cache'

# Bikin folder cache lokal kalau belum ada
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def handle_client(client_socket, client_address):
    """
    Fungsi worker thread untuk menangani request dari masing-masing client. [cite: 354, 355]
    """
    start_time = time.time()
    try:
        # 1. Terima request dari client
        request = client_socket.recv(4096).decode('utf-8')
        if not request:
            client_socket.close()
            return

        # 2. Parse URL dari baris pertama HTTP request (Contoh: GET /index.html HTTP/1.1)
        first_line = request.split('\n')[0]
        url = first_line.split(' ')[1]
        
        # Bersihkan nama file untuk cache (hapus slash di depan)
        filename = url.lstrip('/')
        if filename == '':
            filename = 'index.html'
        
        cache_path = os.path.join(CACHE_DIR, filename)

        # 3. Cek apakah file sudah ada di Cache Lokal
        if os.path.exists(cache_path):
            # ==========================================
            # SKENARIO CACHE HIT 
            # ==========================================
            with open(cache_path, 'rb') as f:
                response_data = f.read()
            
            client_socket.sendall(response_data)
            
            # Catat log sesuai ketentuan: IP client, URL, status cache, dan waktu respons 
            elapsed_time = (time.time() - start_time) * 1000
            print(f"[LOG] {client_address[0]} | URL: {url} | Status: CACHE HIT | Time: {elapsed_time:.2f}ms")

        else:
            # ==========================================
            # SKENARIO CACHE MISS 
            # ==========================================
            # Forward request ke Web Server
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                server_socket.connect((WEB_SERVER_HOST, WEB_SERVER_PORT))
                server_socket.sendall(request.encode('utf-8'))
                
                # Terima response dari Web Server
                response_data = b""
                while True:
                    data = server_socket.recv(4096)
                    if not data:
                        break
                    response_data += data
                
                server_socket.close()

                # Simpan response ke Cache Lokal
                if response_data:
                    with open(cache_path, 'wb') as f:
                        f.write(response_data)
                
                # Kirim balik ke Client
                client_socket.sendall(response_data)

                elapsed_time = (time.time() - start_time) * 1000
                print(f"[LOG] {client_address[0]} | URL: {url} | Status: CACHE MISS | Time: {elapsed_time:.2f}ms")

            except ConnectionRefusedError:
                error_msg = "HTTP/1.1 502 Bad Gateway\r\n\r\nServer Web Mati atau Tidak Terjangkau."
                client_socket.sendall(error_msg.encode('utf-8'))
                print(f"[ERROR] {client_address[0]} | URL: {url} | 502 Bad Gateway")
            finally:
                server_socket.close()

    except Exception as e:
        print(f"Error handling client {client_address}: {e}")
    finally:
        client_socket.close()

def start_proxy():
    # Menggunakan SOCK_STREAM untuk TCP 
    proxy_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    proxy_server.bind((PROXY_HOST, PROXY_PORT))
    proxy_server.listen(10)
    
    print(f"[*] Proxy Server berjalan di port {PROXY_PORT}...")
    print("[*] Menunggu koneksi dari client...\n")

    while True:
        # Loop utama untuk menerima koneksi [cite: 354]
        client_socket, client_address = proxy_server.accept()
        
        # Tiap ada client baru, spawn thread baru [cite: 337, 348]
        client_thread = threading.Thread(
            target=handle_client, 
            args=(client_socket, client_address)
        )
        client_thread.daemon = True
        client_thread.start()

if __name__ == '__main__':
    start_proxy()