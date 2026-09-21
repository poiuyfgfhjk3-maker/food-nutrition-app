import os
import io
import shutil
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3

from app.services.db_service import (
    init_database, search_foods, get_food_by_id, 
    calculate_nutrition, get_database_stats, DB_PATH, DAILY_RECOMMENDED
)
from app.services.vision_service import (
    analyze_food_image, get_api_key, set_runtime_api_key
)
from scripts.import_mfds_xlsx import import_excel_to_sqlite, sync_all_raw_files

app = FastAPI(title="식약처 영양성분 기반 AI 음식 분석기", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_database()

class RecalculateRequest(BaseModel):
    food_id: int
    grams: float

class ApiKeyRequest(BaseModel):
    api_key: str

@app.get("/api/stats")
def get_stats():
    stats = get_database_stats()
    api_key = get_api_key()

    source_stats = []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT source, COUNT(*) as cnt FROM foods GROUP BY source ORDER BY cnt DESC")
        for row in cursor.fetchall():
            source_stats.append({"source": row[0], "count": row[1]})
        conn.close()
    except Exception:
        pass

    return {
        "total_foods": stats["total_foods"],
        "top_categories": stats["top_categories"],
        "source_stats": source_stats,
        "has_api_key": bool(api_key),
        "api_key_masked": f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else ("설정됨" if api_key else "미설정")
    }

@app.post("/api/set-api-key")
def update_api_key(req: ApiKeyRequest):
    if not req.api_key or len(req.api_key.strip()) < 10:
        raise HTTPException(status_code=400, detail="유효한 API 키를 입력해 주세요.")
    set_runtime_api_key(req.api_key.strip())
    return {"success": True, "message": "API 키가 성공적으로 설정되었습니다."}

@app.get("/api/search")
def search_food_items(q: str = "", limit: int = 15):
    if not q:
        return []
    return search_foods(q, limit=limit)

@app.post("/api/calculate")
def recalculate(req: RecalculateRequest):
    food = get_food_by_id(req.food_id)
    if not food:
        raise HTTPException(status_code=404, detail="식품을 찾을 수 없습니다.")
    return calculate_nutrition(food, req.grams)

@app.post("/api/analyze")
async def analyze_image(file: UploadFile = File(...)):
    contents = await file.read()
    mime_type = file.content_type or "image/jpeg"

    vision_result = analyze_food_image(contents, mime_type)
    detected_foods = vision_result.get("foods", [])

    matched_items = []
    tot = {
        "calories": 0.0, "carbohydrates": 0.0, "protein": 0.0, "fat": 0.0,
        "sugar": 0.0, "sodium": 0.0, "fiber": 0.0, "calcium": 0.0,
        "iron": 0.0, "magnesium": 0.0, "potassium": 0.0, "zinc": 0.0,
        "vitamin_a": 0.0, "vitamin_c": 0.0, "vitamin_d": 0.0, "folate": 0.0
    }

    for item in detected_foods:
        detected_name = item.get("food_name", "")
        est_grams = float(item.get("estimated_grams", 100.0))
        serving_ratio = float(item.get("serving_ratio", 1.0))
        visual_cues = item.get("visual_cues", "")

        candidates = search_foods(detected_name, limit=5)
        
        if candidates:
            best_match = candidates[0]
            calc_data = calculate_nutrition(best_match, est_grams)
            calc_data["detected_name"] = detected_name
            calc_data["visual_cues"] = visual_cues
            calc_data["candidates"] = candidates[:4]
            calc_data["confidence"] = item.get("confidence", 0.9)
        else:
            calc_data = {
                "food_id": None,
                "name": detected_name,
                "detected_name": detected_name,
                "category": "기타",
                "serving_size_ref": 100.0,
                "consumed_grams": est_grams,
                "serving_ratio": serving_ratio,
                "calories": round(est_grams * 1.5, 1),
                "carbohydrates": round(est_grams * 0.2, 1),
                "protein": round(est_grams * 0.1, 1),
                "fat": round(est_grams * 0.05, 1),
                "sugar": round(est_grams * 0.02, 1),
                "sodium": round(est_grams * 2.0, 1),
                "cholesterol": 0.0,
                "saturated_fat": 0.0,
                "trans_fat": 0.0,
                "minerals": {"calcium": 25.0, "iron": 0.8, "magnesium": 20.0, "potassium": 150.0, "zinc": 0.5},
                "vitamins": {"fiber": 1.5, "vitamin_a": 10.0, "vitamin_c": 5.0, "vitamin_d": 0.0, "folate": 15.0},
                "dv_percentages": {},
                "source": "AI 추정치",
                "visual_cues": visual_cues,
                "candidates": []
            }

        matched_items.append(calc_data)

        tot["calories"] += calc_data["calories"]
        tot["carbohydrates"] += calc_data["carbohydrates"]
        tot["protein"] += calc_data["protein"]
        tot["fat"] += calc_data["fat"]
        tot["sugar"] += calc_data["sugar"]
        tot["sodium"] += calc_data["sodium"]

        mins = calc_data.get("minerals", {})
        tot["calcium"] += mins.get("calcium", 0.0)
        tot["iron"] += mins.get("iron", 0.0)
        tot["magnesium"] += mins.get("magnesium", 0.0)
        tot["potassium"] += mins.get("potassium", 0.0)
        tot["zinc"] += mins.get("zinc", 0.0)

        vits = calc_data.get("vitamins", {})
        tot["fiber"] += vits.get("fiber", 0.0)
        tot["vitamin_a"] += vits.get("vitamin_a", 0.0)
        tot["vitamin_c"] += vits.get("vitamin_c", 0.0)
        tot["vitamin_d"] += vits.get("vitamin_d", 0.0)
        tot["folate"] += vits.get("folate", 0.0)

    # 1일 영양소 기준치 대비 전체 비율
    total_dv = {k: round((tot[k] / DAILY_RECOMMENDED[k]) * 100, 1) if DAILY_RECOMMENDED.get(k) else 0.0 for k in tot}

    return {
        "is_mock": vision_result.get("is_mock", False),
        "diet_summary": vision_result.get("diet_summary", "식단 분석 완료"),
        "total_nutrition": {
            "calories": round(tot["calories"], 1),
            "carbohydrates": round(tot["carbohydrates"], 1),
            "protein": round(tot["protein"], 1),
            "fat": round(tot["fat"], 1),
            "sugar": round(tot["sugar"], 1),
            "sodium": round(tot["sodium"], 1),
            "minerals": {
                "calcium": round(tot["calcium"], 1),
                "iron": round(tot["iron"], 2),
                "magnesium": round(tot["magnesium"], 1),
                "potassium": round(tot["potassium"], 1),
                "zinc": round(tot["zinc"], 2),
            },
            "vitamins": {
                "fiber": round(tot["fiber"], 1),
                "vitamin_a": round(tot["vitamin_a"], 1),
                "vitamin_c": round(tot["vitamin_c"], 1),
                "vitamin_d": round(tot["vitamin_d"], 2),
                "folate": round(tot["folate"], 1),
            },
            "dv_percentages": total_dv
        },
        "foods": matched_items,
        "api_error": vision_result.get("api_error")
    }

@app.post("/api/upload-excel")
async def upload_mfds_excel(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="오직 .xlsx 또는 .xls 파일만 지원됩니다.")

    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
    os.makedirs(upload_dir, exist_ok=True)
    temp_path = os.path.join(upload_dir, file.filename)

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        count = import_excel_to_sqlite(temp_path, source_name=file.filename)
        return {
            "success": True,
            "filename": file.filename,
            "imported_count": count,
            "message": f"성공적으로 {count:,}건의 영양 데이터(무기질/비타민 포함)가 등록되었습니다!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"엑셀 변환 중 오류 발생: {str(e)}")

@app.post("/api/sync-raw-files")
def sync_raw_folder():
    res = sync_all_raw_files()
    return res

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_INDEX = os.path.join(PROJECT_ROOT, "frontend", "public", "index.html")

@app.get("/", response_class=HTMLResponse)
def serve_index():
    if os.path.exists(FRONTEND_INDEX):
        with open(FRONTEND_INDEX, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Frontend UI not ready</h1>"
