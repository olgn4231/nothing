function setProgressUI(pct, label, indeterminate) {
    const wrap = document.getElementById('progressWrap');
    const bar = document.getElementById('progressBar');
    const lbl = document.getElementById('progressLabel');
    wrap.style.display = 'block';
    lbl.textContent = label || '';
    bar.classList.toggle('indeterminate', !!indeterminate);
    if (!indeterminate) {
        bar.style.width = `${Math.min(100, Math.max(0, pct))}%`;
    }
}

function hideProgressUI() {
    const wrap = document.getElementById('progressWrap');
    const bar = document.getElementById('progressBar');
    wrap.style.display = 'none';
    bar.classList.remove('indeterminate');
    bar.style.width = '0%';
}

async function readAutomationStream(formData, onEvent) {
    const response = await fetch('/api/run_automation_stream', {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        let errText = `HTTP ${response.status}`;
        try {
            const j = await response.json();
            if (j.detail) errText = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
        } catch {
            errText = await response.text();
        }
        throw new Error(errText);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split('\n\n');
        buffer = chunks.pop() || '';
        for (const block of chunks) {
            parseSseBlock(block, onEvent);
        }
    }
    if (buffer.trim()) {
        for (const block of buffer.split('\n\n')) {
            parseSseBlock(block, onEvent);
        }
    }
}

function parseSseBlock(block, onEvent) {
    const line = block.trim();
    if (!line.startsWith('data:')) return;
    const jsonStr = line.slice(5).trim();
    if (!jsonStr) return;
    let data;
    try {
        data = JSON.parse(jsonStr);
    } catch {
        return;
    }
    onEvent(data);
}

document.getElementById('automatorForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const submitBtn = document.getElementById('submitBtn');
    const btnText = document.getElementById('btnText');
    const loader = document.getElementById('loader');
    const statusBox = document.getElementById('statusBox');

    submitBtn.disabled = true;
    btnText.textContent = 'Đang chạy…';
    loader.style.display = 'block';

    statusBox.style.display = 'none';
    hideProgressUI();
    setProgressUI(0, '⚙️ Đang gửi dữ liệu lên server…', false);

    const formData = new FormData(e.target);

    try {
        let finalResult = null;

        await readAutomationStream(formData, (data) => {
            if (data.type === 'progress') {
                setProgressUI(data.pct ?? 0, data.label || '', data.indeterminate);
            } else if (data.type === 'done') {
                finalResult = data;
                setProgressUI(100, '✅ Hoàn tất.', false);
            } else if (data.type === 'error') {
                throw new Error(data.message || 'Lỗi không xác định');
            }
        });

        if (!finalResult) {
            throw new Error('Kết nối kết thúc sớm — không nhận được kết quả cuối.');
        }

        statusBox.style.display = 'block';
        statusBox.style.color = '#34d399';
        statusBox.style.background = 'rgba(16, 185, 129, 0.1)';
        statusBox.style.borderColor = 'rgba(16, 185, 129, 0.2)';
        const generated =
            finalResult.generated_content != null ? String(finalResult.generated_content) : '';
        statusBox.innerHTML = `✅ <b>Tự động hóa hoàn tất!</b><br>${finalResult.message}<br><br><b>Bài viết AI tạo ra:</b><br><i style="color:#e4e4e7">"${generated.replace(/\n/g, '<br>')}"</i>`;
    } catch (error) {
        hideProgressUI();
        statusBox.style.display = 'block';
        statusBox.style.color = '#f87171';
        statusBox.style.background = 'rgba(248, 113, 113, 0.1)';
        statusBox.style.borderColor = 'rgba(248, 113, 113, 0.2)';
        statusBox.innerHTML = `❌ <b>Lỗi:</b> ${error.message}`;
    } finally {
        submitBtn.disabled = false;
        btnText.textContent = '🚀 Bước 2: Bắt Đầu Đăng Bài FB';
        loader.style.display = 'none';
    }
});



/* Tabs Switching */
function switchTab(tabId) {
    document.querySelectorAll('.tab-pane').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    
    document.getElementById('tab-' + tabId).style.display = 'block';
    if (tabId === 'dashboard') {
        document.getElementById('btnTabDashboard').classList.add('active');
        loadDashboardStats();
    } else {
        document.getElementById('btnTabAutomation').classList.add('active');
    }
}

/* Dashboard Loader */
async function loadDashboardStats() {
    try {
        const res = await fetch('/api/dashboard_stats');
        const data = await res.json();
        document.getElementById('dbTotalGroups').innerText = data.total_groups || 0;
        
        const tbody = document.getElementById('groupTableBody');
        tbody.innerHTML = '';
        if (data.groups && data.groups.length > 0) {
            data.groups.forEach(g => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td style="padding:10px; border-bottom:1px solid rgba(255,255,255,0.05);">${g.name}</td>
                    <td style="padding:10px; border-bottom:1px solid rgba(255,255,255,0.05);"><a href="${g.url}" target="_blank" style="color:#818cf8; text-decoration:none;">Link</a></td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="2" style="padding:10px; text-align:center; color:#a1a1aa;">Chưa có dữ liệu. Hãy chạy Automation với tuỳ chọn "Cào danh sách" để lấy.</td></tr>';
        }
    } catch (e) {
        console.error("Lỗi tải dashboard", e);
    }
}


/* UX check box */
document.getElementById('auto_fetch_groups').addEventListener('change', function() {
    const txtUrl = document.getElementById('fb_target_url');
    if (this.checked) {
        txtUrl.disabled = true;
        txtUrl.placeholder = "Hệ thống sẽ tự động sử dụng danh sách trong CSDL hoặc quét mới...";
        txtUrl.style.opacity = '0.5';
    } else {
        txtUrl.disabled = false;
        txtUrl.placeholder = "https://www.facebook.com/groups/xxxxx\nhttps://www.facebook.com/truongquocbao";
        txtUrl.style.opacity = '1';
    }
});



// init loading dashboard if active
if (document.getElementById('tab-dashboard').style.display !== 'none') {
    loadDashboardStats();
}
