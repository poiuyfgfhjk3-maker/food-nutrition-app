import os
import sys
import uvicorn

# Windows 콘솔 인코딩 대응
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def main():
    backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    port_env = os.environ.get("PORT")
    is_cloud = bool(port_env)

    host = os.environ.get("HOST", "0.0.0.0" if is_cloud else "127.0.0.1")
    port = int(port_env) if port_env else 8000
    url = f"http://{host}:{port}"

    print("=" * 60)
    print(" [식약처 영양성분 DB 기반 AI 푸드 영양 스캐너 서버 시작]")
    print(f" 접속 주소: {url}")
    print("=" * 60)

    if not is_cloud and sys.platform == "win32":
        import threading
        def open_browser():
            import time
            import webbrowser
            time.sleep(1.2)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=open_browser, daemon=True).start()

    reload_flag = not is_cloud
    uvicorn.run("app.main:app", host=host, port=port, reload=reload_flag, app_dir=backend_dir)

if __name__ == "__main__":
    main()
