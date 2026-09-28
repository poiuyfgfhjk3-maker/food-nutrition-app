import os
import io
import shutil
import base64
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
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
from app.services.island_service import (
    determine_guardian, calculate_island_environment, get_next_meal_advice, YOUTH_RECOMMENDED
)
from app.services.allergen_service import (
    MFDS_ALLERGENS, predict_allergens_for_food, 
    merge_ai_and_rule_allergens, aggregate_meal_allergens
)
from scripts.import_mfds_xlsx import (
    import_excel_to_sqlite, import_csv_to_sqlite, import_file_to_sqlite, 
    sync_all_raw_files, classify_mfds_category
)

app = FastAPI(title="식약처 영양성분 기반 AI 음식 분석기 & Nutri-Island", version="3.1.0")

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
            cat = classify_mfds_category(row[0])
            source_stats.append({"source": row[0], "count": row[1], "category": cat})
        conn.close()
    except Exception:
        pass

    # 4대 식약처 DB 슬롯 상태 집계
    SLOT_DEFS = [
        {"id": "cooked", "name": "음식DB (외식/조리)", "pattern": ["음식", "외식", "조리"], "description": "일반음식점, 외식 및 조리식품 19,617건"},
        {"id": "processed", "name": "가공식품DB", "pattern": ["가공"], "description": "가공식품 및 즉석조리식품 80,000+건"},
        {"id": "raw_agri", "name": "농·축·수산물DB (원재료성)", "pattern": ["농", "축", "수산", "성분표", "원재료"], "description": "원재료 농축수산물 영양성분 30,000+건"},
        {"id": "functional", "name": "건강기능식품DB", "pattern": ["건강기능", "건기식", "기능"], "description": "식약처 인증 건강기능식품 영양성분"}
    ]
    slots_status = []
    for s_def in SLOT_DEFS:
        matching_sources = [
            s for s in source_stats 
            if any(p in s["source"].lower() for p in s_def["pattern"])
        ]
        total_cnt = sum(s["count"] for s in matching_sources)
        slots_status.append({
            "slot_id": s_def["id"],
            "id": s_def["id"],
            "name": s_def["name"],
            "status": "loaded" if total_cnt > 0 else "empty",
            "is_loaded": total_cnt > 0,
            "count": total_cnt,
            "total_count": total_cnt,
            "sources": matching_sources,
            "description": s_def["description"]
        })

    return {
        "total_foods": stats["total_foods"],
        "top_categories": stats["top_categories"],
        "source_stats": source_stats,
        "slots_status": slots_status,
        "has_api_key": bool(api_key),
        "api_key_masked": f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else ("설정됨" if api_key else "미설정")
    }

@app.post("/api/set-api-key")
def update_api_key(req: ApiKeyRequest):
    if not req.api_key or len(req.api_key.strip()) < 10:
        raise HTTPException(status_code=400, detail="유효한 API 키를 입력해 주세요.")
    set_runtime_api_key(req.api_key.strip())
    return {"success": True, "message": "API 키가 성공적으로 설정되었습니다."}

@app.get("/api/allergens/list")
def get_allergen_list():
    """식품의약품안전처 「식품등의 표시기준」 19종 법정 알레르기 유발물질 마스터 목록"""
    return MFDS_ALLERGENS

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
    calc_data = calculate_nutrition(food, req.grams)
    calc_data["allergens"] = predict_allergens_for_food(food.get("name", ""))
    return calc_data

class ChangeFoodRequest(BaseModel):
    food_id: Optional[int] = None
    food_name: Optional[str] = None
    grams: float = 200.0

@app.post("/api/change-food")
def change_food_item(req: ChangeFoodRequest):
    """식약처 34.5만 건 DB에서 사용자가 선택한 어떤 음식이든 영양성분 및 19종 알레르기 즉각 재산출"""
    food = None
    if req.food_id:
        food = get_food_by_id(req.food_id)
    elif req.food_name:
        candidates = search_foods(req.food_name.strip(), limit=1)
        if candidates:
            food = candidates[0]

    if not food:
        raise HTTPException(status_code=404, detail="해당 음식을 찾을 수 없습니다.")

    calc_data = calculate_nutrition(food, req.grams)
    calc_data["allergens"] = predict_allergens_for_food(food.get("name", ""))
    calc_data["visual_cues"] = f"식약처 공식 데이터베이스({food.get('source', '식약처')}) 기준"
    calc_data["candidates"] = search_foods(food.get("name", ""), limit=4)
    calc_data["confidence"] = 1.0
    return calc_data

