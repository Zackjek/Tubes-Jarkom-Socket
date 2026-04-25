# client.py
# Nama: Muhammad Zaky Mubarok
# Peran: Client - HTTP Request via Proxy dan UDP QoS Pinger

import argparse
import math
import socket
import time


# =========================================================
# KONFIGURASI DEFAULT
# =========================================================
DEFAULT_PROXY_HOST = "127.0.0.1"   # Ganti dengan IP laptop proxy saat testing kelompok
DEFAULT_PROXY_PORT = 8080

DEFAULT_SERVER_HOST = "127.0.0.1"  # Ganti dengan IP laptop web server saat testing kelompok
DEFAULT_UDP_PORT = 9000

BUFFER_SIZE = 4096
TCP_TIMEOUT = 5
UDP_TIMEOUT = 1


# =========================================================
# UTILITAS HTTP
# =========================================================
def normalize_path(path):
    """
    Memastikan path HTTP selalu diawali dengan '/'.
    Contoh:
    index.html  -> /index.html
    /index.html -> /index.html
    """
    if not path:
        return "/index.html"

    if not path.startswith("/"):
        path = "/" + path

    return path


def build_http_get_request(path, host):
    """
    Membuat HTTP GET request secara manual.
    Request ini dikirim ke proxy, bukan langsung ke web server.
    """
    path = normalize_path(path)

    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"User-Agent: TUBES-JARKOM-CLIENT/1.0\r\n"
        f"Accept: text/html,*/*\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )

    return request


def receive_all(sock):
    """
    Menerima seluruh response dari socket TCP sampai koneksi ditutup
    atau timeout terjadi.
    """
    response = b""

    while True:
        try:
            data = sock.recv(BUFFER_SIZE)

            if not data:
                break

            response += data

        except socket.timeout:
            # Kalau sudah ada sebagian response, hentikan agar program tidak menggantung.
            if response:
                break
            raise

    return response


def split_http_response(response_bytes):
    """
    Memisahkan header HTTP dan body HTML.
    Jika format response tidak lengkap, tetap dikembalikan secara aman.
    """
    separator = b"\r\n\r\n"

    if separator in response_bytes:
        header_bytes, body_bytes = response_bytes.split(separator, 1)
    else:
        header_bytes = response_bytes
        body_bytes = b""

    header_text = header_bytes.decode("utf-8", errors="replace")
    body_text = body_bytes.decode("utf-8", errors="replace")

    return header_text, body_text


# =========================================================
# MODE 1: HTTP CLIENT VIA PROXY
# =========================================================
def http_get_via_proxy(proxy_host, proxy_port, server_host, path):
    """
    Mengirim HTTP GET request ke proxy menggunakan TCP.
    Client tidak melakukan HTTP request langsung ke web server.
    """
    path = normalize_path(path)
    request = build_http_get_request(path, server_host)

    client_socket = None

    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.settimeout(TCP_TIMEOUT)

        start_time = time.perf_counter()

        print("\n=== MODE TCP: HTTP GET VIA PROXY ===")
        print(f"Proxy tujuan    : {proxy_host}:{proxy_port}")
        print(f"Host header     : {server_host}")
        print(f"Path diminta    : {path}")
        print("-" * 50)

        client_socket.connect((proxy_host, proxy_port))
        client_socket.sendall(request.encode("utf-8"))

        response = receive_all(client_socket)

        end_time = time.perf_counter()
        response_time_ms = (end_time - start_time) * 1000

        header_text, body_text = split_http_response(response)

        print("\n=== HTTP HEADER ===")
        print(header_text if header_text else "(Header kosong)")

        print("\n=== ISI HALAMAN / BODY HTML ===")
        print(body_text if body_text else "(Body kosong atau response tidak memiliki body)")

        print("\n=== RINGKASAN TCP ===")
        print(f"Ukuran response : {len(response)} bytes")
        print(f"Waktu response  : {response_time_ms:.2f} ms")

        return {
            "success": True,
            "response_size": len(response),
            "response_time_ms": response_time_ms,
        }

    except socket.timeout:
        print("\nERROR: Koneksi ke proxy timeout.")
        return {"success": False, "error": "timeout"}

    except ConnectionRefusedError:
        print("\nERROR: Proxy belum berjalan atau port proxy salah.")
        print("Pastikan urutan menjalankan program: webserver.py -> proxy.py -> client.py")
        return {"success": False, "error": "connection refused"}

    except OSError as error:
        print(f"\nERROR OS/socket: {error}")
        return {"success": False, "error": str(error)}

    except Exception as error:
        print(f"\nERROR tidak terduga: {error}")
        return {"success": False, "error": str(error)}

    finally:
        if client_socket is not None:
            client_socket.close()


