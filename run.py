import os
import sys
import webbrowser
import uvicorn

# Windows 콘솔 인코딩 대응
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def main():
    backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
    sys.path.insert(0, backend_dir)

    host = "127.0.0.1"
    port = 8000
    url = f"http://{host}:{port}"

    print("=" * 60)
    print(" [식약처 영양성분 DB 기반 AI 푸드 영양 스캐너 서버 시작]")
    print(f" 접속 주소: {url}")
    print("=" * 60)

    import threading
    def open_browser():
        import time
        time.sleep(1.2)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run("app.main:app", host=host, port=port, reload=False, app_dir=backend_dir)

if __name__ == "__main__":
    main()
