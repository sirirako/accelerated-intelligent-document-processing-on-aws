#!/usr/bin/env python3
"""Probe which ActiveMQ wire protocols a broker actually exposes.

Answers "does this broker support STOMP?" without needing credentials, a JWT, or
the broker admin console. Run it from somewhere with network reach to the broker
(inside the VPC, or a bastion/Cloud Desktop that can route there).

Each port is probed in three stages, so the output distinguishes a firewall from
a missing connector from a TLS problem:

    1. TCP connect      - is anything listening / does the SG allow us?
    2. TLS handshake    - is it a TLS connector, and is the cert chain trusted?
    3. Protocol hello   - for STOMP ports, send a CONNECT frame and look for a
                          CONNECTED or ERROR frame. Either proves STOMP is
                          speaking; a timeout or garbage means it is not.

Usage:
    python probe_mq_ports.py --host amq-broker.example.com
    python probe_mq_ports.py --host amq-broker.example.com --ca-cert /path/ca.pem
    python probe_mq_ports.py --host amq-broker.example.com --ports 61614,61617

Exit code is 0 if a usable STOMP connector was found, 1 otherwise.
"""

import argparse
import socket
import ssl
import sys

# (port, protocol, tls, is_stomp)
DEFAULT_PORTS = [
    (61614, "STOMP", True, True),
    (61613, "STOMP", False, True),
    (61619, "WebSocket/STOMP", True, False),
    (61617, "OpenWire", True, False),
    (61616, "OpenWire", False, False),
    (5671, "AMQP 1.0", True, False),
    (8883, "MQTT", True, False),
]

TIMEOUT = 6


def tcp_connect(host, port):
    try:
        return socket.create_connection((host, port), TIMEOUT), None
    except socket.timeout:
        return None, "timeout (firewall/SG dropping, or nothing listening)"
    except ConnectionRefusedError:
        return None, "refused (reachable, but no connector on this port)"
    except socket.gaierror as e:
        return None, f"DNS failure: {e}"
    except OSError as e:
        return None, f"{type(e).__name__}: {e}"


def tls_wrap(sock, host, ca_cert):
    """Wrap in TLS. Hostname check is off: the customer's broker cert is known
    not to match its hostname, and here we only care which protocol answers."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    if ca_cert:
        try:
            ctx.load_verify_locations(ca_cert)
            ctx.verify_mode = ssl.CERT_REQUIRED
        except Exception as e:
            return None, f"could not load CA bundle: {e}", None
    else:
        ctx.verify_mode = ssl.CERT_NONE
    try:
        tls = ctx.wrap_socket(sock, server_hostname=host)
    except ssl.SSLError as e:
        msg = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in msg:
            return None, f"TLS cert not trusted by the supplied CA bundle: {msg}", None
        return None, f"not a TLS connector, or TLS error: {msg}", None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}", None

    peer = tls.getpeercert()
    return tls, None, peer


def stomp_hello(sock):
    """Send a STOMP CONNECT and report what comes back.

    Bad credentials are fine and even useful: an ERROR frame still proves a STOMP
    connector is on the other end, which is the question being asked.
    """
    frame = (
        b"CONNECT\naccept-version:1.0,1.1,1.2\nhost:probe\n"
        b"login:\npasscode:\n\n\x00"
    )
    try:
        sock.sendall(frame)
        sock.settimeout(TIMEOUT)
        data = sock.recv(1024)
    except socket.timeout:
        return False, "no reply to STOMP CONNECT (likely not a STOMP connector)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    if not data:
        return False, "connection closed with no reply"
    head = data[:200].decode("utf-8", "replace").strip()
    if data.startswith(b"CONNECTED"):
        return True, f"STOMP CONNECTED (anonymous accepted) - {head!r}"
    if data.startswith(b"ERROR"):
        # This is a PASS for our purposes.
        return True, f"STOMP ERROR frame - connector IS live, auth rejected: {head!r}"
    return False, f"non-STOMP reply: {head!r}"


def cert_summary(peer):
    if not peer:
        return "  cert: (not validated - no CA bundle given)"
    subject = dict(x[0] for x in peer.get("subject", ()))
    cn = subject.get("commonName", "?")
    sans = [v for k, v in peer.get("subjectAltName", ()) if k == "DNS"]
    return f"  cert CN={cn}  SAN={sans or '(none)'}"


def main():
    ap = argparse.ArgumentParser(description="Probe ActiveMQ protocol connectors")
    ap.add_argument("--host", required=True, help="Broker hostname")
    ap.add_argument("--ca-cert", help="CA bundle (omit to skip cert validation)")
    ap.add_argument("--ports", help="Comma-separated ports to probe instead of defaults")
    args = ap.parse_args()

    if args.ports:
        wanted = {int(p) for p in args.ports.split(",")}
        ports = [p for p in DEFAULT_PORTS if p[0] in wanted]
        for p in sorted(wanted - {x[0] for x in DEFAULT_PORTS}):
            ports.append((p, "unknown", True, True))
    else:
        ports = DEFAULT_PORTS

    print(f"Probing {args.host}")
    print(f"CA bundle: {args.ca_cert or '(none - certs not validated)'}\n")

    stomp_ok = []
    for port, proto, tls, is_stomp in ports:
        label = f"{port:>5} {proto:<16}{'TLS' if tls else 'plain':<6}"
        sock, err = tcp_connect(args.host, port)
        if err:
            print(f"{label} -- {err}")
            continue
        print(f"{label} -- TCP open")

        peer = None
        if tls:
            sock, err, peer = tls_wrap(sock, args.host, args.ca_cert)
            if err:
                print(f"       TLS: {err}")
                continue
            print(f"       TLS handshake OK ({sock.version()})")
            print(f"     {cert_summary(peer)}")

        if is_stomp:
            ok, detail = stomp_hello(sock)
            print(f"       STOMP probe: {detail}")
            if ok:
                stomp_ok.append((port, tls))
        try:
            sock.close()
        except Exception:
            pass
        print()

    print("=" * 68)
    if stomp_ok:
        best = [p for p, t in stomp_ok if t] or [p for p, _ in stomp_ok]
        print(f"STOMP IS AVAILABLE on port(s): {sorted(p for p, _ in stomp_ok)}")
        print(f"\nSet CompletionHookMQPort to {best[0]} and run test_activemq.py.")
        return 0

    print("NO STOMP CONNECTOR FOUND on the probed ports.")
    print(
        "\nIf every port timed out, this is probably a network/SG issue rather\n"
        "than a broker config one - re-run from inside the VPC before concluding\n"
        "STOMP is unavailable.\n\n"
        "If only OpenWire (61617) answered, the broker genuinely has no STOMP\n"
        "connector. stomp.py cannot speak OpenWire; ask them to enable STOMP, or\n"
        "the hook needs a different client (AMQP 1.0 via qpid-proton, or a bridge)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