# =========================================================
# UTILITAS QOS UDP
# =========================================================
def calculate_average(values):
    if not values:
        return 0.0

    return sum(values) / len(values)


def calculate_jitter(rtt_list):
    """
    Menghitung jitter sebagai deviasi standar dari selisih RTT berturut-turut.

    Rumus sederhana:
    1. Hitung delta RTT: |RTT_i - RTT_(i-1)|
    2. Hitung rata-rata delta
    3. Hitung deviasi standar dari delta tersebut
    """
    if len(rtt_list) < 2:
        return 0.0

    rtt_differences = []

    for i in range(1, len(rtt_list)):
        difference = abs(rtt_list[i] - rtt_list[i - 1])
        rtt_differences.append(difference)

    mean_difference = calculate_average(rtt_differences)

    variance = 0.0
    for difference in rtt_differences:
        variance += (difference - mean_difference) ** 2

    variance = variance / len(rtt_differences)
    jitter = math.sqrt(variance)

    return jitter


def calculate_throughput_kbps(total_success_payload_bytes, duration_seconds):
    """
    Throughput dihitung dari total payload berhasil dibagi durasi pengujian.
    Satuan dikonversi ke kbps.
    """
    if duration_seconds <= 0:
        return 0.0

    total_bits = total_success_payload_bytes * 8
    throughput_kbps = total_bits / duration_seconds / 1000

    return throughput_kbps


# =========================================================
# MODE 2: UDP QOS PINGER
# =========================================================
def udp_qos_ping(server_host, udp_port, total_packet):
    """
    Mengirim paket UDP ke Web Server UDP Echo.
    Setiap paket berformat: Ping <seq> <timestamp>
    Menghasilkan statistik:
    - RTT min/avg/max
    - Packet loss
    - Jitter
    - Throughput
    """
    if total_packet < 10:
        print("Jumlah paket minimal untuk ketentuan tugas adalah 10. Nilai otomatis diubah menjadi 10.")
        total_packet = 10

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.settimeout(UDP_TIMEOUT)

    rtt_list = []
    lost_packet = 0
    success_payload_bytes = 0

    print("\n=== MODE UDP: QOS PINGER ===")
    print(f"Target UDP server : {server_host}:{udp_port}")
    print(f"Jumlah paket      : {total_packet}")
    print(f"Timeout/paket     : {UDP_TIMEOUT} detik")
    print("-" * 60)

    test_start_time = time.perf_counter()

    for seq in range(1, total_packet + 1):
        timestamp = time.time()
        payload = f"Ping {seq} {timestamp}"
        payload_bytes = payload.encode("utf-8")

        try:
            send_time = time.perf_counter()

            udp_socket.sendto(payload_bytes, (server_host, udp_port))
            data, address = udp_socket.recvfrom(BUFFER_SIZE)

            receive_time = time.perf_counter()

            rtt_ms = (receive_time - send_time) * 1000
            rtt_list.append(rtt_ms)
            success_payload_bytes += len(data)

            echoed_payload = data.decode("utf-8", errors="replace")

            print(
                f"Reply from {address[0]}:{address[1]} "
                f"seq={seq} RTT={rtt_ms:.2f} ms payload='{echoed_payload}'"
            )

        except socket.timeout:
            lost_packet += 1
            print(f"Request timed out: seq={seq}")

        except OSError as error:
            lost_packet += 1
            print(f"ERROR socket pada seq={seq}: {error}")

        except Exception as error:
            lost_packet += 1
            print(f"ERROR tidak terduga pada seq={seq}: {error}")

        time.sleep(1)

    test_end_time = time.perf_counter()
    duration_seconds = test_end_time - test_start_time

    udp_socket.close()

    received_packet = total_packet - lost_packet
    packet_loss_percent = (lost_packet / total_packet) * 100

    print("\n=== STATISTIK QOS UDP ===")
    print(f"Packet sent       : {total_packet}")
    print(f"Packet received   : {received_packet}")
    print(f"Packet lost       : {lost_packet}")
    print(f"Packet loss       : {packet_loss_percent:.2f}%")
    print(f"Durasi pengujian  : {duration_seconds:.2f} detik")

    if rtt_list:
        min_rtt = min(rtt_list)
        avg_rtt = calculate_average(rtt_list)
        max_rtt = max(rtt_list)
        jitter = calculate_jitter(rtt_list)
        throughput_kbps = calculate_throughput_kbps(success_payload_bytes, duration_seconds)

        print(f"Min RTT           : {min_rtt:.2f} ms")
        print(f"Avg RTT           : {avg_rtt:.2f} ms")
        print(f"Max RTT           : {max_rtt:.2f} ms")
        print(f"Jitter            : {jitter:.2f} ms")
        print(f"Throughput        : {throughput_kbps:.2f} kbps")
        print(f"Payload berhasil  : {success_payload_bytes} bytes")
    else:
        print("Tidak ada paket yang berhasil diterima.")
        print("RTT, jitter, dan throughput tidak dapat dihitung.")


