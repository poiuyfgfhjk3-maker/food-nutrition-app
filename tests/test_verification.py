import sys
import os
import unittest
import io

# Add backend to sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from fastapi.testclient import TestClient
from app.main import app
from app.services.allergen_service import MFDS_ALLERGENS, predict_allergens_for_food
from scripts.import_mfds_xlsx import classify_mfds_category, load_csv_safely

class TestNutritionAndAllergyScanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_mfds_19_allergens_master(self):
        """식약처 19종 법정 알레르기 유발물질 마스터 검증"""
        self.assertEqual(len(MFDS_ALLERGENS), 19)
        for meta in MFDS_ALLERGENS:
            self.assertIn("name", meta)
            self.assertIn("legal_definition", meta)
            self.assertIn("common_ingredients", meta)
            self.assertIn("cross_reactivity", meta)
            self.assertIn("clinical_notes", meta)
            self.assertIn("action_guide", meta)

    def test_allergen_prediction_with_proof(self):
        """음식 알러지 예측 시 클릭용 추론 근거(proof) 포함 여부 검증"""
        allergens = predict_allergens_for_food("제육볶음", "돼지고기와 고추장 양념")
        self.assertTrue(len(allergens) > 0)
        
        # 돼지고기(pork)가 검출되었는지 확인
        pork_item = next((a for a in allergens if a["id"] == "pork"), None)
        self.assertIsNotNone(pork_item)
        self.assertIn("proof", pork_item)
        proof = pork_item["proof"]
        self.assertIn("legal_basis", proof)
        self.assertTrue("식품의약품안전처" in proof["legal_basis"] or "식약처" in proof["legal_basis"])
        self.assertIn("detected_reason", proof)

    def test_api_stats_slots(self):
        """GET /api/stats 호출 시 식약처 4대 DB 슬롯 현황(slots_status) 반환 검증"""
        res = self.client.get("/api/stats")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("slots_status", data)
        slots = data["slots_status"]
        self.assertEqual(len(slots), 4)
        slot_ids = [s["slot_id"] for s in slots]
        self.assertIn("cooked", slot_ids)
        self.assertIn("processed", slot_ids)
        self.assertIn("raw_agri", slot_ids)
        self.assertIn("functional", slot_ids)

    def test_api_calculate_nutrition_proof(self):
        """POST /api/calculate 호출 시 영양성분 1:1 수학적 산출 근거(proof_breakdown) 반환 검증"""
        search_res = self.client.get("/api/search?q=비빔밥")
        self.assertEqual(search_res.status_code, 200)
        foods = search_res.json()
        if foods:
            food_id = foods[0]["id"]
            calc_res = self.client.post("/api/calculate", json={"food_id": food_id, "grams": 350.0})
            self.assertEqual(calc_res.status_code, 200)
            data = calc_res.json()
            self.assertIn("proof_breakdown", data)
            proof = data["proof_breakdown"]
            self.assertIn("items", proof)
            self.assertIn("ratio_multiplier", proof)
            item_names = [it["name"] for it in proof["items"]]
            self.assertIn("열량", item_names)
            self.assertIn("칼슘", item_names)
            self.assertIn("철분", item_names)
            self.assertIn("비타민 C", item_names)

    def test_classify_mfds_category(self):
        """식약처 다운로드 파일명 자동 슬롯 분류 검증"""
        self.assertIn("음식", classify_mfds_category("20260828_음식DB_19617건.csv"))
        self.assertIn("가공", classify_mfds_category("통합식품영양성분DB_가공식품.csv"))
        self.assertIn("농", classify_mfds_category("농축수산물_영양데이터.csv"))
        self.assertIn("건강기능", classify_mfds_category("건강기능식품_영양DB.csv"))

    def test_api_upload_csv(self):
        """POST /api/upload-csv 엔드포인트에 4가지 식약처 형식 CSV 업로드 검증"""
        csv_content = (
            "식품코드,식품명,데이터구분명,1회제공량,에너지(kcal),탄수화물(g),단백질(g),지방(g),당류(g),나트륨(mg),식이섬유(g),칼슘(mg),철(mg),칼륨(mg),마그네슘(mg),아연(mg),비타민A(μg RAE),비타민C(mg),비타민D(μg),엽산(μg)\n"
            "TEST001,테스트비빔밥,음식,300,500,70,18,12,5,600,6.5,45,2.1,350,55,1.8,120,15,1.2,65\n"
        )
        files = [("files", ("2026_음식DB_test.csv", io.BytesIO(csv_content.encode('utf-8-sig')), "text/csv"))]
        res = self.client.post("/api/upload-csv", files=files)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertGreaterEqual(data.get("total_imported", 0), 1)

    def test_api_analyze(self):
        """POST /api/analyze 호출 시 비전/음식 분석 결과에 영양 산출근거 및 알러지 추론근거가 모두 포함되는지 검증"""
        dummy_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        files = {"file": ("bibimbap.png", io.BytesIO(dummy_png), "image/png")}
        data = {"food_hint": "비빔밥"}
        res = self.client.post("/api/analyze", files=files, data=data)
        self.assertEqual(res.status_code, 200)
        result = res.json()
        self.assertIn("foods", result)
        self.assertTrue(len(result["foods"]) > 0)
        first_food = result["foods"][0]
        
        # 1. 영양성분 및 미네랄/비타민 검증
        self.assertIn("proof_breakdown", first_food)
        self.assertIn("minerals", first_food)
        self.assertIn("vitamins", first_food)
        self.assertIn("calcium", first_food["minerals"])
        self.assertIn("vitamin_c", first_food["vitamins"])
        
        # 2. 알러지 위험도 및 추론 근거 검증
        self.assertIn("allergens", first_food)
        self.assertIn("total_allergens", result)
        if first_food["allergens"]:
            allergen = first_food["allergens"][0]
            self.assertIn("proof", allergen)
            self.assertIn("legal_basis", allergen["proof"])

if __name__ == "__main__":
    unittest.main()

