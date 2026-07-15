import socket


def is_port_open(host, port, timeout=5):
    """
    verifies if a port is open in a remote host

    :param host: IP of the remote host
    :type host: str

    :param port: port to check
    :type port: int

    :param timeout: timeout max to check
    :type timeout: int

    :return: True if the port is open
    :rtype: bool
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        return result == 0
