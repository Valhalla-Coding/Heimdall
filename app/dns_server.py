"""
Lightweight DNS server built with dnslib.

Listens on UDP port 5353 (no root/admin required).
- Resolves hostnames defined in the Route table → proxy IP (192.168.1.10).
- All *.local queries that match a route resolve to the proxy machine.
- Falls back to 8.8.8.8 for everything else so normal internet still works.

Router setup: set DNS Server 1 to 192.168.1.10 in your router's DHCP settings.
Every device on the network then automatically resolves *.local via this server.
"""

import os
import socket
import logging

from dnslib import RR, QTYPE, A
from dnslib.server import DNSServer, BaseResolver, DNSLogger

from .database import SessionLocal, Route, Device

DNS_PORT   = int(os.environ.get("DNS_PORT", 5353))
UPSTREAM_DNS = "8.8.8.8"

# The IP of THIS machine on the LAN — what all *.local names resolve to.
# Clients get routed here, then the proxy forwards them to the right service.
PROXY_IP = os.environ.get("PROXY_IP", "192.168.1.10")

log = logging.getLogger("dns")


class ProxyResolver(BaseResolver):
    """
    Resolves *.local hostnames that match a Route in the DB → PROXY_IP.
    Everything else is forwarded to upstream DNS so internet keeps working.
    """

    def resolve(self, request, handler):
        qname = str(request.q.qname).rstrip(".").lower()
        qtype = QTYPE[request.q.qtype]
        reply = request.reply()

        if qtype in ("A", "ANY"):
            db = SessionLocal()
            try:
                route = (
                    db.query(Route)
                    .filter(Route.hostname == qname, Route.enabled == True)
                    .first()
                )
                # Also resolve the bare device hostname (e.g. "oden.local")
                # even if there's no explicit route — resolve to PROXY_IP so
                # the proxy can serve the landing page.
                if not route:
                    device = (
                        db.query(Device)
                        .filter(Device.active == True)
                        .all()
                    )
                    # Match oden.local → device hostname "oden"
                    matched = any(
                        qname == f"{d.hostname}.local" or qname == d.hostname
                        for d in device
                    )
                    if matched:
                        route = True  # just needs to resolve
            finally:
                db.close()

            if route:
                log.info(f"DNS: {qname} → {PROXY_IP}")
                reply.add_answer(
                    RR(
                        rname=request.q.qname,
                        rtype=QTYPE.A,
                        ttl=60,
                        rdata=A(PROXY_IP),
                    )
                )
                return reply

        # Fall back to upstream
        try:
        