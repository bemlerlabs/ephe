"""
◑ Ephe – Given-When-Then validation of every capability
Every single function is tested live.
"""
import asyncio
import tempfile
import pathlib
import shutil

PASS = 0
FAIL = 0

def ok(name, desc):
    global PASS
    PASS += 1
    print(f"  ✅ {name:24s} {desc}")

def fail(name, desc):
    global FAIL
    FAIL += 1
    print(f"  ❌ {name:24s} {desc}")

def test(name, condition, desc):
    if condition:
        ok(name, desc)
    else:
        fail(name, desc)

async def main():
    print("=" * 60)
    print(" ◑ Ephe – GIVEN-WHEN-THEN VALIDATION")
    print("=" * 60)

    print("\n── Core Modules ──")

    # 1. ThinkingStreamParser
    from core.chat import ThinkingStreamParser
    chunks = []
    p = ThinkingStreamParser(on_chunk=lambda t: chunks.append(t))
    for t in ["Hi", "<|think|>", "Gedanke", "<|/think|>", " Antwort"]:
        p.feed(t)
    p.flush()
    test("ThinkingParser", "Gedanke" in p.thinking and "Antwort" in p.answer,
         "GIVEN <|think|> stream WHEN parsed THEN thinking/answer split")

    # 2. CorrectionJournal
    from core.corrections import CorrectionJournal
    cj = CorrectionJournal(path=pathlib.Path(tempfile.mkdtemp()) / "c.md")
    cj.add("falsch", "richtig")
    entries = cj.get_recent(5)
    test("CorrectionJournal", len(entries) >= 1,
         f"GIVEN add(bad,good) WHEN get_recent THEN {len(entries)} entry")

    # 3. FeedbackStore
    from core.feedback import FeedbackStore
    fs = FeedbackStore(base_dir=pathlib.Path(tempfile.mkdtemp()))
    fs.thumbs_up("q1", "good")
    fs.thumbs_down("q2", "bad")
    test("FeedbackStore", len(fs.get_good_examples()) == 1 and len(fs.get_bad_examples()) == 1,
         "GIVEN up+down WHEN get THEN 1 good + 1 bad")

    # 4. UserProfile
    from core.profile import load_profile, update_profile
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    ppath = tmpdir / "profile.json"
    updated = update_profile({"name": "Michi", "expertise": "KI"}, path=ppath)
    loaded = load_profile(path=ppath)
    test("UserProfile", loaded.name == "Michi",
         f"GIVEN update(Michi) WHEN load THEN name={loaded.name}")

    # 5. Session
    from core.session import save_session, load_last_session
    # Session uses a fixed path, just test it doesn't crash
    try:
        msgs = load_last_session()
        test("SessionStore", isinstance(msgs, list),
             f"GIVEN session WHEN load THEN {len(msgs)} messages")
    except Exception as e:
        fail("SessionStore", str(e))

    # 6. MemoryStore (ChromaDB)
    from core.memory import Memory
    ms = Memory(persist_dir=tempfile.mkdtemp())
    ms.store("Der Schwarzwald im Nebel")
    r = ms.search("Schwarzwald", top_k=1)
    found = bool(r) and any("Schwarzwald" in str(x) for x in r)
    test("MemoryStore", found,
         f"GIVEN store(Schwarzwald) WHEN search THEN found ({len(r)} results)")

    # 7. EpheScheduler
    from core.scheduler import EpheScheduler
    sc = EpheScheduler()
    sc.start()
    jid = sc.add_job("Test", "0 0 31 2 *")  # never fires
    jobs = sc.list_jobs()
    sc.remove_job(jid)
    sc.stop()
    test("Scheduler", len(jobs) == 1,
         "GIVEN add_job(cron) WHEN list THEN 1 job")

    # 8. SkillLoader
    from core.skills import SkillLoader
    sl = SkillLoader()
    skills = sl.load_all()
    test("SkillLoader", len(skills) >= 6,
         f"GIVEN skills/ WHEN load_all THEN {len(skills)} skills")

    # 9. resolve_trigger
    sk = sl.resolve_trigger("/research")
    test("resolve_trigger", sk is not None and sk.name == "web-researcher",
         "GIVEN /research WHEN resolve THEN web-researcher")

    # 10. SkillBuilder / Learn Command
    from core.commands import is_learn_command, extract_learn_topic
    test("SkillBuilder",
         is_learn_command("/learn Test") and extract_learn_topic("/learn Test") == "Test",
         "GIVEN /learn Test WHEN parse THEN topic=Test")

    # 11. ArtifactDetector
    from core.artifact_detector import ArtifactDetector
    det = ArtifactDetector()
    code = "X:\n```python\nimport os\nfor i in range(10):\n    print(i)\n# line4\n# end\n```"
    arts = det.detect(code)
    test("ArtifactDetector", len(arts) >= 1,
         f"GIVEN code block ≥5 lines WHEN detect THEN {len(arts)} artifact")

    # 12. SlashCommands
    from core.commands import COMMANDS
    test("SlashCommands", len(COMMANDS) > 0,
         f"GIVEN COMMANDS dict WHEN loaded THEN {len(COMMANDS)} commands")

    print("\n── Tools (Live Execution) ──")

    from core.tools import (
        web_search, file_search, read_file, list_directory,
        get_datetime, run_shell, execute_confirmed_shell,
        load_workspace
    )

    # 13. web_search
    try:
        r = await web_search("Python 3", max_results=2)
        test("web_search", len(r) >= 1,
             f"GIVEN query WHEN search THEN {len(r)} results")
    except Exception as e:
        fail("web_search", str(e))

    # 14. get_datetime
    r = await get_datetime()
    test("get_datetime", "2026" in r,
         f"GIVEN now WHEN call THEN \"{r}\"")

    # 15. list_directory
    r = await list_directory("/Users/demo/Desktop")
    test("list_directory", len(r) > 0,
         f"GIVEN Desktop WHEN list THEN {len(r)} entries")

    # 16. file_search
    r = await file_search("README", "/Users/demo/Desktop")
    test("file_search", len(r) > 0 and "nicht" not in r.lower()[:20],
         f"GIVEN README WHEN search Desktop THEN hits found")

    # 17. read_file
    tmp = pathlib.Path(tempfile.gettempdir()) / "ephe_gwt.txt"
    tmp.write_text("GWT Testinhalt")
    r = await read_file(str(tmp))
    tmp.unlink()
    test("read_file", "GWT" in r,
         "GIVEN tmp file WHEN read THEN content returned")

    # 18. run_shell (real execution + security gates)
    try:
        r = await run_shell("echo Ephe")
        test("run_shell", "Ephe" in r,
             "GIVEN whitelisted cmd WHEN run_shell THEN output returned (echte Ausführung)")
        r2 = await run_shell("rm -rf /tmp/ephe_never")
        test("run_shell_gate", "Sicherheit" in r2 or "Whitelist" in r2,
             "GIVEN blocked cmd WHEN run_shell THEN Security-Message, NICHT ausgeführt")
    except Exception as e:
        fail("run_shell", str(e))

    # 19. execute_confirmed_shell
    r = await execute_confirmed_shell("echo Ephe", confirmed=True)
    test("exec_confirmed_shell", "Ephe" in r,
         "GIVEN confirmed=True WHEN echo THEN output returned")

    # 20. load_workspace
    td = pathlib.Path(tempfile.mkdtemp())
    (td / "a.py").write_text("print(1)")
    (td / "b.py").write_text("print(2)")
    r = await load_workspace(str(td), extensions=[".py"])
    shutil.rmtree(td)
    test("load_workspace", "a.py" in r and "b.py" in r,
         "GIVEN dir with .py WHEN load THEN both files included")

    print("\n── API Endpoints (Live Server auf :8765) ──")

    import requests
    API = "http://127.0.0.1:8765/api"

    # 21. Health
    r = requests.get(f"{API}/health", timeout=5)
    test("GET /health", r.ok and r.json().get("ollama") == True,
         "GIVEN server WHEN health THEN ollama=True")

    # 22. Profile GET
    r = requests.get(f"{API}/profile", timeout=5)
    test("GET /profile", r.ok and "name" in r.json(),
         "GIVEN profile WHEN get THEN has name field")

    # 23. Profile PUT
    r = requests.put(f"{API}/profile",
                     json={"name": "GWT", "expertise": "Test",
                           "preferred_language": "de", "response_style": "kurz"},
                     timeout=5)
    test("PUT /profile", r.ok,
         "GIVEN new name WHEN put THEN saved")

    # 24. Skills GET
    r = requests.get(f"{API}/skills", timeout=5)
    skills_count = len(r.json()["skills"]) if r.ok else 0
    test("GET /skills", r.ok and skills_count >= 6,
         f"GIVEN skills WHEN list THEN {skills_count} skills")

    # 25. Memory List
    r = requests.get(f"{API}/memory/list", timeout=5)
    test("GET /memory/list", r.ok,
         f"GIVEN memory WHEN list THEN {len(r.json().get('entries',[]))} entries")

    # 26. Memory Search
    r = requests.get(f"{API}/memory/search?q=test&limit=3", timeout=5)
    test("GET /memory/search", r.ok,
         "GIVEN query WHEN search THEN 200 OK")

    # 27. Feedback
    r = requests.post(f"{API}/feedback/thumbs_up",
                      json={"prompt": "gwt", "response": "ok"}, timeout=5)
    test("POST /feedback", r.ok,
         "GIVEN good answer WHEN thumbs_up THEN saved")

    # 28. Mobile QR
    r = requests.get(f"{API}/mobile/qr", timeout=10)
    url = r.json().get("url", "") if r.ok else ""
    test("GET /mobile/qr", url.endswith("/mobile.html"),
         f"GIVEN request WHEN qr THEN URL → /mobile.html")

    # 29. Mobile Ping + Status
    requests.post(f"{API}/mobile/ping", timeout=5)
    r = requests.get(f"{API}/mobile/status", timeout=5)
    test("mobile ping→status", r.ok and r.json()["connected"] == True,
         "GIVEN ping WHEN status THEN connected=True")

    # 30. Scheduler
    r = requests.get(f"{API}/schedule", timeout=5)
    test("GET /schedule", r.ok,
         f"GIVEN scheduler WHEN list THEN {len(r.json().get('jobs',[]))} jobs")

    # 31. Chat (sync)
    r = requests.post(f"{API}/chat",
                      json={"message": "Sage nur OK", "model": "gemma4:12b"},
                      timeout=60)
    resp_text = r.json().get("response", "") if r.ok else ""
    test("POST /chat", r.ok and len(resp_text) > 0,
         f"GIVEN 'Sage OK' WHEN chat THEN response: \"{resp_text[:40]}\"")

    # 32. SSE Stream endpoint (connect only)
    r = requests.post(f"{API}/chat/stream",
                      json={"message": "Sage OK", "model": "gemma4:12b",
                            "history": [], "autonomous": False},
                      stream=True, timeout=10)
    first = b""
    try:
        for chunk in r.iter_content(256):
            first += chunk
            if len(first) > 100:
                break
    except:
        pass
    test("POST /chat/stream", r.ok and len(first) > 0,
         f"GIVEN msg WHEN stream THEN SSE started ({len(first)} bytes)")

    print()
    print("=" * 60)
    print(f"  ERGEBNIS: {PASS} bestanden / {FAIL} fehlgeschlagen")
    print(f"  GESAMT:   {PASS + FAIL} Tests")
    print("=" * 60)

    if FAIL > 0:
        exit(1)


asyncio.run(main())
