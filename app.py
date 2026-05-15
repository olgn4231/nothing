import asyncio
import json
import os
import threading
import time
import uuid
import webbrowser

import uvicorn
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List, Optional


from services.ads_manager import configure_ads_campaign
from services.fb_poster import auto_post_to_groups
from services.db import get_all_groups, count_groups
from pydantic import BaseModel

# asyncio.to_thread: Python 3.9+
if hasattr(asyncio, "to_thread"):
    _to_thread = asyncio.to_thread
else:

    async def _to_thread(func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

app = FastAPI(title="Auto Sale Xe AI", version="2.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def _sse_event(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


async def save_car_uploads(car_images: Optional[List[UploadFile]]) -> List[str]:
    saved: List[str] = []
    if not car_images:
        return saved
    for image in car_images:
        if not image.filename:
            continue
        base = os.path.basename(image.filename) or "image"
        _, ext = os.path.splitext(base)
        ext = ext if ext.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp") else ""
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.abspath(os.path.join("uploads", unique_name))
        with open(file_path, "wb") as f:
            f.write(await image.read())
        saved.append(file_path)
    return saved


@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/dashboard_stats")
async def dashboard_stats():
    count = count_groups()
    groups = get_all_groups()
    return {"total_groups": count, "groups": groups}


@app.post("/api/run_automation")
async def run_automation(

    fb_target_url: Optional[str] = Form(""),
    post_delay: int = Form(15),
    raw_script: str = Form(""),
    car_segment: str = Form(""),
    final_caption: str = Form(""),
    car_images: Optional[List[UploadFile]] = File(None)
):
    saved_images = await save_car_uploads(car_images)

    content = final_caption.strip() or raw_script.strip()

    # 2. Lên kế hoạch Ads (Tự lấy số dư)
    ads_status = configure_ads_campaign(
        car_segment
    )

    # Xử lý dánh sách URL (loại bỏ dòng văng, khoảng trắng dư)
    url_list = [u.strip() for u in (fb_target_url or "").split('\n') if u.strip()]

    # 3. Playwright đăng bài công khai thực tế (Hàng loạt)
    post_status = await auto_post_to_groups(

        url_list,
        post_delay,
        content,
        image_paths=saved_images
    )

    img_msg = f"<br>📸 Đã tải lên và đính kèm {len(saved_images)} hình ảnh." if saved_images else ""

    return {
        "status": "success",
        "message": f"<b>Chiến dịch Ads:</b><br>{ads_status}<br><br><b>Tiến trình Facebook:</b><br>{post_status}{img_msg}",
        "generated_content": content
    }


@app.post("/api/run_automation_stream")
async def run_automation_stream(

    fb_target_url: Optional[str] = Form(""),
    post_delay: int = Form(15),
    raw_script: str = Form(""),
    car_segment: str = Form(""),
    final_caption: str = Form(""),
    car_images: Optional[List[UploadFile]] = File(None),
    auto_fetch_groups: Optional[str] = Form("false"),
    ai_filter_groups: Optional[str] = Form("false"),
):
    """Cùng logic run_automation nhưng gửi SSE (tiến trình) về client."""
    is_auto_fetch = auto_fetch_groups.lower() == "true"
    is_ai_filter = ai_filter_groups.lower() == "true"

    async def events():
        try:
            yield _sse_event(
                {
                    "type": "progress",
                    "pct": 3,
                    "label": "Đang lưu ảnh tải lên…",
                    "step": "upload",
                    "indeterminate": False,
                }
            )
            saved_images = await save_car_uploads(car_images)
            yield _sse_event(
                {
                    "type": "progress",
                    "pct": 10,
                    "label": f"Đã lưu {len(saved_images)} ảnh.",
                    "step": "upload",
                    "indeterminate": False,
                }
            )

            yield _sse_event(
                {
                    "type": "progress",
                    "pct": 15,
                    "label": "Đang chuẩn bị nội dung bài đăng…",
                    "step": "content",
                    "indeterminate": False,
                }
            )
            content = final_caption.strip() or raw_script.strip()
            yield _sse_event(
                {
                    "type": "progress",
                    "pct": 35,
                    "label": "Đã sinh xong nội dung bài đăng.",
                    "step": "ai",
                    "indeterminate": False,
                }
            )

            yield _sse_event(
                {
                    "type": "progress",
                    "pct": 40,
                    "label": "Đang lên kế hoạch Ads…",
                    "step": "ads",
                    "indeterminate": False,
                }
            )
            ads_status = await _to_thread(configure_ads_campaign, car_segment)
            yield _sse_event(
                {
                    "type": "progress",
                    "pct": 48,
                    "label": "Hoàn tất bước Ads.",
                    "step": "ads",
                    "indeterminate": False,
                }
            )

            url_list = [u.strip() for u in (fb_target_url or "").split("\n") if u.strip()]
            yield _sse_event(
                {
                    "type": "progress",
                    "pct": 52,
                    "label": "Đang mở trình duyệt (Playwright). Đăng nhập / 2FA nếu cần — bước này có thể rất lâu.",
                    "step": "facebook",
                    "indeterminate": True,
                }
            )

            post_status = await auto_post_to_groups(
                url_list,
                post_delay,
                content,
                image_paths=saved_images,
                auto_fetch=is_auto_fetch,
                ai_filter=is_ai_filter
            )

            img_msg = (
                f"<br>📸 Đã tải lên và đính kèm {len(saved_images)} hình ảnh."
                if saved_images
                else ""
            )
            yield _sse_event(
                {
                    "type": "done",
                    "pct": 100,
                    "status": "success",
                    "message": f"<b>Chiến dịch Ads:</b><br>{ads_status}<br><br><b>Tiến trình Facebook:</b><br>{post_status}{img_msg}",
                    "generated_content": content,
                    "indeterminate": False,
                }
            )
        except Exception as e:
            yield _sse_event({"type": "error", "message": str(e)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def open_browser(port: int):
    # Tránh mở hàng loạt tab khi uvicorn reload
    if os.environ.get("UVICORN_WINDOW_OPENED"):
        return
    os.environ["UVICORN_WINDOW_OPENED"] = "1"
    time.sleep(1.5)
    print(f"🚀 Đang mở trình duyệt tại http://127.0.0.1:{port}")
    webbrowser.open(f"http://127.0.0.1:{port}")


def _read_port() -> int:
    raw = os.environ.get("PORT", "8000").strip() or "8000"
    try:
        p = int(raw)
        return p if 1 <= p <= 65535 else 8000
    except ValueError:
        return 8000


if __name__ == "__main__":
    _port = _read_port()
    # Chế độ Debug: Tự động tải lại khi đổi code
    # Nếu muốn tắt reload để ổn định Playwright, đặt AUTO_SALE_XE_RELOAD=0
    _reload_env = os.environ.get("AUTO_SALE_XE_RELOAD", "").strip().lower()
    _reload = _reload_env not in ("0", "false", "no")
    
    if _reload:
        print("🛠️ Đang chạy ở chế độ DEBUG (Auto-reload: ON)")
    else:
        print("🚀 Đang chạy ở chế độ PRODUCTION (Auto-reload: OFF)")

    threading.Thread(target=lambda: open_browser(_port), daemon=True).start()
    uvicorn.run("app:app", host="0.0.0.0", port=_port, reload=_reload, log_level="info")
