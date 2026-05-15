import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright

import subprocess
import socket
import urllib.request
import urllib.error

# Playwright async API + Uvicorn trên Windows thường lỗi khởi chạy (subprocess/event loop).
# Chạy sync API trong thread riêng tránh xung đột.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright_fb")


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _launch_detached_chrome_and_connect(p):
    """Mở trình duyệt thật qua tiến trình tách biệt và kết nối CDP để browser không bị tắt khi script xong."""
    user_data_dir = os.path.abspath("chrome_profile")
    os.makedirs(user_data_dir, exist_ok=True)
    
    port = _find_free_port()
    cdp_url = f"http://127.0.0.1:{port}"
    
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    ]
    
    exe_path = None
    for cp in chrome_paths:
        if os.path.exists(cp):
            exe_path = cp
            break
            
    if not exe_path:
        raise Exception("Không tìm thấy Chrome mở độc lập.")

    # Detach: Mở process độc lập khỏi server python
    subprocess.Popen(
        [
            exe_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check"
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Chờ tiến trình CDP sẵn sàng
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{cdp_url}/json/version", timeout=1)
            time.sleep(1)
            break
        except Exception:
            time.sleep(0.5)
            
    browser = p.chromium.connect_over_cdp(cdp_url)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    return browser, context, {"channel": "chrome detached"}, cdp_url





def _connect_existing_chrome_over_cdp(p):
    """
    Kết nối vào Chrome đang chạy với --remote-debugging-port.
    Mục tiêu: không tự bật thêm cửa sổ trình duyệt mới.
    """
    cdp_url = (os.environ.get("AUTO_SALE_XE_CHROME_CDP_URL") or "").strip() or "http://127.0.0.1:9222"
    browser = p.chromium.connect_over_cdp(cdp_url)
    # Ưu tiên context/tab có sẵn để bám đúng cửa sổ Chrome user đang dùng.
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.pages[0] if context.pages else context.new_page()
    return browser, context, page, cdp_url


def _pick_alive_page(context, current_page):
    """Nếu page hiện tại bị đóng, chọn page còn sống trong context."""
    try:
        if current_page is not None and not current_page.is_closed():
            return current_page
    except Exception:
        pass
    try:
        # Lấy page cuối cùng còn sống (FB hay mở tab mới khi checkpoint/auth)
        for p in reversed(context.pages or []):
            try:
                if not p.is_closed():
                    return p
            except Exception:
                continue
    except Exception:
        pass
    return current_page


def _try_click_facebook_try_another_way(page):
    """Khi kẹt màn 'Kiểm tra thông báo trên thiết bị khác', FB có nút chuyển sang SMS/mã khác."""
    for label in ("Thử cách khác", "Try another way", "Try Another Way"):
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count() == 0:
                continue
            el = btn.first
            if el.is_visible(timeout=600):
                el.click(no_wait_after=True)
                time.sleep(1.5)
                return
        except Exception:
            continue


def _facebook_url_still_security_flow(url: str) -> bool:
    u = url.lower()
    # Tránh khớp nhầm chuỗi "oauth" trong query không liên quan; vẫn bắt đường dẫn OAuth thật.
    return any(
        x in u
        for x in (
            "login.php",
            "/login",
            "two_step",
            "two_factor",
            "checkpoint",
            "auth_platform",
            "/oauth",
            "oauth.php",
            "recover",
            "device_based",
            "cookie_settings",
        )
    )


def _cookies_indicate_facebook_session(page) -> bool:
    """FB thường set c_user + xs khi đã phiên; đôi khi chỉ thấy qua document.cookie hoặc một trong hai."""
    try:
        for c in page.context.cookies():
            name = (c.get("name") or "").strip()
            val = (c.get("value") or "").strip()
            if name in ("c_user", "xs") and val:
                return True
    except Exception:
        pass
    try:
        dc = page.evaluate("() => document.cookie || ''")
        if "c_user=" in dc or "xs=" in dc:
            return True
    except Exception:
        pass
    return False


def _login_password_field_visible(page) -> bool:
    try:
        loc = page.locator('input[name="pass"]').first
        return loc.is_visible(timeout=400)
    except Exception:
        return False


def _facebook_main_ui_visible(page) -> bool:
    """Một trong các dấu hiệu giao diện đã đăng nhập (FB hay đổi class, ưu tiên aria)."""
    selectors = (
        'div[aria-label="Create"]',
        'div[aria-label="Tạo"]',
        '[aria-label="Create post"]',
        '[aria-label="Tạo bài viết"]',
        '[aria-label="Account"]',
        '[aria-label="Tài khoản"]',
        "svg.x19dipnz",
        '[data-testid="left_nav_menu_list"]',
        '[data-testid="new-post-button"]',
        '[data-testid="search-global-typeahead-input"]',
        'input[placeholder*="Search Facebook"]',
        'input[placeholder*="Tìm kiếm trên Facebook"]',
    )
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=600):
                return True
        except Exception:
            continue
    return False


def _facebook_feed_or_composer_heuristic(page) -> bool:
    """Dự phòng khi aria/testid đổi: văn bản composer / khối bài trong feed."""
    try:
        return bool(
            page.evaluate(
                """() => {
          const t = (document.body && document.body.innerText) || '';
          if (t.includes("Bạn đang nghĩ gì")) return true;
          if (t.includes("What's on your mind")) return true;
          if (t.includes("Write something")) return true;
          if (document.querySelector('[role="main"] [role="article"]')) return true;
          if (document.querySelector('[data-pagelet^="FeedStories"]')) return true;
          if (document.querySelector('[data-pagelet="ProfileTilesFeed_0"]')) return true;
          return false;
        }"""
            )
        )
    except Exception:
        return False


def _facebook_session_ready(page) -> bool:
    """Coi như đã vào FB hợp lệ: không còn màn bảo mật/đăng nhập + có cookie phiên hoặc thấy UI chính."""
    try:
        url = page.url
    except Exception:
        return False
    if "facebook.com" not in url.lower():
        return False
    if _facebook_url_still_security_flow(url):
        return False
    # Cookie phiên là tín hiệu đáng tin nhất; ưu tiên trước ô mật khẩu (FB đôi khi còn input ẩn trong DOM).
    if _cookies_indicate_facebook_session(page):
        return True
    if _login_password_field_visible(page):
        return False
    return _facebook_main_ui_visible(page) or _facebook_feed_or_composer_heuristic(page)


def _wait_until_facebook_home(page):
    """Chờ đăng nhập xong: cookie c_user + URL sạch, hoặc UI trang chủ; xen kẽ 'Thử cách khác'."""
    while True:
        try:
            if _facebook_session_ready(page):
                return
        except Exception:
            pass
        _try_click_facebook_try_another_way(page)
        time.sleep(2)


from services.db import save_groups, get_all_groups

def _auto_post_to_groups_sync(target_urls, delay_seconds, content, image_paths, auto_fetch=False, ai_filter=False):
    if image_paths is None:
        image_paths = []

    if not target_urls and not auto_fetch:
        return (
            "⚠️ Chưa có URL nhóm/tường hợp lệ. Hãy nhập ít nhất một dòng link trong ô danh sách."
        )

    with sync_playwright() as p:
        browser = None
        context = None
        connected_cdp = False
        try:
            note = ""
            use_existing = (os.environ.get("AUTO_SALE_XE_USE_EXISTING_CHROME") or "").strip().lower() in (
                "1",
                "true",
                "yes",
            )
            if use_existing:
                try:
                    browser, context, page, cdp_url = _connect_existing_chrome_over_cdp(p)
                    connected_cdp = True
                    note = f"<br><i>(Đang bám vào Chrome đang mở sẵn qua CDP: {cdp_url}. Tool sẽ không tự mở cửa sổ mới.)</i><br>"
                except Exception as e:
                    note = f"<br><i>(Không bám được Chrome đang mở sẵn qua CDP: {e}. Sẽ fallback sang chế độ mở trình duyệt tự động.)</i><br>"

            if not connected_cdp:
                browser, context, launch_opts, cdp_url = _launch_detached_chrome_and_connect(p)
                if launch_opts.get("channel"):
                    note = f"<br><i>(Đang dùng trình duyệt chính có lưu trữ phiên, chạy nền độc lập: {launch_opts['channel']})</i><br>"
                connected_cdp = True # Trick Playwright not to close the original browser
                page = context.pages[0] if context.pages else context.new_page()

            # FB có thể tự mở tab mới (checkpoint/auth/accountscenter). Bắt sự kiện để luôn bám tab mới nhất.
            state = {"page": page}

            def _on_new_page(p):
                state["page"] = p

            try:
                context.on("page", _on_new_page)
            except Exception:
                pass
            # 0 = không giới hạn — cần khi FB chuyển 2FA/checkpoint (click login chờ navigation rất lâu).
            state["page"].set_default_timeout(0)
            state["page"].set_default_navigation_timeout(0)

            msg = f"🤖 Khởi động Playwright (với {len(target_urls)} nhóm mục tiêu).{note}\n"

            page = _pick_alive_page(context, state["page"])
            state["page"] = page
            page.goto("https://www.facebook.com/")
            # Theo yêu cầu: người dùng đăng nhập thủ công, tool chỉ tự động từ trang chủ.
            # (Áp dụng cho cả chế độ A và B để tránh lỗi tab bị FB đóng khi click Login.)
            msg += (
                "🔐 Vui lòng đăng nhập thủ công trên cửa sổ trình duyệt đang được điều khiển.\n"
                "<br><i>Khi bạn vào được trang chủ Facebook (newsfeed), tool sẽ tự chạy tiếp để mở group và đăng bài.</i><br>"
            )
            try:
                # Trong khi chờ, luôn bám page/tab còn sống (FB có thể đổi tab).
                while True:
                    state["page"] = _pick_alive_page(context, state["page"])
                    if state["page"] is None:
                        time.sleep(1.0)
                        continue
                    if _facebook_session_ready(state["page"]):
                        break
                    _try_click_facebook_try_another_way(state["page"])
                    time.sleep(2)
            except Exception:
                msg += "⏳ [Cảnh báo] Không thấy trang chủ sau khi đăng nhập. Vẫn tiếp tục thực thi.\n"

            page = state["page"]
            if auto_fetch:
                msg += f"<br>🔍 Đang bắt đầu quét danh sách Nhóm Facebook mới nhất từ /groups/joins/...<br>"
                try:
                    page.goto("https://www.facebook.com/groups/joins/", wait_until="domcontentloaded")
                    time.sleep(3)
                    # Cuộn để tải thêm nhóm
                    for _ in range(5):
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        time.sleep(1.5)
                    
                    group_elements = page.locator('a[href*="/groups/"]').all()
                    fetched_groups = []
                    for el in group_elements:
                        href = el.get_attribute("href")
                        if href and "/groups/" in href and "joins" not in href and "discover" not in href:
                            text = el.inner_text().strip()
                            if text and len(text) > 3:
                                clean_href = href.split("?")[0]
                                if not clean_href.endswith("/"):
                                    clean_href += "/"
                                if not any(g['url'] == clean_href for g in fetched_groups):
                                    fetched_groups.append({'url': clean_href, 'name': text})
                    
                    save_groups(fetched_groups)
                    
                    # Ưu tiên lấy hết các group có trong db ra để post sau khi đã quét xong
                    all_db_groups = get_all_groups()
                    if all_db_groups:
                        target_urls = [g['url'] for g in all_db_groups]
                    else:
                        target_urls = [g['url'] for g in fetched_groups]
                        
                    msg += f"✅ Đã lưu và tải được {len(target_urls)} nhóm vào danh sách tự động chạy.<br>"
                except Exception as e:
                    msg += f"❌ Lỗi khi tự động quét nhóm mới: {e}<br>"

            success_count = 0
            for idx, raw_url in enumerate(target_urls):
                # Luôn bám page còn sống / tab mới nhất trước mỗi group.
                state["page"] = _pick_alive_page(context, state["page"])
                page = state["page"]
                target_url = raw_url
                if target_url and not target_url.startswith("http"):
                    target_url = "https://" + target_url

                msg += f"<br>🔹 <b>Nhóm {idx + 1}:</b> {target_url}<br>"
                try:
                    try:
                        page.goto(target_url, wait_until="domcontentloaded")
                    except Exception:
                        pass
                    time.sleep(2.5)


                    page.evaluate(
                        """() => {
                        const spans = Array.from(document.querySelectorAll('span'));
                        const target = spans.find(s => s.innerText.includes('Bạn đang nghĩ gì') || s.innerText.includes('Write something'));
                        if(target) target.click();
                    }"""
                    )
                    time.sleep(1)

                    try:
                        fallback_box = page.locator(
                            'div[data-pagelet="GroupInlineComposer"] div[role="button"], div[data-pagelet="ProfileComposer"] div[role="button"]'
                        ).first
                        if fallback_box.is_visible(timeout=1000):
                            fallback_box.click()
                            time.sleep(1)
                    except Exception:
                        pass

                    if image_paths:
                        # Facebook group post usually has an input[type=file][multiple].
                        # The modal is often appended at the end of the DOM, so .last is safer than .first
                        multi_file_input = page.locator('input[type="file"][multiple]')
                        if multi_file_input.count() > 0:
                            multi_file_input.last.set_input_files(image_paths)
                        else:
                            file_input = page.locator('input[type="file"][accept*="image"]')
                            if file_input.count() > 0:
                                try:
                                    file_input.last.set_input_files(image_paths)
                                except Exception:
                                    # Fallback: if it does not accept multiple files, upload only the first one
                                    logger_msg = f"Warning: single file input only, uploading 1 image."
                                    print(logger_msg)
                                    file_input.last.set_input_files([image_paths[0]])
                        time.sleep(2.5)

                    # The post modal is injected at the end of the DOM, so .last is required to focus the active modal.
                    text_area = page.locator('div[role="textbox"][contenteditable="true"]').last
                    text_area.click(timeout=3000)
                    page.keyboard.insert_text(content)
                    time.sleep(1)

                    submit_btn = page.locator('div[aria-label="Post"], div[aria-label="Đăng"]').last
                    if submit_btn.is_visible():
                        submit_btn.click()
                    else:
                        page.evaluate(
                            """() => {
                            const dialogs = document.querySelectorAll('div[role="dialog"]');
                            const root = dialogs.length > 0 ? dialogs[dialogs.length - 1] : document;
                            const spans = Array.from(root.querySelectorAll('span')).reverse();
                            const btn = spans.find(s => s.innerText === 'Đăng' || s.innerText === 'Post');
                            if (btn && btn.closest('div[role="button"]')) {
                                btn.closest('div[role="button"]').click();
                            } else if (dialogs.length > 0) {
                                // Fallback using standard DOM search if dialog scoping fails
                                const allSpans = Array.from(document.querySelectorAll('span')).reverse();
                                const fallbackBtn = allSpans.find(s => s.innerText === 'Đăng' || s.innerText === 'Post');
                                if (fallbackBtn && fallbackBtn.closest('div[role="button"]')) {
                                    fallbackBtn.closest('div[role="button"]').click();
                                }
                            }
                        }"""
                        )

                    time.sleep(3)
                    success_count += 1
                    msg += '➡️ <span style="color:#34d399;">Thành công!</span><br>'

                except Exception as e:
                    print(f"Lỗi khi post vào {target_url}: {e}")
                    import traceback
                    traceback.print_exc()
                    err_detail = str(e).split('\\n')[0][:100].replace('<', '&lt;').replace('>', '&gt;')
                    msg += f'➡️ <span style="color:#f87171;">Lỗi thao tác: Bỏ qua Group này ({err_detail}).</span><br>'

                if idx < len(target_urls) - 1:
                    msg += f"<i>(Chờ {delay_seconds} giây trước khi qua Nhóm tiếp theo...)</i><br>"
                    time.sleep(delay_seconds)

            msg += f"<br>✅ Đã chạy xong danh sách! ({success_count}/{len(target_urls)} nhóm thành công)."
            return msg
        finally:
            # Nếu bám vào Chrome có sẵn, không được đóng browser/context (sẽ tắt Chrome của user).
            if connected_cdp:
                pass


async def auto_post_to_groups(target_urls, delay_seconds, content, image_paths=None, auto_fetch=False, ai_filter=False):
    """
    Đăng bài lên nhiều URL Facebook bằng Playwright (cửa sổ thật khi có thể, để xử lý checkpoint/2FA).
    """
    if image_paths is None:
        image_paths = []

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            _executor,
            _auto_post_to_groups_sync,
            target_urls,
            delay_seconds,
            content,
            image_paths,
            auto_fetch,
            ai_filter
        )

    except Exception as e:
        return (
            " Lỗi Playwright: "
            f"{e}<br><small>Nếu lỗi khi đăng nhập: hoàn tất 2FA/checkpoint trên cửa sổ trình duyệt, rồi chạy lại. "
            "Cài Chromium: <code>python -m playwright install chromium</code>.</small>"
        )
