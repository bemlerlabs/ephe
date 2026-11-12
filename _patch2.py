p='server/routes/settings.py'
s=open(p).read()
anchor='    return {\n        "provider": _active_provider_dict(),\n        "memory_enabled"'
assert s.count(anchor)==1, f'return anchor {s.count(anchor)}'
ret_block = """
        # The window the switch just resolved: the engine's own reported maximum
        # when the probe answered, None when nothing named one (the surface keeps its
        # previous value; the backend keeps its fallback order). Same key the
        # model-providers route answers with, so both surfaces read one number.
        "context_window": _engine_window,"""
s=s.replace(anchor, '    return {\n        "provider": _active_provider_dict(),' + ret_block + '\n        "memory_enabled"', 1)
open(p,'w').write(s)
print('patched, refs:', s.count('_engine_window'))
