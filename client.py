# client.py
# Nama: Muhammad Zaky Mubarok
# Peran: Client - HTTP Request via Proxy dan UDP QoS Pinger

import socket
import time


# =========================
# KONFIGURASI DEFAULT
# =========================
PROXY_HOST = "127.0.0.1"      # Ganti dengan IP laptop Proxy jika beda perangkat
PROXY_PORT = 8080

SERVER_HOST = "127.0.0.1"     # Ganti dengan IP laptop Web Server untuk UDP QoS
UDP_PORT = 9000

BUFFER_SIZE = 4096
TCP_TIMEOUT = 5
UDP_TIMEOUT = 1


# =========================
# MODE 1: HTTP CLIENT VIA PROXY
# =========================
def receive_all(sock):
    response = b""

    while True:
        data = sock.recv(BUFFER_SIZE)
        if not data:
            break
        response += data

    return response


def http_get_via_proxy(proxy_host, proxy_port, server_host, path):
    if not path.startswith("/"):
        path = "/" + path

    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {server_host}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )

    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.settimeout(TCP_TIMEOUT)

        start_time = time.perf_counter()

        client_socket.connect((proxy_host, proxy_port))
        client_socket.sendall(request.encode("utf-8"))

        response = receive_all(client_socket)

        end_time = time.perf_counter()
        response_time = (end_time - start_time) * 1000

        print("\n=== HTTP RESPONSE DARI PROXY ===")
        print(response.decode("utf-8", errors="replace"))

        print("\n=== INFO HTTP REQUEST ===")
        print(f"Proxy tujuan    : {proxy_host}:{proxy_port}")
        print(f"Path diminta    : {path}")
        print(f"Ukuran response : {len(response)} bytes")
        print(f"Waktu response  : {response_time:.2f} ms")

    except socket.timeout:
        print("ERROR: Koneksi ke proxy timeout.")

    except ConnectionRefusedError:
        print("ERROR: Proxy belum berjalan atau port salah.")

    except Exception as error:
        print(f"ERROR: {error}")

    finally:
        try:
            client_socket.close()
        except:
            pass


# =========================
# MODE 2: UDP QOS PINGER
# =========================
def calculate_jitter(rtt_list):
    if len(rtt_list) < 2:
        return 0

    total_difference = 0

    for i in range(1, len(rtt_list)):
        total_difference += abs(rtt_list[i] - rtt_list[i - 1])

    return total_difference / (len(rtt_list) - 1)


def udp_qos_ping(server_host, udp_port, total_packet=10):
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.settimeout(UDP_TIMEOUT)

    rtt_list = []
    lost_packet = 0

    print("\n=== UDP QOS PINGER ===")
    print(f"Target server : {server_host}:{udp_port}")
    print(f"Jumlah paket  : {total_packet}")
    print("-" * 40)

    for seq in range(1, total_packet + 1):
        timestamp = time.time()
        payload = f"Ping {seq} {timestamp}"

        try:
            start_time = time.perf_counter()

            udp_socket.sendto(payload.encode("utf-8"), (server_host, udp_port))
            data, address = udp_socket.recvfrom(BUFFER_SIZE)

            end_time = time.perf_counter()
            rtt = (end_time - start_time) * 1000
            rtt_list.append(rtt)

            print(f"Reply from {address[0]}: seq={seq} RTT={rtt:.2f} ms")

        except socket.timeout:
            lost_packet += 1
            print(f"Request timed out: seq={seq}")

        except Exception as error:
            lost_packet += 1
            print(f"ERROR seq={seq}: {error}")

        time.sleep(1)

    udp_socket.close()

    received_packet = total_packet - lost_packet
    packet_loss = (lost_packet / total_packet) * 100

    print("\n=== STATISTIK QOS UDP ===")
    print(f"Packet sent     : {total_packet}")
    print(f"Packet received : {received_packet}")
    print(f"Packet lost     : {lost_packet}")
    print(f"Packet loss     : {packet_loss:.2f}%")

    if rtt_list:
        min_rtt = min(rtt_list)
        avg_rtt = sum(rtt_list) / len(rtt_list)
        max_rtt = max(rtt_list)
        jitter = calculate_jitter(rtt_list)

        print(f"Min RTT         : {min_rtt:.2f} ms")
        print(f"Avg RTT         : {avg_rtt:.2f} ms")
        print(f"Max RTT         : {max_rtt:.2f} ms")
        print(f"Jitter          : {jitter:.2f} ms")
    else:
        print("Tidak ada paket yang berhasil diterima, statistik RTT tidak tersedia.")


# =========================
# MENU PROGRAM
# =========================
def main():
    print("===================================")
    print(" CLIENT - TUBES JARINGAN KOMPUTER")
    print("===================================")
    print("1. HTTP GET via Proxy")
    print("2. UDP QoS Ping")
    print("3. Keluar")

    choice = input("Pilih mode: ")

    if choice == "1":
        proxy_host = input(f"Masukkan IP Proxy [{PROXY_HOST}]: ") or PROXY_HOST
        path = input("Masukkan path file [/index.html]: ") or "/index.html"

        http_get_via_proxy(
            proxy_host=proxy_host,
            proxy_port=PROXY_PORT,
            server_host=SERVER_HOST,
            path=path
        )

    elif choice == "2":
        server_host = input(f"Masukkan IP Web Server UDP [{SERVER_HOST}]: ") or SERVER_HOST
        total_packet_input = input("Jumlah paket UDP [10]: ") or "10"

        try:
            total_packet = int(total_packet_input)
        except ValueError:
            total_packet = 10

        udp_qos_ping(
            server_host=server_host,
            udp_port=UDP_PORT,
            total_packet=total_packet
        )

    elif choice == "3":
        print("Program selesai.")

    else:
        print("Pilihan tidak valid.")


if __name__ == "__main__":
    main()