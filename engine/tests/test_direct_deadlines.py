"""Real HTTP parser over local socket pairs; no external network requests."""
import hashlib
import multiprocessing
import socket
import threading
import time
import unittest
from unittest.mock import patch

from jobrouter import transport
from jobrouter.transport import FetchError, PublicFetcher

_REAL_WORKER = transport._direct_request_worker


def direct_fixture_worker(directory, url, user_agent, timeout, max_bytes):
    mode = url.rsplit('/', 1)[-1]
    client, server = socket.socketpair()
    client.settimeout(timeout)

    def send():
        try:
            server.recv(4096)
            if mode == 'headers-slow':
                server.sendall(b'HTTP/1.1 200 OK\r\nX-Slow: ')
                data = b'x' * 200
            elif mode == 'chunk-framing-slow':
                server.sendall(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1;')
                data = b'x' * 200
            elif mode == 'body-slow':
                server.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 200\r\n\r\n')
                data = b'x' * 200
            elif mode == 'chunked':
                server.sendall(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n')
                return
            else:
                status = mode if mode in ('302', '403', '429') else '200'
                server.sendall(f'HTTP/1.1 {status} Fixture\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello'.encode())
                return
            for byte in data:
                server.sendall(bytes([byte]))
                time.sleep(0.03)
        except OSError:
            pass
        finally:
            server.close()

    def resolve(hostname, port, **kwargs):
        if mode == 'dns-slow':
            time.sleep(20)
        address = '127.0.0.1' if mode == 'private-dns' else '93.184.216.34'
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, port))]

    def connect(address, timeout):
        assert address == ('93.184.216.34', 443), 'must pin validated DNS address'
        if mode == 'connect-slow':
            time.sleep(20)
        threading.Thread(target=send, daemon=True).start()
        return client

    class TLSContext:
        def wrap_socket(self, raw, server_hostname):
            assert server_hostname == 'jobs.example', 'must retain hostname verification'
            if mode == 'tls-slow':
                time.sleep(20)
            return raw

    try:
        with patch.object(transport.socket, 'getaddrinfo', resolve), patch.object(transport.socket, 'create_connection', connect), patch.object(transport.ssl, 'create_default_context', return_value=TLSContext()):
            _REAL_WORKER(directory, url, user_agent, timeout, max_bytes)
    finally:
        client.close()
        server.close()


class DirectDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.worker = patch.object(transport, '_direct_request_worker', direct_fixture_worker)
        self.worker.start()
        self.addCleanup(self.worker.stop)

    def test_success_and_receipt(self):
        fetcher = PublicFetcher(timeout=3, per_origin_delay=0)
        response = fetcher._one('https://jobs.example/ok')
        self.assertEqual(response.body, b'hello')
        self.assertEqual(response.status, 200)
        self.assertEqual(fetcher.receipts[0]['sha256'], hashlib.sha256(b'hello').hexdigest())

    def test_total_deadline_includes_dns_connect_tls_headers_body_and_chunk_framing(self):
        for mode in ('dns-slow', 'connect-slow', 'tls-slow', 'headers-slow', 'body-slow', 'chunk-framing-slow'):
            fetcher = PublicFetcher(timeout=0.5, per_origin_delay=0)
            pids = []
            reap = transport._reap_request_worker

            def record_reap(process):
                pids.append(process.pid)
                reap(process)

            start = time.monotonic()
            with self.subTest(mode=mode), patch.object(transport, '_reap_request_worker', record_reap):
                with self.assertRaisesRegex(FetchError, 'Direct fetch deadline exceeded'):
                    fetcher._one('https://jobs.example/' + mode)
                self.assertLess(time.monotonic() - start, 3)
                self.assertEqual(len(pids), 1)
                self.assertFalse(any(p.pid in pids for p in multiprocessing.active_children()))
                self.assertEqual(fetcher.used, 1)
                self.assertIn('deadline exceeded', fetcher.receipts[0]['error'])

    def test_private_dns_is_rejected(self):
        with self.assertRaisesRegex(FetchError, 'Non-public DNS answer'):
            PublicFetcher(timeout=3)._wire('https://jobs.example/private-dns')

    def test_size_limit(self):
        for mode in ('ok', 'chunked'):
            with self.subTest(mode=mode):
                self.assertEqual(PublicFetcher(timeout=3, max_bytes=5)._wire('https://jobs.example/' + mode).body, b'hello')
                with self.assertRaisesRegex(FetchError, 'byte limit'):
                    PublicFetcher(timeout=3, max_bytes=4)._wire('https://jobs.example/' + mode)

    def test_redirect_and_access_status_are_preserved(self):
        for status in (302, 403, 429):
            with self.subTest(status=status):
                fetcher = PublicFetcher(timeout=3, per_origin_delay=0)
                self.assertEqual(fetcher._one('https://jobs.example/' + str(status)).status, status)
                if status in (403, 429):
                    with self.assertRaisesRegex(FetchError, 'Origin stopped'):
                        fetcher._one('https://jobs.example/ok')
                    self.assertEqual(fetcher.used, 1)
