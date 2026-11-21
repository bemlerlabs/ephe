# Server

The FastAPI app: refusals, error opacity and the frozen route contract.

Applies on top of the root AGENTS.md.

## Refusals carry a code

- Raise `server.refusals.Refused(code, **params)` for a refusal the route already understands. It is
  an `HTTPException`, so existing handlers keep working, and the code is the translation key.
- The envelope in `server/main.py` carries `error.code` (the transport class), `error.reason_code`,
  `error.reason_params` and `error.next`. `reason_code` is what `app/src/lib/api/http.ts` prefers
  over `detail` when it picks the sentence to show.
- Register the code in `REASONS` and its move in `NEXT_STEPS`. The sentence the reader sees is the
  one in their own bundle, so a new code needs `serverError.<code>` in both `app/src/locales/en.json`
  and `app/src/locales/de.json`; a test fails when either is missing.
- `HTTPException(detail="a sentence")` is the shape that put one language in front of a reader of the
  other. New routes answer with a code.

## Nothing about an exception reaches the page

An exception's class name, its message and a traceback are for the log, never for the response body
(CWE-209, CWE-497). Log the failure with the request id from `REQUEST_ID_HEADER` and answer with a
payload built from the route's own values. The pattern that keeps a handler clean: the helper that
catches the failure logs it and returns a boolean or a value, and the route builds the response from
that value and its own strings. `server/routes/plugins.py` carries the shape after 7fce5e1f, which
removed the caught exception from the scope that built the answer.

`core/observability.py::error_payload` is the envelope. Keep it to the code, a sentence and the
request id; a stack, a module path or a class name in `detail` is the defect this rule names.

## Route contract

- `/api/*` is userspace. `tests/test_w3_68_api_contract_frozen.py::FROZEN_ROUTES` names every
  operation, and an added, removed or renamed route reds that file. The update belongs in the same
  patch that touches `server/routes/*` or `server/main.py`; the delta it prints is the review.
- Routes are additive. A removal needs a compatibility shim and a documented migration, and a field
  another client reads is a contract, not an implementation detail.
- A GET that writes state or opens another service goes into `AUTHORITY_GET_PREFIXES` in
  `server/middleware.py`, so `LocalRequestGuardMiddleware` checks its origin. A read-only GET stays
  open for the app's own token-free fetch; `AUTHORITY_GET_PREFIXES` is the one place that decides
  which GETs spend authority.
- A mutation, or a GET that spends local authority, requires an origin this server serves or the LAN
  token. The `testserver` host is a seam for the suite; it is not an allowance for a route.
- A browser-only endpoint the app calls with `fetch` checks `X-Requested-With: XMLHttpRequest`,
  which a cross-site form cannot set. The client half is in `app/src/lib/api/http.ts`. A route that
  opens a socket or returns a token stays behind the origin check as well.
- Security defaults are conservative: loopback binding, no wildcard CORS, mobile pairing off until
  the operator enables it, tool approval on. Changing one of those is a boundary in the root hub.

## Tests for a route

A route test uses `TestClient(create_app())`; the autouse fixtures in `tests/conftest.py` already
point `EPHE_CONFIG_DIR` at `tmp_path`, so the developer's own `~/.ephe` is never in play. Assert the
status, the envelope and the absence of an exception's class name. A refusal test also asserts the
sentence the bundle renders for the code, so the code and its text cannot drift apart.
