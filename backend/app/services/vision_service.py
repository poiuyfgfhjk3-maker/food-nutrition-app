import os
import json
import base64
import requests
from typing import Dict, Any, List

def get_api_key() -> str:
    """환경 변수 또는 .env 파일에서 Gemini API 키 획득"""
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key

    # backend/.env 및 루트 .env 모두 탐색
    paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"),
    ]
    for env_path in paths:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
    return ""

def set_runtime_api_key(new_key: str):
    """실행 중 API 키 저장 및 갱신"""
    os.environ["GEMINI_API_KEY"] = new_key.strip()
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"GEMINI_API_KEY={new_key.strip()}\n")

def analyze_food_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> Dict[str, Any]:
    """
    최신 Gemini Flash Vision 모델을 활용하여
    음식 사진에서 음식 종류와 시각적 부피 기반 그램수(g)를 추정
    """
    api_key = get_api_key()

    if not api_key:
        print("[WARN] GEMINI_API_KEY가 설정되지 않아 체험(Mock) 모드로 분석합니다.")
        return get_mock_analysis_result("API 키가 아직 등록되지 않아 체험 모드로 분석되었습니다.")

    base64_img = base64.b64encode(image_bytes).decode("utf-8")

    prompt = """
당신은 대한민국 최고의 영양학 및 음식 비전 AI 전문가입니다.
제공된 음식 사진을 정밀하게 분석하여 다음 사항을 파악해 주세요:
1. 사진에 담긴 모든 개별 음식/반찬/음료를 식별하세요. (한상차림일 경우 각 메뉴를 분리)
2. 각 음식의 섭취 예상 중량(그램수, g)을 추정하세요.
   - 접시/그릇의 크기, 밥공기, 숟가락 등 주변 물체와의 비율을 감안하여 실제 부피와 밀도를 분석하세요.
   - 식약처 1인분 기준 대비 대략적인 인분 비율(예: 0.5인분, 1.0인분, 1.2인분 등)을 함께 계산하세요.
3. 왜 그렇게 중량을 추정했는지 시각적 근거(visual_cues)를 한국어로 간결하게 설명하세요.

반드시 아래 JSON 포맷으로만 응답해야 합니다:
{
  "diet_summary": "식단 전체에 대한 1줄 요약 (예: 계란후라이와 소고기, 나물이 푸짐하게 담긴 영양 비빔밥)",
  "foods": [
    {
      "food_name": "비빔밥",
      "estimated_grams": 450,
      "serving_ratio": 1.0,
      "visual_cues": "대형 유기그릇에 밥 1공기와 콩나물, 당근, 시금치, 계란후라이가 얹어져 1인분 약 450g으로 추정됩니다.",
      "confidence": 0.96
    }
  ]
}
"""

    # 사용 가능한 최신 모델들 순차 시도
    models = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-flash-latest", "gemini-2.5-flash"]
    last_error = None

    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64_img
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.2
            }
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=25)
            if resp.status_code == 200:
                result_json = resp.json()
                text_content = result_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_content)
                parsed["is_mock"] = False
                parsed["model_used"] = model_name
                return parsed
            else:
                last_error = f"API Error ({resp.status_code}): {resp.text}"
                print(f"[WARN] {model_name} 실패: {last_error}")
        except Exception as e:
            last_error = str(e)
            print(f"[WARN] {model_name} 호출 예외: {e}")

    print(f"[ERROR] Gemini API 호출 실패로 시뮬레이션 모드로 전환합니다: {last_error}")
    
    error_msg = "API 호출에 실패하여 체험 모드로 분석되었습니다."
    if "PERMISSION_DENIED" in str(last_error):
        error_msg = "입력하신 API 키의 접근 권한이 거부되었습니다(PERMISSION_DENIED). Google AI Studio에서 생성한 'AIzaSy...'로 시작하는 올바른 키인지 확인해 주세요."
    elif "404" in str(last_error):
        error_msg = "지원되지 않는 모델 버전입니다."

    mock = get_mock_analysis_result(error_msg)
    mock["api_error"] = error_msg
    return mock

def get_mock_analysis_result(reason: str = "") -> Dict[str, Any]:
    """체험 모드 또는 API 에러 시 반환되는 식약처 DB 연동 대표 식단 데이터 (비빔밥 정식)"""
    return {
        "is_mock": True,
        "api_error": reason,
        "diet_summary": "[체험 모드] 계란후라이와 소고기, 나물을 곁들인 영양 비빔밥 정식",
        "foods": [
            {
                "food_name": "비빔밥",
                "estimated_grams": 420.0,
                "serving_ratio": 1.0,
                "visual_cues": "그릇의 크기와 밥 1공기, 콩나물·시금치·당근 고명 비중을 감안하여 약 420g(1인분)으로 추정했습니다.",
                "confidence": 0.95
            },
            {
                "food_name": "배추김치",
                "estimated_grams": 40.0,
                "serving_ratio": 0.8,
                "visual_cues": "종지에 소량 담긴 반찬용 배추김치 분량(약 40g)입니다.",
                "confidence": 0.92
            }
        ]
    }
