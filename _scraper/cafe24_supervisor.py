# -*- coding: utf-8 -*-
"""cafe24.py ALL 수퍼바이저 — 소스 11곳 순차 실행 (kpp_supervisor 패턴, 2026-07-09).
   출력 10분 무응답이면 kill 후 체크포인트(data/_<site>_done.json)에서 재시작.
   완료 신호('완료 브랜드별 누계') 보이면 다음 소스로. 실행: python -u cafe24_supervisor.py
   순서 = sources.md 진행 순서: 전용 브랜드몰 → 종합몰(시네몰·반도)."""
import subprocess, sys, io, time, threading, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "cafe24.py")
STALL_SEC = 600
MAX_RESTARTS = 40
ORDER = ["fomex","hktools","sama","benro","hipixel","mustcolor",
         "motionnine","onnoff","ldnet","cinemall","bando"]

def run_site(site):
    state = {"last": time.time(), "finished": False}
    for attempt in range(1, MAX_RESTARTS+1):
        print(f"=== [수퍼바이저] {site} 실행 {attempt}/{MAX_RESTARTS} ===", flush=True)
        p = subprocess.Popen([sys.executable, "-u", SCRIPT, site, "ALL"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=HERE)
        state["last"] = time.time()
        def reader():
            for line in p.stdout:
                try: sys.stdout.buffer.write(line); sys.stdout.flush()
                except Exception: pass
                state["last"] = time.time()
                if "완료 브랜드별 누계".encode("utf-8") in line:
                    state["finished"] = True
        t = threading.Thread(target=reader, daemon=True); t.start()
        while p.poll() is None:
            time.sleep(10)
            if time.time() - state["last"] > STALL_SEC:
                print(f"\n!! [수퍼바이저] {site} {STALL_SEC}s 무응답 → kill 후 재시작", flush=True)
                p.kill()
                break
        t.join(timeout=10)
        if state["finished"] or (p.poll() == 0 and time.time()-state["last"] <= STALL_SEC):
            print(f"=== [수퍼바이저] {site} 완료 ===", flush=True)
            return True
        time.sleep(5)
    print(f"!! [수퍼바이저] {site} 최대 재시작 도달 — 스킵하고 다음 소스", flush=True)
    return False

if __name__ == "__main__":
    sites = sys.argv[1:] or ORDER
    fail = [s for s in sites if not run_site(s)]
    print(f"\n=== [수퍼바이저] 전체 종료 — 실패 소스: {fail or '없음'} ===", flush=True)