@app.post("/api/analyze")
async def analyze_image(
    file: UploadFile = File(...),
    food_hint: Optional[str] = Form(None)
):
    contents = await file.read()
    mime_type = file.content_type or "image/jpeg"
    filename = file.filename or ""

    vision_result = analyze_food_image(
        contents, 
        mime_type=mime_type, 
        filename=filename, 
        user_hint=food_hint or ""
    )
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
        ai_allergens = item.get("allergens", [])

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

        # 식약처 19종 알레르기 유발물질 AI 및 규칙 앙상블 분석
        rule_allergens = predict_allergens_for_food(detected_name, visual_cues)
        food_allergens = merge_ai_and_rule_allergens(ai_allergens, rule_allergens)
        calc_data["allergens"] = food_allergens

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

    # 전체 식단 알레르기 유발물질 종합 집계
    total_allergens = aggregate_meal_allergens(matched_items)

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
        "total_allergens": total_allergens,
        "api_error": vision_result.get("api_error")
    }

@app.post("/api/upload-csv")
@app.post("/api/upload-data")
async def upload_mfds_data(
    files: List[UploadFile] = File(...),
    slot_category: Optional[str] = Form(None)
):
    """식약처 4대 DB CSV 또는 XLSX 파일 다중 일괄/개별 업로드 및 자동 적재"""
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
    os.makedirs(upload_dir, exist_ok=True)

    results = []
    total_imported = 0

    for file in files:
        fname = file.filename or ""
        if not fname.lower().endswith(('.csv', '.txt', '.xlsx', '.xls')):
            results.append({
                "filename": fname,
                "status": "error",
                "error": "지원되지 않는 파일 형식입니다. (.csv, .xlsx, .xls만 지원)"
            })
            continue

        temp_path = os.path.join(upload_dir, fname)
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        try:
            count = import_file_to_sqlite(temp_path, source_name=fname)
            cat = slot_category or classify_mfds_category(fname)
            total_imported += count
            results.append({
                "filename": fname,
                "category": cat,
                "count": count,
                "status": "success"
            })
        except Exception as e:
            results.append({
                "filename": fname,
                "status": "error",
                "error": str(e)
            })

    return {
        "success": True,
        "total_files": len(results),
        "total_imported": total_imported,
        "details": results,
        "message": f"성공적으로 {total_imported:,}건의 식약처 영양 및 알러지 데이터가 등록되었습니다!"
    }

@app.post("/api/upload-excel")
async def upload_mfds_excel(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.xlsx', '.xls', '.csv', '.txt')):
        raise HTTPException(status_code=400, detail="오직 .csv, .xlsx 또는 .xls 파일만 지원됩니다.")

    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
    os.makedirs(upload_dir, exist_ok=True)
    temp_path = os.path.join(upload_dir, file.filename)

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        count = import_file_to_sqlite(temp_path, source_name=file.filename)
        cat = classify_mfds_category(file.filename)
        return {
            "success": True,
            "filename": file.filename,
            "category": cat,
            "imported_count": count,
            "message": f"성공적으로 {count:,}건의 영양 데이터(무기질/비타민 포함)가 등록되었습니다!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 파일 변환 중 오류 발생: {str(e)}")

@app.post("/api/sync-raw-files")
def sync_raw_folder():
    res = sync_all_raw_files()
    return res

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_INDEX = os.path.join(PROJECT_ROOT, "frontend", "public", "index.html")
FRONTEND_ISLAND = os.path.join(PROJECT_ROOT, "frontend", "public", "island.html")
FRONTEND_ASSETS = os.path.join(PROJECT_ROOT, "frontend", "public", "assets")
os.makedirs(FRONTEND_ASSETS, exist_ok=True)
app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS), name="assets")

@app.get("/assets/{file_name}")
def serve_asset(file_name: str):
    file_path = os.path.join(FRONTEND_ASSETS, file_name)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Asset not found")

