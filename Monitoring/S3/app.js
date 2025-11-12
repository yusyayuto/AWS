// API GatewayのエンドポイントURL（最後のスラッシュは不要）
const API_BASE_URL = 'https://YOUR_API_ID.execute-api.ap-northeast-1.amazonaws.com/prod';

let allAlerts = [];
let currentFilter = 'all';

// ページ読み込み時の初期化
document.addEventListener('DOMContentLoaded', () => {
    loadAlerts();
    setupFilterButtons();
});

// フィルターボタンのイベント設定
function setupFilterButtons() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            filterButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.dataset.filter;
            renderTable();
        });
    });
}

// アラート一覧を取得
async function loadAlerts() {
    try {
        showMessage('データを読み込んでいます...', 'info');
        
        const response = await fetch(`${API_BASE_URL}/alerts`);
        
        if (!response.ok) {
            throw new Error(`HTTPエラー: ${response.status}`);
        }
        
        const data = await response.json();
        allAlerts = data.alerts || [];
        
        updateStats();
        renderTable();
        clearMessage();
        
    } catch (error) {
        console.error('エラー:', error);
        showMessage(`データの読み込みに失敗しました: ${error.message}`, 'error');
    }
}

// 統計情報を更新
function updateStats() {
    const total = allAlerts.length;
    const pending = allAlerts.filter(a => a.status === 'pending').length;
    const truePositive = allAlerts.filter(a => a.status === 'true_positive').length;
    const falsePositive = allAlerts.filter(a => a.status === 'false_positive').length;
    
    document.getElementById('total-count').textContent = total;
    document.getElementById('pending-count').textContent = pending;
    document.getElementById('true-positive-count').textContent = truePositive;
    document.getElementById('false-positive-count').textContent = falsePositive;
}

// テーブルを描画
function renderTable() {
    const container = document.getElementById('table-container');
    
    let filteredAlerts = allAlerts;
    if (currentFilter !== 'all') {
        filteredAlerts = allAlerts.filter(a => a.status === currentFilter);
    }
    
    if (filteredAlerts.length === 0) {
        container.innerHTML = '<div class="loading">アラートがありません</div>';
        return;
    }
    
    const table = `
        <table>
            <thead>
                <tr>
                    <th>発生日時</th>
                    <th>アラーム名</th>
                    <th>種別</th>
                    <th>ステータス</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
                ${filteredAlerts.map(alert => `
                    <tr>
                        <td>${formatDate(alert.timestamp)}</td>
                        <td>${alert.alarm_name || '-'}</td>
                        <td>${alert.alert_type || '-'}</td>
                        <td>${renderStatusBadge(alert.status)}</td>
                        <td>${renderActionButtons(alert)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = table;
}

// 日時をフォーマット
function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('ja-JP', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// ステータスバッジを描画
function renderStatusBadge(status) {
    const statusMap = {
        'pending': { label: '未判定', class: 'status-pending' },
        'true_positive': { label: '真の異常', class: 'status-true-positive' },
        'false_positive': { label: '誤検知', class: 'status-false-positive' }
    };
    
    const statusInfo = statusMap[status] || { label: status, class: 'status-pending' };
    return `<span class="status-badge ${statusInfo.class}">${statusInfo.label}</span>`;
}

// 操作ボタンを描画
function renderActionButtons(alert) {
    if (alert.status === 'pending') {
        return `
            <button class="action-btn btn-true" onclick="updateStatus('${alert.alert_id}', 'true_positive')">
                真の異常
            </button>
            <button class="action-btn btn-false" onclick="updateStatus('${alert.alert_id}', 'false_positive')">
                誤検知
            </button>
        `;
    }
    return '-';
}

// ステータスを更新
async function updateStatus(alertId, newStatus) {
    try {
        showMessage('更新中...', 'info');
        
        const response = await fetch(`${API_BASE_URL}/alerts/${alertId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status: newStatus })
        });
        
        if (!response.ok) {
            throw new Error(`HTTPエラー: ${response.status}`);
        }
        
        showMessage('ステータスを更新しました', 'success');
        
        // データを再読み込み
        await loadAlerts();
        
    } catch (error) {
        console.error('エラー:', error);
        showMessage(`更新に失敗しました: ${error.message}`, 'error');
    }
}

// メッセージを表示
function showMessage(text, type) {
    const messageDiv = document.getElementById('message');
    messageDiv.className = type;
    messageDiv.textContent = text;
    messageDiv.style.display = 'block';
}

// メッセージをクリア
function clearMessage() {
    const messageDiv = document.getElementById('message');
    messageDiv.style.display = 'none';
}
