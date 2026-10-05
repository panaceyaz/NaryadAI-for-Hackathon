import os
import json
from pathlib import Path
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn
from google import genai

app = FastAPI(title="NaryadAI Backend")

BASE_DIR = Path(__file__).resolve().parent

# ===== GEMINI =====
GEMINI_API_KEY = None
env_path = BASE_DIR / "gemini.env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("GEMINI_API_KEY="):
            GEMINI_API_KEY = line.split("=", 1)[1].strip()
            break
    print(f"[NaryadAI] Ключ загружен: {bool(GEMINI_API_KEY)}")
else:
    print(f"[NaryadAI] Файл не найден: {env_path}")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ===== ХРАНИЛИЩЕ =====
tasks_db = [
    {
        "id": 101,
        "category": "FIRE",
        "equipment": "Цех №1 ➔ Компрессор Boge",
        "description": "Плановая замена масляного фильтра",
        "section": "Б",
        "worker": "Иванов А. В.",
        "duration": "120",
        "status": "in_progress",
        "checklist_passed": True,
        "ai_score": None,
        "ai_verdict": None
    }
]


# ===== СТРАНИЦА =====
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open(BASE_DIR / "site.html", "r", encoding="utf-8") as f:
        return f.read()


# ===== API =====
@app.get("/api/tasks")
async def get_tasks():
    return {"tasks": tasks_db}


@app.post("/api/tasks/create")
async def create_task(
    category: str = Form(...),
    equipment: str = Form(...),
    description: str = Form(...),
    section: str = Form(...),
    worker: str = Form(...),
    duration: str = Form(...),
    checklist_passed: bool = Form(...)
):
    if not checklist_passed:
        raise HTTPException(status_code=400, detail="Инструктаж не подтвержден!")

    new_id = 101 if not tasks_db else max(t["id"] for t in tasks_db) + 1

    new_task = {
        "id": new_id,
        "category": category,
        "equipment": equipment,
        "description": description,
        "section": section,
        "worker": worker,
        "duration": duration,
        "status": "new",
        "checklist_passed": checklist_passed,
        "ai_score": None,
        "ai_verdict": None,
        "ai_checks": None,
    }
    tasks_db.append(new_task)
    return {"status": "success", "task": new_task}


