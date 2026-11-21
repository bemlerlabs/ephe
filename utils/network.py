import socket

def get_local_ip() -> str:
    """Returns the local IPv4 address of the machine on the local network."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(2.0)
            # connect to an external server but doesn't actually send any data on DGRAM
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        # Fallback if offline
        return "127.0.0.1"

def is_internet_available(timeout: float = 2.0) -> bool:
    """Checks if the system has internet access by attempting a DNS/UDP connection."""
    try:
        # Pinging a reliable external IP (dns.google)
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("1.1.1.1", 53))
        return True
    except Exception:
        return False
