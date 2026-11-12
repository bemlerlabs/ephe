p='server/routes/settings.py'
s=open(p).read()
anchor="            raise HTTPException(status_code=400, detail=str(exc)) from exc\n\n        if key:"
assert s.count(anchor)==1, f'anchor count {s.count(anchor)}'
probe_block = """
        # Dynamic default: the moment an engine is chosen, its own reported window
        # becomes the context window. The probe is asked NOW, inside the switch the
        # user just made - not lazily at the next status-bar poll - so every later
        # answer (budget meter, compaction, the chat loop) reads the fresh value from
        # the probe cache. A failed probe leaves the fallback order (env > probe cache
        # > tier > legacy) untouched; the switch itself never depends on it.
        _engine_window = None
        try:
            from server.routes.model_provider import _active_context_window

            _engine_window = await _active_context_window(get_active_provider())
        except Exception:
            _engine_window = None
"""
s=s.replace(anchor, "            raise HTTPException(status_code=400, detail=str(exc)) from exc\n" + probe_block + "\n        if key:", 1)
old_ret='    return {\n        "provider": _active_provider_dict(),'
assert s.count(old_ret)==1, f'return anchor {s.count(old_ret)}'
ret_block = """
        # The window the switch just resolved: the engine's own reported maximum
        # when the probe answered, None when nothing named one (the surface keeps its
        # previous value; the backend keeps its fallback order). Same key the
        # model-providers route answers with, so both surfaces read one number.
        "context_window": _engine_window,"""
s=s.replace(old_ret, old_ret + ret_block, 1)
open(p,'w').write(s)
print('patched, refs:', s.count('_engine_window'))
