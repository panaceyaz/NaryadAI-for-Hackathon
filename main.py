from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="NaryadAI Backend")

# Хранилище в памяти для хакатона
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

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("site.html", "r", encoding="utf-8") as f:
        return f.read()

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
        "ai_verdict": None
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

@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: int, photo: UploadFile = File(None)):
    task = next((t for t in tasks_db if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Наряд не найден")

    task["status"] = "done"
    task["ai_score"] = 98
    task["ai_verdict"] = "СИЗ (каска, жилет) обнаружены. Зона ограждена."

    return {"status": "success", "task": task}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
