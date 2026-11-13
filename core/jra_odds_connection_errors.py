"""Privacy-preserving classification for public odds website transport failures.

Never render raw request URL, tokens, proxy settings, HTML or exception details.
"""
def describe_connection(exc):
    name = type(exc).__name__.lower()
    detail = str(exc).lower()
    if "timeout" in name or "timed out" in detail or "timeout" in detail:
        return "タイムアウト（接続先の応答なし）"
    if ("nameresolution" in detail or "name resolution" in detail
            or "gaierror" in detail or "temporary failure in name" in detail):
        return "DNS名前解決エラー"
    if "ssl" in name or "certificate" in detail or "tls" in detail:
        return "SSL/TLS接続エラー"
    if "proxy" in name or "proxyerror" in detail:
        return "プロキシ接続エラー"
    if ("connectionrefused" in detail or "connection refused" in detail
            or "connectionreset" in detail or "connection reset" in detail):
        return "接続拒否・切断"
    if "connectionerror" in name or "connect" in name:
        return "通信接続エラー"
    return "通信エラー（" + type(exc).__name__[:32] + "）"