@app.get("/", response_class=HTMLResponse)
def serve_index():
    if os.path.exists(FRONTEND_INDEX):
        with open(FRONTEND_INDEX, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Frontend UI not ready</h1>"

@app.get("/island", response_class=HTMLResponse)
@app.get("/island.html", response_class=HTMLResponse)
def serve_island():
    if os.path.exists(FRONTEND_ISLAND):
        with open(FRONTEND_ISLAND, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Nutri-Island UI not ready</h1>"

class IslandEnvironmentRequest(BaseModel):
    cumulative_nutrition: Dict[str, Any]
    meal_count: int = 1

@app.post("/api/island/environment")
def get_island_env(req: IslandEnvironmentRequest):
    return calculate_island_environment(req.cumulative_nutrition, req.meal_count)

class DemoMealRequest(BaseModel):
    sample_id: str
    meal_type: str = "lunch"

@app.post("/api/island/demo-meal")
def analyze_demo_meal(req: DemoMealRequest):
    samples = {
        "balanced_lunch": {
            "name": "영양 가득 불고기 백반 (달걀말이 & 시금치나물)",
            "foods": ["소불고기", "달걀말이", "시금치나물", "현미밥"],
            "nutrition": {
                "calories": 580.0, "carbohydrates": 75.0, "protein": 32.0, "fat": 16.0,
                "sugar": 6.5, "sodium": 620.0,
                "minerals": {"calcium": 180.0, "iron": 3.8, "magnesium": 75.0, "potassium": 580.0, "zinc": 2.4},
                "vitamins": {"fiber": 6.2, "vitamin_a": 220.0, "vitamin_c": 18.0, "vitamin_d": 1.2, "folate": 85.0}
            }
        },
        "protein_breakfast": {
            "name": "든든한 달걀 토스트와 따뜻한 우유",
            "foods": ["달걀후라이", "우유", "식빵"],
            "nutrition": {
                "calories": 420.0, "carbohydrates": 45.0, "protein": 22.0, "fat": 14.0,
                "sugar": 11.0, "sodium": 480.0,
                "minerals": {"calcium": 310.0, "iron": 2.1, "magnesium": 42.0, "potassium": 360.0, "zinc": 1.8},
                "vitamins": {"fiber": 2.1, "vitamin_a": 160.0, "vitamin_c": 2.0, "vitamin_d": 2.5, "folate": 45.0}
            }
        },
        "fruit_snack": {
            "name": "상큼한 딸기 & 바나나 과일 보울",
            "foods": ["딸기", "바나나"],
            "nutrition": {
                "calories": 160.0, "carbohydrates": 38.0, "protein": 2.2, "fat": 0.6,
                "sugar": 22.0, "sodium": 4.0,
                "minerals": {"calcium": 28.0, "iron": 0.7, "magnesium": 36.0, "potassium": 480.0, "zinc": 0.3},
                "vitamins": {"fiber": 4.5, "vitamin_a": 15.0, "vitamin_c": 65.0, "vitamin_d": 0.0, "folate": 40.0}
            }
        },
        "sweet_snack": {
            "name": "달콤한 초코도넛과 콜라",
            "foods": ["초코도넛", "콜라"],
            "nutrition": {
                "calories": 490.0, "carbohydrates": 78.0, "protein": 4.5, "fat": 18.0,
                "sugar": 46.0, "sodium": 320.0,
                "minerals": {"calcium": 35.0, "iron": 1.2, "magnesium": 18.0, "potassium": 110.0, "zinc": 0.4},
                "vitamins": {"fiber": 1.0, "vitamin_a": 10.0, "vitamin_c": 0.0, "vitamin_d": 0.0, "folate": 8.0}
            }
        }
    }

    sample = samples.get(req.sample_id, samples["balanced_lunch"])
    guardian = determine_guardian(sample["nutrition"])
    next_advice = get_next_meal_advice(req.meal_type, sample["nutrition"])

    # 데모 식단 알레르기 19종 지식베이스 연동
    sample_allergens = aggregate_meal_allergens([
        {"name": f, "allergens": predict_allergens_for_food(f)} for f in sample["foods"]
    ])

    return {
        "success": True,
        "sample_name": sample["name"],
        "meal_type": req.meal_type,
        "nutrition": sample["nutrition"],
        "guardian": guardian,
        "next_meal_advice": next_advice,
        "foods_summary": sample["foods"],
        "allergens": sample_allergens
    }

@app.post("/api/island/analyze-meal")
async def analyze_island_meal(request: Request):
    content_type = request.headers.get("content-type", "")
    contents = b""
    mime_type = "image/jpeg"
    filename = ""
    meal_type = "lunch"
    food_hint = ""

    if "application/json" in content_type:
        try:
            body = await request.json()
            meal_type = body.get("meal_type", "lunch")
            food_hint = body.get("food_hint", "")
            filename = body.get("filename", "")
            img_b64 = body.get("image_base64", "")
            if img_b64:
                if "," in img_b64:
                    header, img_b64 = img_b64.split(",", 1)
                    if "image/png" in header:
                        mime_type = "image/png"
                contents = base64.b64decode(img_b64)
        except Exception as e:
            print(f"[WARN] Island JSON 파싱 실패: {e}")
    else:
        form = await request.form()
        meal_type = form.get("meal_type", "lunch")
        food_hint = form.get("food_hint", "")
        file_obj = form.get("file")
        if file_obj and hasattr(file_obj, "read"):
            contents = await file_obj.read()
            mime_type = getattr(file_obj, "content_type", "image/jpeg") or "image/jpeg"
            filename = getattr(file_obj, "filename", "") or ""

    vision_result = analyze_food_image(
        contents, 
        mime_type=mime_type, 
        filename=filename, 
        user_hint=food_hint
    )
    detected_foods = vision_result.get("foods", [])

    tot = {
        "calories": 0.0, "carbohydrates": 0.0, "protein": 0.0, "fat": 0.0,
        "sugar": 0.0, "sodium": 0.0, "fiber": 0.0, "calcium": 0.0,
        "iron": 0.0, "magnesium": 0.0, "potassium": 0.0, "zinc": 0.0,
        "vitamin_a": 0.0, "vitamin_c": 0.0, "vitamin_d": 0.0, "folate": 0.0
    }
    matched_names = []
    food_objects = []

    for item in detected_foods:
        detected_name = item.get("food_name", "")
        est_grams = float(item.get("estimated_grams", 100.0))
        ai_allergens = item.get("allergens", [])

        candidates = search_foods(detected_name, limit=3)
        if candidates:
            best = candidates[0]
            calc_data = calculate_nutrition(best, est_grams)
            real_name = best.get("name", detected_name)
            matched_names.append(real_name)
        else:
            calc_data = {
                "calories": round(est_grams * 1.5, 1),
                "carbohydrates": round(est_grams * 0.2, 1),
                "protein": round(est_grams * 0.1, 1),
                "fat": round(est_grams * 0.05, 1),
                "sugar": round(est_grams * 0.02, 1),
                "sodium": round(est_grams * 2.0, 1),
                "minerals": {"calcium": 25.0, "iron": 0.8, "magnesium": 20.0, "potassium": 150.0, "zinc": 0.5},
                "vitamins": {"fiber": 1.5, "vitamin_a": 10.0, "vitamin_c": 5.0, "vitamin_d": 0.0, "folate": 15.0}
            }
            real_name = detected_name
            matched_names.append(detected_name)

        # 알레르기 분석 및 앙상블
        rule_allergens = predict_allergens_for_food(detected_name, "")
        food_allergens = merge_ai_and_rule_allergens(ai_allergens, rule_allergens)
        calc_data["name"] = real_name
        calc_data["allergens"] = food_allergens
        food_objects.append(calc_data)

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

    total_nutrition = {
        "calories": round(tot["calories"], 1),
        "carbohydrates": round(tot["carbohydrates"], 1),
        "protein": round(tot["protein"], 1),
        "fat": round(tot["fat"], 1),
        "sugar": round(tot["sugar"], 1),
        "sodium": round(tot["sodium"], 1),
        "minerals": {k: round(tot[k], 1) for k in ["calcium", "iron", "magnesium", "potassium", "zinc"]},
        "vitamins": {k: round(tot[k], 1) for k in ["fiber", "vitamin_a", "vitamin_c", "vitamin_d", "folate"]}
    }

    guardian = determine_guardian(total_nutrition)
    next_advice = get_next_meal_advice(meal_type, total_nutrition)
    total_allergens = aggregate_meal_allergens(food_objects)

    return {
        "success": True,
        "is_mock": vision_result.get("is_mock", False),
        "meal_type": meal_type,
        "nutrition": total_nutrition,
        "guardian": guardian,
        "next_meal_advice": next_advice,
        "foods_summary": matched_names if matched_names else ["인식된 음식"],
        "allergens": total_allergens
    }
