import socket
import threading
import os
import time

# =========================================================
# KONFIGURASI SERVER
# =========================================================
TCP_HOST = '0.0.0.0'
TCP_PORT = 8000       # HTTP Server

UDP_HOST = '0.0.0.0'
UDP_PORT = 9000       # UDP Echo Server

# Direktori tempat file HTML disimpan (sama dengan lokasi webserver.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BUFFER_SIZE = 4096


# =========================================================
# UTILITAS HTTP
# =========================================================
def get_content_type(filename):
    """
    Menentukan Content-Type berdasarkan ekstensi file.
    """
    ext = os.path.splitext(filename)[1].lower()
    content_types = {
        '.html': 'text/html; charset=utf-8',
        '.htm':  'text/html; charset=utf-8',
        '.css':  'text/css',
        '.js':   'application/javascript',
        '.png':  'image/png',
        '.jpg':  'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.ico':  'image/x-icon',
        '.txt':  'text/plain',
    }
    return content_types.get(ext, 'application/octet-stream')


def build_response(status_code, status_text, body_bytes, content_type='text/html; charset=utf-8'):
    """
    Membangun HTTP response dengan format HTTP/1.1 yang valid.
    Format:
        HTTP/1.1 <status_code> <status_text>\r\n
        Content-Type: <content_type>\r\n
        Content-Length: <size>\r\n
        Connection: close\r\n
        \r\n
        <body>
    """
    header = (
        f"HTTP/1.1 {status_code} {status_text}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    return header.encode('utf-8') + body_bytes


def build_404():
    body = b"<html><body><h1>404 Not Found</h1><p>File tidak ditemukan di server.</p></body></html>"
    return build_response(404, "Not Found", body)


def build_500():
    body = b"<html><body><h1>500 Internal Server Error</h1><p>Terjadi kesalahan pada server.</p></body></html>"
    return build_response(500, "Internal Server Error", body)


# =========================================================
# TCP: HANDLER PER CLIENT
# =========================================================
def handle_tcp_client(client_socket, client_address):
    """
    Worker thread untuk menangani satu koneksi TCP dari proxy.
    Menerima HTTP GET request, membaca file, mengirim HTTP response.
    """
    try:
        # Terima request dari proxy
        raw_request = b""
        client_socket.settimeout(5)

        while True:
            try:
                chunk = client_socket.recv(BUFFER_SIZE)
                if not chunk:
                    break
                raw_request += chunk
                # HTTP request diakhiri dengan double CRLF
                if b"\r\n\r\n" in raw_request:
                    break
            except socket.timeout:
                break

        if not raw_request:
            client_socket.close()
            return

        # Parse baris pertama: "GET /path HTTP/1.1"
        try:
            request_text = raw_request.decode('utf-8', errors='replace')
            first_line = request_text.split('\n')[0].strip()
            parts = first_line.split(' ')

            method = parts[0] if len(parts) > 0 else ''
            path   = parts[1] if len(parts) > 1 else '/'
        except Exception:
            client_socket.sendall(build_500())
            log(client_address[0], '?', 500, 'Gagal parse request')
            return

        # Normalkan path: "/" -> "/index.html"
        if path == '/':
            path = '/index.html'

        # Buang query string jika ada (misal /page.html?foo=bar)
        path = path.split('?')[0]

        # Bersihkan traversal path berbahaya (security basic)
        filename = os.path.normpath(path.lstrip('/'))
        file_path = os.path.join(BASE_DIR, filename)

        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

        # Hanya layani GET
        if method != 'GET':
            body = b"<html><body><h1>405 Method Not Allowed</h1></body></html>"
            response = build_response(405, "Method Not Allowed", body)
            client_socket.sendall(response)
            log(client_address[0], path, 405, timestamp)
            return

        # Cek file ada atau tidak
        if not os.path.isfile(file_path):
            client_socket.sendall(build_404())
            log(client_address[0], path, 404, timestamp)
            return

        # Baca dan kirim file
        try:
            with open(file_path, 'rb') as f:
                body_bytes = f.read()

            content_type = get_content_type(filename)
            response = build_response(200, "OK", body_bytes, content_type)
            client_socket.sendall(response)
            log(client_address[0], path, 200, timestamp)

        except Exception as e:
            client_socket.sendall(build_500())
            log(client_address[0], path, 500, f'Error baca file: {e}')

    except Exception as e:
        print(f"[ERROR] handle_tcp_client dari {client_address}: {e}")

    finally:
        client_socket.close()


def log(client_ip, path, status_code, info=''):
    """
    Mencatat log: IP client, jalur berkas, timestamp, dan status code.
    """
    print(f"[LOG] IP: {client_ip} | Path: {path} | Status: {status_code} | Info: {info}")


# =========================================================
# TCP: MAIN SERVER LOOP
# =========================================================
def start_tcp_server():
    """
    Server TCP yang berjalan di port 8000.
    Setiap koneksi masuk ditangani oleh thread terpisah (thread-per-connection).
    """
    tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_server.bind((TCP_HOST, TCP_PORT))
    tcp_server.listen(10)

    print(f"[*] TCP Web Server berjalan di port {TCP_PORT}...")

    while True:
        try:
            client_socket, client_address = tcp_server.accept()

            thread = threading.Thread(
                target=handle_tcp_client,
                args=(client_socket, client_address),
                daemon=True
            )
            thread.start()

        except Exception as e:
            print(f"[ERROR] TCP accept loop: {e}")


# =========================================================
# UDP: ECHO SERVER LOOP
# =========================================================
def start_udp_server():
    """
    UDP Echo Server yang berjalan di port 9000.
    Menerima paket dari client dan memantulkan (echo) payload persis apa adanya.
    Format payload yang diterima: "Ping <seq> <timestamp>"
    """
    udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_server.bind((UDP_HOST, UDP_PORT))

    print(f"[*] UDP Echo Server berjalan di port {UDP_PORT}...")

    while True:
        try:
            data, client_address = udp_server.recvfrom(BUFFER_SIZE)

            # Echo: kirim balik payload persis sama tanpa modifikasi
            udp_server.sendto(data, client_address)

            payload_text = data.decode('utf-8', errors='replace')
            print(f"[UDP] Echo ke {client_address[0]}:{client_address[1]} | Payload: '{payload_text}'")

        except Exception as e:
            print(f"[ERROR] UDP echo loop: {e}")


# =========================================================
# MAIN: JALANKAN TCP DAN UDP BERSAMAAN
# =========================================================
def main():
    print("=" * 50)
    print("  WEB SERVER - TUBES JARINGAN KOMPUTER")
    print("=" * 50)
    print(f"  Base directory : {BASE_DIR}")
    print(f"  TCP HTTP       : port {TCP_PORT}")
    print(f"  UDP Echo       : port {UDP_PORT}")
    print("=" * 50)
    print("\nPastikan file HTML diletakkan di direktori yang sama dengan webserver.py")
    print("Urutan jalankan: webserver.py -> proxy.py -> client.py\n")

    # Jalankan UDP server di thread terpisah (daemon)
    udp_thread = threading.Thread(target=start_udp_server, daemon=True)
    udp_thread.start()

    # TCP server jalan di main thread
    start_tcp_server()


if __name__ == '__main__':
    main()