@app.post("/api/tasks/{task_id}/status")
async def update_status(task_id: int, status: str = Form(...)):
    task = next((t for t in tasks_db if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Наряд не найден")
    task["status"] = status
    return {"status": "success", "task": task}


# ===== GEMINI-АНАЛИЗ ФОТО =====
@app.post("/api/tasks/{task_id}/analyze")
async def analyze_photo(task_id: int, photo: UploadFile = File(...)):
    task = next((t for t in tasks_db if t["id"] == task_id), None)
    if not task:
        print(f"[NaryadAI] Создаю задачу #{task_id} на лету")
        task = {
            "id": task_id,
            "category": "UNKNOWN",
            "equipment": "Не указано",
            "description": "",
            "section": "-",
            "worker": "-",
            "duration": "0",
            "status": "review",
            "checklist_passed": True,
            "ai_score": None,
            "ai_verdict": None,
        }
        tasks_db.append(task)

    if not gemini_client:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY не настроен на сервере")

    image_bytes = await photo.read()
    mime = photo.content_type or "image/jpeg"

    prompt = """Ты — система контроля охраны труда на промышленном объекте.
Проанализируй фото рабочего места и проверь наличие СИЗ.

ВАЖНО: Анализируй ТОЛЬКО реальные фотографии людей на рабочем месте.
Если на фото:
- нет человека,
- изображён текст, документ, схема, чертёж, учебник,
- непонятное изображение,

то ВСЕ проверки должны быть ok=false, conf=0, score=0,
а verdict = "На фото не обнаружен работник. Анализ СИЗ невозможен."

Верни СТРОГО JSON без markdown, без пояснений:
{
  "helmet":  {"ok": true/false, "conf": 0-100},
  "vest":    {"ok": true/false, "conf": 0-100},
  "gloves":  {"ok": true/false, "conf": 0-100},
  "fencing": {"ok": true/false, "conf": 0-100},
  "score": 0-100,
  "verdict": "краткий вердикт на русском",
  "detections": [
    {"label": "Каска", "box_2d": [ymin, xmin, ymax, xmax]}
  ]
}

Правила:
- score = сумма уверенно обнаруженных СИЗ: каска 40, жилет 30, перчатки 20, ограждение 10
- Уверенность conf должна быть честной: если не видишь чётко — снижай
- Если объект не виден в кадре — ok=false, conf=0
- box_2d — только для РЕАЛЬНО обнаруженных объектов на человеке
- verdict пиши по-русски, кратко, для мастера
"""

    try:
        import time
        print(f"[NaryadAI] Отправляю фото в Gemini: {len(image_bytes)} bytes, mime={mime}")

        response = None
        last_error = None

        for attempt in range(3):
            try:
                response = gemini_client.models.generate_content(
                    model="gemini-3.5-flash",
                    contents=[
                        {"role": "user", "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": mime, "data": image_bytes}},
                        ]},
                    ],
                    config={"response_mime_type": "application/json", "temperature": 0.2},
                )
                break
            except Exception as inner_e:
                last_error = inner_e
                err_str = str(inner_e)
                if "503" in err_str or "UNAVAILABLE" in err_str or "overloaded" in err_str.lower() or "high demand" in err_str.lower():
                    print(f"[NaryadAI] Попытка {attempt + 1}/3 — 503. Ждём 3 сек...")
                    time.sleep(3)
                    continue
                raise

        if response is None:
            raise Exception(f"Gemini не ответил после 3 попыток: {last_error}")

        raw = response.text.strip()
        print("=== RAW GEMINI RESPONSE ===")
        print(raw[:1000])
        print("===========================")

        # Убираем markdown-обёртку, если она есть
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        result = json.loads(raw)
        print(f"[NaryadAI] JSON разобран. Score={result.get('score')}")

        checks = [
            {"name": "Каска",           "ok": bool(result["helmet"]["ok"]),  "conf": int(result["helmet"]["conf"])},
            {"name": "Жилет",           "ok": bool(result["vest"]["ok"]),    "conf": int(result["vest"]["conf"])},
            {"name": "Перчатки",        "ok": bool(result["gloves"]["ok"]),  "conf": int(result["gloves"]["conf"])},
            {"name": "Ограждение зоны", "ok": bool(result["fencing"]["ok"]), "conf": int(result["fencing"]["conf"])},
        ]

        boxes = []
        for det in result.get("detections", []):
            box = det.get("box_2d")
            if not box or len(box) != 4:
                continue
            ymin, xmin, ymax, xmax = box
            label = det.get("label", "Объект")
            cls = "bbox-helmet" if "каск" in label.lower() else (
                  "bbox-vest"   if "жилет" in label.lower() else "bbox-glove")
            boxes.append({
                "label": f"{label} ✓",
                "class": cls,
                "top":    f"{ymin / 10}%",
                "left":   f"{xmin / 10}%",
                "w":      f"{(xmax - xmin) / 10}%",
                "h":      f"{(ymax - ymin) / 10}%",
            })

        # Сохраняем в задачу
        task["ai_score"] = int(result["score"])
        task["ai_checks"] = checks
        task["ai_verdict"] = result["verdict"]
        task["ai_boxes"] = boxes
        task["status"] = "review"

        print(f"[NaryadAI] Возвращаю задачу #{task['id']} с полями ai_score/ai_checks/ai_boxes")

        return {"status": "success", "task": task}

    except json.JSONDecodeError as e:
        import traceback
        print("=== JSON PARSE ERROR ===")
        traceback.print_exc()
        print("RAW был:", repr(raw) if 'raw' in locals() else 'N/A')
        print("========================")
        raise HTTPException(status_code=500, detail=f"ИИ вернул некорректный JSON: {str(e)}")

    except Exception as e:
        import traceback
        print("=== GEMINI ERROR ===")
        traceback.print_exc()
        print("====================")
        raise HTTPException(status_code=500, detail=f"Ошибка ИИ-анализа: {type(e).__name__}: {str(e)}")

# ===== СТАРЫЙ ЭНДПОИНТ (оставлен для совместимости) =====
@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: int, photo: UploadFile = File(None)):
    task = next((t for t in tasks_db if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Наряд не найден")

    task["status"] = "done"
    task["ai_score"] = 98
    task["ai_verdict"] = "СИЗ (каска, жилет) обнаружены. Зона ограждена."

    return {"status": "success", "task": task}


# ===== ЗАПУСК =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
