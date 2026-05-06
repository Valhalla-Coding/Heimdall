"""
Lightweight DNS server built with dnslib.

Listens on UDP port 53 (requires cap_net_bind_service or root).
- Resolves *.local hostnames that match a Route or Device in the DB -> PROXY_IP.
- Falls back to 8.8.8.8 for everything else so normal internet still works.

Set DNS_PORT env var to override (default 53).
Set PROXY_IP env var to the LAN IP of this machine (detected automatically by run.sh).
"""

import os
import socket
import logging

from dnslib import RR, QTYPE, A, DNSRecord
from dnslib.server import DNSServer, BaseResolver, DNSLogger

from .database import SessionLocal, Route, Device

DNS_PORT     = int(os.environ.get("DNS_PORT", 53))
UPSTREAM_DNS = "8.8.8.8"
PROXY_IP     = os.environ.get("PROXY_IP", "192.168.1.10")

log = logging.getLogger("dns")


class ProxyResolver(BaseResolver):
    """
    Resolves *.local hostnames that match a Route or Device in the DB -> PROXY_IP.
    Everything else is forwarded upstream so normal internet keeps working.
    """

    def resolve(self, request, handler):
        qname = str(request.q.qname).rstrip(".").lower()
        qtype = QTYPE[request.q.qtype]
        reply = request.reply()

        if qtype in ("A", "ANY"):
            db = SessionLocal()
            try:
                # Check for an explicit route match
                route = (
                    db.query(Route)
                    .filter(Route.hostname == qname, Route.enabled == True)
                    .first()
                )

                if not route:
                    # Also resolve bare device hostnames (e.g. "oden.local")
                    # so the proxy can serve the landing page even without an
                    # explicit route entry.
                    devices = db.query(Device).filter(Device.active == True).all()
                    matched = any(
                        qname == f"{d.hostname}.local" or
                        qname == f"www.{d.hostname}.local" or
                        qname == d.hostname
                        for d in devices
                    )
                    if matched:
                        route = True  # sentinel — just needs to resolve
            finally:
                db.close()

            if route:
                log.info(f"DNS: {qname} -> {PROXY_IP}")
                reply.add_answer(RR(
                    rname=request.q.qname,
                    rtype=QTYPE.A,
                    ttl=60,
                    rdata=A(PROXY_IP),
                ))
                return reply

        # Fall back to upstream DNS
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3)
            sock.sendto(request.pack(), (UPSTREAM_DNS, 53))
            data, _ = sock.recvfrom(4096)
            sock.close()
            return DNSRecord.parse(data)
        except Exception as exc:
            log.warning(f"DNS upstream failed for {qname}: {exc}")
            return reply


def start_dns_server():
    """Start the DNS server. Called in a daemon thread from main.py."""
    resolver = ProxyResolver()
    logger   = DNSLogger(prefix=False)
    server   = DNSServer(resolver, port=DNS_PORT, address="0.0.0.0", logger=logger)
    log.info(f"DNS server listening on UDP 0.0.0.0:{DNS_PORT}")
    server.start()
