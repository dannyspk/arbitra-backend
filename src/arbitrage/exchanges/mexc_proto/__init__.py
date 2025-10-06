"""mexc_proto package - prefer generated pb2 modules and fall back to stubs.

This file will import the generated *_pb2 modules produced by protoc
when available. If generation hasn't been run, lightweight stub
classes remain as a safe fallback so the feeder can run without error.
"""
from __future__ import annotations

try:
    # prefer generated modules
    from . import PublicIncreaseDepthsV3Api_pb2 as PublicIncreaseDepthsV3Api_pb2
    from . import PublicIncreaseDepthsBatchV3Api_pb2 as PublicIncreaseDepthsBatchV3Api_pb2
    from . import PublicLimitDepthsV3Api_pb2 as PublicLimitDepthsV3Api_pb2
    from . import PublicAggreDepthsV3Api_pb2 as PublicAggreDepthsV3Api_pb2
    from . import PublicAggreDealsV3Api_pb2 as PublicAggreDealsV3Api_pb2
    from . import PublicDealsV3Api_pb2 as PublicDealsV3Api_pb2
    from . import PublicBookTickerV3Api_pb2 as PublicBookTickerV3Api_pb2
    from . import PublicBookTickerBatchV3Api_pb2 as PublicBookTickerBatchV3Api_pb2

    # map common message type names to generated classes (best-effort)
    PublicIncreaseDepthsV3Api = getattr(PublicIncreaseDepthsV3Api_pb2, 'PublicIncreaseDepthsV3Api', None) or getattr(PublicIncreaseDepthsV3Api_pb2, 'PublicIncreaseDepthsV3ApiMessage', None)
    PublicIncreaseDepthsBatchV3Api = getattr(PublicIncreaseDepthsBatchV3Api_pb2, 'PublicIncreaseDepthsBatchV3Api', None)
    PublicLimitDepthsV3Api = getattr(PublicLimitDepthsV3Api_pb2, 'PublicLimitDepthsV3Api', None)
    PublicAggreDepthsV3Api = getattr(PublicAggreDepthsV3Api_pb2, 'PublicAggreDepthsV3Api', None)
    PublicAggreDealsV3Api = getattr(PublicAggreDealsV3Api_pb2, 'PublicAggreDealsV3Api', None)
    PublicDealsV3Api = getattr(PublicDealsV3Api_pb2, 'PublicDealsV3Api', None)
    PublicBookTickerV3Api = getattr(PublicBookTickerV3Api_pb2, 'PublicBookTickerV3Api', None)
    PublicBookTickerBatchV3Api = getattr(PublicBookTickerBatchV3Api_pb2, 'PublicBookTickerBatchV3Api', None)

    __all__ = [
        'PublicIncreaseDepthsV3Api',
        'PublicIncreaseDepthsBatchV3Api',
        'PublicLimitDepthsV3Api',
        'PublicAggreDepthsV3Api',
        'PublicAggreDealsV3Api',
        'PublicDealsV3Api',
        'PublicBookTickerV3Api',
        'PublicBookTickerBatchV3Api',
    ]
except Exception:
    # fallback stubs
    class _BaseProtoStub:
        def __init__(self):
            self._raw = b''

        def ParseFromString(self, data: bytes):
            self._raw = data

        def to_dict(self):
            return {'_raw_len': len(self._raw)}

    class PublicIncreaseDepthsV3Api(_BaseProtoStub):
        pass

    class PublicIncreaseDepthsBatchV3Api(_BaseProtoStub):
        pass

    class PublicLimitDepthsV3Api(_BaseProtoStub):
        pass

    class PublicAggreDepthsV3Api(_BaseProtoStub):
        pass

    class PublicAggreDealsV3Api(_BaseProtoStub):
        pass

    class PublicDealsV3Api(_BaseProtoStub):
        pass

    class PublicBookTickerV3Api(_BaseProtoStub):
        pass

    class PublicBookTickerBatchV3Api(_BaseProtoStub):
        pass

    __all__ = [
        'PublicIncreaseDepthsV3Api',
        'PublicIncreaseDepthsBatchV3Api',
        'PublicLimitDepthsV3Api',
        'PublicAggreDepthsV3Api',
        'PublicAggreDealsV3Api',
        'PublicDealsV3Api',
        'PublicBookTickerV3Api',
        'PublicBookTickerBatchV3Api',
    ]
