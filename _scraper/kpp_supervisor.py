# -*- coding: utf-8 -*-
"""kpp.py ALL 수퍼바이저 — 출력 4분 무응답이면 kill 후 체크포인트(data/_kpp_done.json)에서 재시작.
   KPP 장시간 연결 타르핏으로 requests가 안 죽고 매달리는 사고(2026-07-08 2회) 대응.
   완료 신호('완료 브랜드별 누계') 보이면 정상 종료. 실행: python -u kpp_supervisor.py"""
import subprocess, sys, io, time, threading, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "kpp.py")
STALL_SEC = 600          # 10분 무응답 = 행 판정. kpp.py 전 요청에 절대 데드라인 도입 후(2026-07-09)
                         # 진짜 행은 불가능 — 서버 스로틀로 요청이 40s+씩 걸릴 때 오판 방지 위해 240→600
MAX_RESTARTS = 40

state = {"last": time.time(), "finished": False}

def run_once(attempt):
    p = subprocess.Popen([sys.executable, "-u", SCRIPT, "ALL"],
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
            print(f"\n!! [수퍼바이저] {STALL_SEC}s 무응답 → kill 후 재시작 (attempt {attempt})", flush=True)
            p.kill()
            break
    t.join(timeout=10)
    return p.poll()

for attempt in range(1, MAX_RESTARTS+1):
    print(f"=== [수퍼바이저] 실행 {attempt}/{MAX_RESTARTS} ===", flush=True)
    rc = run_once(attempt)
    if state["finished"]:
        print("=== [수퍼바이저] 스크랩 정상 완료 ===", flush=True); break
    if rc == 0 and time.time()-state["last"] <= STALL_SEC:
        print("=== [수퍼바이저] 프로세스 정상 종료 ===", flush=True); break
    time.sleep(5)
else:
    print("!! [수퍼바이저] 최대 재시작 도달 — 확인 필요", flush=True)
