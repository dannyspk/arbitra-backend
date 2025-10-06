import time
import glob
import os
import base64
from arbitrage.exchanges.mexc_depth_feeder import MexcDepthFeeder

# Start feeder for BTCUSDT, run for short time, stop and inspect
f = MexcDepthFeeder(['BTCUSDT'])
print('Starting feeder... (will run ~8s)')
f.start()
try:
    time.sleep(8)
finally:
    print('Stopping feeder...')
    f.stop()

print('\nOrder book snapshot:')
print(f.get_order_book('BTCUSDT', depth=5))

# Look for sample bin files
samples = sorted(glob.glob('mexc_sample_*.bin'))
if not samples:
    print('\nNo mexc_sample_*.bin files found in repo root; check mexc_raw_messages.log for raw frames.')
else:
    print(f'\nFound {len(samples)} sample files. Trying to decode first one: {samples[0]}')
    path = samples[0]
    with open(path, 'rb') as fh:
        data = fh.read()
    # try to decode with mexc_proto
    try:
        import importlib
        proto = importlib.import_module('arbitrage.exchanges.mexc_proto')
        decoded = None
        from google.protobuf.json_format import MessageToDict
        for name, objv in list(proto.__dict__.items()):
            try:
                if hasattr(objv, '__name__') and objv.__name__.endswith('_pb2'):
                    continue
            except Exception:
                pass
            # we want classes or modules named Public* or containing 'Depth'
            try:
                if isinstance(objv, type):
                    # instantiate
                    inst = objv()
                    if hasattr(inst, 'ParseFromString'):
                        try:
                            inst.ParseFromString(data)
                            decoded = MessageToDict(inst, preserving_proto_field_name=True)
                            print(f'Decoded with proto class {name}:')
                            print(decoded)
                            break
                        except Exception:
                            continue
            except Exception:
                continue
        if decoded is None:
            print('No proto class parsed the sample; printing first 64 bytes hex:')
            print(data[:64].hex())
    except Exception as e:
        print('Error while trying to decode sample with mexc_proto:', e)

print('\nDone.')
