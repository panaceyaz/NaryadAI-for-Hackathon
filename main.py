from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="НарядAI Backend")

# Временное хранилище в памяти для хакатона (вместо БД)
tasks_db = []

@app.get("/", response_class=HTMLResponse)
async def read_index():
    """Отдает основной HTML-файл при заходе на сайт"""
    with open("site.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/tasks/create")
async def create_task(equipment: str = Form(...), description: str = Form(...), worker: str = Form(...)):
    """Принимает данные от Мастера и создает новый наряд"""
    new_task = {
        "id": len(tasks_db) + 1,
        "equipment": equipment,
        "description": description,
        "worker": worker,
        "status": "new",  # new -> in_progress -> done
        "ai_score": None,
        "ai_verdict": None
    }
    tasks_db.append(new_task)
    return {"status": "success", "task": new_task}

@app.get("/api/tasks")
async def get_tasks():
    """Возвращает список всех задач для Канбан-доски"""
    return {"tasks": tasks_db}

@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: int, parts: str = Form(...), photo: UploadFile = File(None)):
    """Принимает отчет Рабочего и запускает ИИ-анализ"""
    task = next((t for t in tasks_db if t["id"] == task_id), None)
    if not task:
        return {"status": "error", "message": "Задача не найдена"}

    # --- ЗДЕСЬ ПОДКЛЮЧАЕТСЯ ЛОГИКА ИИ (OpenAI API / VLM / Gemini) ---
    # Для демонстрации делаем эмуляцию ИИ-оценки на основе списанных деталей
    ai_score = "5/5"
    ai_verdict = f"ИИ подтверждает замену. Списанные материалы ({parts}) соответствуют нормативу."

    task["status"] = "done"
    task["ai_score"] = ai_score
    task["ai_verdict"] = ai_verdict

    return {
        "status": "success",
        "ai_score": ai_score,
        "ai_verdict": ai_verdict
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)