# =========================================================
# MENU INTERAKTIF
# =========================================================
def run_menu():
    while True:
        print("\n===================================")
        print(" CLIENT - TUBES JARINGAN KOMPUTER")
        print("===================================")
        print("1. HTTP GET via Proxy")
        print("2. UDP QoS Ping")
        print("3. Keluar")

        choice = input("Pilih mode: ").strip()

        if choice == "1":
            proxy_host = input(f"Masukkan IP Proxy [{DEFAULT_PROXY_HOST}]: ").strip() or DEFAULT_PROXY_HOST
            server_host = input(f"Masukkan Host Header Web Server [{DEFAULT_SERVER_HOST}]: ").strip() or DEFAULT_SERVER_HOST
            path = input("Masukkan path file [/index.html]: ").strip() or "/index.html"

            http_get_via_proxy(
                proxy_host=proxy_host,
                proxy_port=DEFAULT_PROXY_PORT,
                server_host=server_host,
                path=path
            )

        elif choice == "2":
            server_host = input(f"Masukkan IP Web Server UDP [{DEFAULT_SERVER_HOST}]: ").strip() or DEFAULT_SERVER_HOST
            total_packet_input = input("Jumlah paket UDP [10]: ").strip() or "10"

            try:
                total_packet = int(total_packet_input)
            except ValueError:
                print("Input jumlah paket tidak valid. Nilai otomatis diubah menjadi 10.")
                total_packet = 10

            udp_qos_ping(
                server_host=server_host,
                udp_port=DEFAULT_UDP_PORT,
                total_packet=total_packet
            )

        elif choice == "3":
            print("Program selesai.")
            break

        else:
            print("Pilihan tidak valid.")


# =========================================================
# ARGUMENT PARSER
# =========================================================
def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Client TUBES Jarkom: HTTP via Proxy dan UDP QoS Pinger"
    )

    parser.add_argument(
        "--mode",
        choices=["tcp", "udp", "menu"],
        default="menu",
        help="Mode program: tcp, udp, atau menu"
    )

    parser.add_argument(
        "--proxy-host",
        default=DEFAULT_PROXY_HOST,
        help="Alamat IP proxy untuk mode TCP"
    )

    parser.add_argument(
        "--proxy-port",
        type=int,
        default=DEFAULT_PROXY_PORT,
        help="Port proxy untuk mode TCP"
    )

    parser.add_argument(
        "--server-host",
        default=DEFAULT_SERVER_HOST,
        help="Alamat IP web server. Dipakai sebagai Host header TCP dan target UDP"
    )

    parser.add_argument(
        "--udp-port",
        type=int,
        default=DEFAULT_UDP_PORT,
        help="Port UDP echo server"
    )

    parser.add_argument(
        "--path",
        default="/index.html",
        help="Path file HTML yang diminta pada mode TCP"
    )

    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Jumlah paket UDP untuk mode UDP, minimal 10"
    )

    return parser.parse_args()


# =========================================================
# MAIN PROGRAM
# =========================================================
def main():
    args = parse_arguments()

    if args.mode == "tcp":
        http_get_via_proxy(
            proxy_host=args.proxy_host,
            proxy_port=args.proxy_port,
            server_host=args.server_host,
            path=args.path
        )

    elif args.mode == "udp":
        udp_qos_ping(
            server_host=args.server_host,
            udp_port=args.udp_port,
            total_packet=args.count
        )

    else:
        run_menu()


if __name__ == "__main__":
    main()