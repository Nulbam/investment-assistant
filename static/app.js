document.addEventListener("DOMContentLoaded", () => {
    console.log("[PAGE] 페이지 로드 완료");

    // 1. /test 페이지(기존 1차 수집기)인 경우 기존 로직 유지
    if (document.getElementById("search-form")) {
        initTestCollectorPage();
    }

    // 2. 메인 3탭 페이지인 경우 탭1·탭2·탭3 초기화
    if (document.querySelector(".tabs-nav")) {
        initTabs();
        initExampleChips();
        initTab1Analysis();
        initTab2Rebalance();
        initTab3Tech();
    }
});

/* ============================================================================
 * 공통 유틸리티
 * ============================================================================ */
function showErrorBox(boxEl, messages) {
    boxEl.innerHTML = "";
    const title = document.createElement("strong");
    title.textContent = "안내 / 오류 발생";
    boxEl.appendChild(title);

    const ul = document.createElement("ul");
    messages.forEach((msg) => {
        const li = document.createElement("li");
        li.textContent = msg;
        ul.appendChild(li);
    });
    boxEl.appendChild(ul);
    boxEl.classList.remove("hidden");
}

function setBotMessageContent(el, text) {
    const raw = text || "";
    if (window.marked && window.DOMPurify) {
        const html = window.marked.parse(raw, { breaks: true, gfm: true });
        el.innerHTML = window.DOMPurify.sanitize(html);
    } else {
        el.textContent = raw;
    }
}

function appendChatMessage(containerEl, role, text) {
    const div = document.createElement("div");
    div.className = `chat-msg ${role}`;
    if (role === "bot") {
        setBotMessageContent(div, text);
    } else {
        div.textContent = text;
    }
    containerEl.appendChild(div);
    containerEl.scrollTop = containerEl.scrollHeight;
    return div;
}

function formatNumber(val, unit = "") {
    if (val === null || val === undefined) return "N/A";
    return `${Number(val).toLocaleString("ko-KR")}${unit}`;
}

function formatMarketCap(val) {
    if (val === null || val === undefined) return "N/A";
    const jo = Math.floor(val / 1_000_000_000_000);
    const eok = Math.round((val % 1_000_000_000_000) / 100_000_000);
    if (jo > 0 && eok > 0) {
        return `${jo.toLocaleString("ko-KR")}조 ${eok.toLocaleString("ko-KR")}억원`;
    }
    if (jo > 0) {
        return `${jo.toLocaleString("ko-KR")}조원`;
    }
    return `${eok.toLocaleString("ko-KR")}억원`;
}

function formatEok(val) {
    if (val === null || val === undefined) return "N/A";
    return Math.round(val / 100_000_000).toLocaleString("ko-KR");
}

/* ============================================================================
 * 탭 전환 & 예시 칩
 * ============================================================================ */
function initTabs() {
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabPanels = document.querySelectorAll(".tab-panel");

    tabBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
            const targetId = btn.dataset.tab;
            tabBtns.forEach((b) => b.classList.remove("active"));
            tabPanels.forEach((p) => p.classList.remove("active"));

            btn.classList.add("active");
            const targetPanel = document.getElementById(targetId);
            if (targetPanel) targetPanel.classList.add("active");

            console.log(`[PAGE] 탭 전환 (tab=${targetId})`);
        });
    });
}

function initExampleChips() {
    document.querySelectorAll(".example-chip").forEach((chip) => {
        chip.addEventListener("click", () => {
            const targetInput = document.getElementById(chip.dataset.target);
            if (targetInput) {
                targetInput.value = chip.dataset.code;
            }
        });
    });
}

/* ============================================================================
 * 탭 1: 종목 심층분석 채팅 (collector.py + Dify 챗봇①)
 * ============================================================================ */
function initTab1Analysis() {
    const searchForm = document.getElementById("tab1-search-form");
    const codeInput = document.getElementById("tab1-code-input");
    const analyzeBtn = document.getElementById("tab1-analyze-btn");
    const useToolCheckbox = document.getElementById("tab1-use-tool");
    const errorBox = document.getElementById("tab1-error");
    const evidenceStatus = document.getElementById("tab1-evidence-status");
    const evidencePlaceholder = document.getElementById("tab1-evidence-placeholder");
    const evidenceBody = document.getElementById("tab1-evidence-body");
    const jsonPreview = document.getElementById("tab1-json-preview");

    const chatMessages = document.getElementById("tab1-chat-messages");
    const chatForm = document.getElementById("tab1-chat-form");
    const chatInput = document.getElementById("tab1-chat-input");
    const chatSendBtn = document.getElementById("tab1-chat-send");
    const resetBtn = document.getElementById("tab1-chat-reset");

    let conversationId = "";
    let currentCode = "";
    let cachedCollectedData = null;

    resetBtn.addEventListener("click", () => {
        conversationId = "";
        chatMessages.innerHTML = "";
        appendChatMessage(chatMessages, "bot", "새 대화를 시작합니다. 상단에서 **종목 조회 및 AI 분석**을 누르거나 질문을 입력해 주세요.");
    });

    // 1. 종목 조회 및 1차 전문가 심층분석 실행
    searchForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const code = codeInput.value.trim();
        const useTool = useToolCheckbox.checked;

        if (!/^\d{6}$/.test(code)) {
            const msg = "종목코드는 6자리 숫자여야 합니다. (예: 000660)";
            console.error(`[ERROR] ${msg}`);
            showErrorBox(errorBox, [msg]);
            return;
        }

        errorBox.classList.add("hidden");
        analyzeBtn.disabled = true;
        chatSendBtn.disabled = true;
        conversationId = "";
        cachedCollectedData = null;
        currentCode = code;

        try {
            let collectedData = null;

            if (useTool) {
                evidenceStatus.textContent = "수집 중...";
                console.log(`[SEARCH] 탭1 종목 데이터 수집 시작 (${code})`);

                const fetchResp = await fetch("/fetch", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ code })
                });
                collectedData = await fetchResp.json();

                if (!collectedData.name) {
                    const errs = collectedData.errors && collectedData.errors.length > 0
                        ? collectedData.errors
                        : ["종목 데이터를 수집하지 못했습니다."];
                    evidenceStatus.textContent = "수집 실패";
                    showErrorBox(errorBox, errs);
                    return;
                }

                cachedCollectedData = collectedData;
                console.log(`[COLLECT] 근거 데이터 수집 완료 (${collectedData.name})`);
                renderTab1Evidence(collectedData);

                if (collectedData.errors && collectedData.errors.length > 0) {
                    showErrorBox(errorBox, collectedData.errors);
                }

                appendChatMessage(chatMessages, "user", `📊 ${collectedData.name} (${code}) 종목 조회 및 전문가 심층 분석 요청`);
            } else {
                evidenceStatus.textContent = "도구 미사용";
                evidenceBody.classList.add("hidden");
                evidencePlaceholder.classList.remove("hidden");
                evidencePlaceholder.textContent = "근거 도구 체크박스가 해제되어 수집 없이 AI에게 직접 질문합니다.";
                jsonPreview.textContent = "{}";
                appendChatMessage(chatMessages, "user", `종목코드 ${code} 분석 요청 (근거 도구 미사용)`);
            }

            const loadingMsg = appendChatMessage(chatMessages, "bot", "전문가 AI가 수집된 데이터를 분석 중입니다...");

            const chatResp = await fetch("/api/analyze-chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    code,
                    query: `${code} 종목에 대한 전문가 심층 분석 리포트를 작성해 주세요.`,
                    use_tool: useTool,
                    is_initial: true,
                    collected_data: collectedData
                })
            });
            const chatData = await chatResp.json();

            if (!chatData.ok) {
                setBotMessageContent(loadingMsg, `오류: ${chatData.error || "AI 분석 응답을 가져오지 못했습니다."}`);
                showErrorBox(errorBox, [chatData.error || "AI 분석 중 오류가 발생했습니다."]);
                return;
            }

            conversationId = chatData.conversation_id || "";
            setBotMessageContent(loadingMsg, chatData.answer || "(빈 응답)");
            chatMessages.scrollTop = chatMessages.scrollHeight;
            console.log("[CHAT] Dify 1차 전문가 심층분석 수신 완료");
        } catch (err) {
            console.error("[ERROR] 탭1 조회 및 분석 중 오류:", err.message);
            showErrorBox(errorBox, ["서버와 통신하는 중 네트워크 오류가 발생했습니다."]);
        } finally {
            analyzeBtn.disabled = false;
            chatSendBtn.disabled = false;
        }
    });

    // 2. 분석 결과를 바탕으로 후속 채팅 이어가기
    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const code = codeInput.value.trim();
        const query = chatInput.value.trim();
        const useTool = useToolCheckbox.checked;

        if (!query) return;
        if (useTool && !/^\d{6}$/.test(code)) {
            const msg = "근거 도구 사용 시 6자리 숫자 종목코드를 입력해야 합니다. (예: 000660)";
            console.error(`[ERROR] ${msg}`);
            showErrorBox(errorBox, [msg]);
            return;
        }

        // 사용자가 조회 버튼 없이 바로 질문했거나 종목코드를 바꾼 경우
        const needFreshFetch = useTool && (!conversationId || currentCode !== code);
        if (currentCode !== code) {
            conversationId = "";
            cachedCollectedData = null;
            currentCode = code;
        }

        errorBox.classList.add("hidden");
        appendChatMessage(chatMessages, "user", query);
        chatInput.value = "";
        chatSendBtn.disabled = true;

        const loadingMsg = appendChatMessage(
            chatMessages,
            "bot",
            needFreshFetch ? "종목 근거 데이터 수집 및 답변 생성 중..." : "이전 분석 맥락을 이어서 답변 작성 중..."
        );

        console.log(`[SEARCH] 탭1 채팅 요청 (code=${code}, use_tool=${useTool}, has_conv=${Boolean(conversationId)})`);

        try {
            const resp = await fetch("/api/analyze-chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    code,
                    query,
                    use_tool: useTool,
                    is_initial: false,
                    conversation_id: conversationId,
                    collected_data: needFreshFetch ? cachedCollectedData : null
                })
            });
            const data = await resp.json();

            if (data.collected_data) {
                cachedCollectedData = data.collected_data;
                console.log(`[COLLECT] 근거 데이터 수집 완료 (${data.collected_data.name})`);
                renderTab1Evidence(data.collected_data);
            }

            if (!data.ok) {
                setBotMessageContent(loadingMsg, `오류: ${data.error || "답변을 가져오지 못했습니다."}`);
                console.error(`[ERROR] ${data.error}`);
                showErrorBox(errorBox, [data.error || "분석 채팅 처리 중 오류가 발생했습니다."]);
                return;
            }

            conversationId = data.conversation_id || conversationId;
            setBotMessageContent(loadingMsg, data.answer || "(빈 응답)");
            chatMessages.scrollTop = chatMessages.scrollHeight;
            console.log("[CHAT] Dify 챗봇 응답 수신 완료");
        } catch (err) {
            setBotMessageContent(loadingMsg, "네트워크 오류가 발생했습니다.");
            console.error("[ERROR] 탭1 요청 중 오류 발생:", err.message);
            showErrorBox(errorBox, ["서버와 통신하는 중 네트워크 오류가 발생했습니다."]);
        } finally {
            chatSendBtn.disabled = false;
        }
    });

    function renderTab1Evidence(d) {
        const snap = d.snapshot || {};
        evidenceStatus.textContent = `${d.name} (${d.code})`;
        evidencePlaceholder.classList.add("hidden");
        evidenceBody.classList.remove("hidden");

        // 1. 스냅샷 헤더
        document.getElementById("tab1-stock-code").textContent = d.code || "-";
        document.getElementById("tab1-stock-name").textContent = d.name || "-";

        const priceEl = document.getElementById("tab1-current-price");
        const rateEl = document.getElementById("tab1-change-rate");
        priceEl.textContent = formatNumber(snap.current_price, "원");
        priceEl.classList.remove("up", "down", "flat");
        rateEl.classList.remove("up", "down", "flat");

        const rate = snap.change_rate;
        if (rate === null || rate === undefined) {
            rateEl.textContent = "N/A";
            rateEl.classList.add("flat");
        } else if (rate > 0) {
            rateEl.textContent = `▲ +${rate.toFixed(2)}%`;
            priceEl.classList.add("up");
            rateEl.classList.add("up");
        } else if (rate < 0) {
            rateEl.textContent = `▼ ${rate.toFixed(2)}%`;
            priceEl.classList.add("down");
            rateEl.classList.add("down");
        } else {
            rateEl.textContent = "0.00%";
            rateEl.classList.add("flat");
        }

        // 2. 투자지표 7종 그리드
        const metricsGrid = document.getElementById("tab1-metrics-grid");
        metricsGrid.innerHTML = "";
        const metrics = [
            ["시가총액", formatMarketCap(snap.market_cap)],
            ["PER", formatNumber(snap.per, "배")],
            ["추정 PER", formatNumber(snap.cns_per, "배")],
            ["PBR", formatNumber(snap.pbr, "배")],
            ["EPS", formatNumber(snap.eps, "원")],
            ["BPS", formatNumber(snap.bps, "원")],
            ["배당수익률", formatNumber(snap.dividend_yield, "%")]
        ];
        metrics.forEach(([label, val]) => {
            const item = document.createElement("div");
            item.className = "metric-item";
            const lbl = document.createElement("span");
            lbl.className = "metric-label";
            lbl.textContent = label;
            const v = document.createElement("span");
            v.className = "metric-value";
            v.textContent = val;
            item.append(lbl, v);
            metricsGrid.appendChild(item);
        });

        // 3. 연간 기업실적분석 표
        const tbody = document.getElementById("tab1-financials-tbody");
        tbody.innerHTML = "";
        const financials = d.financials || [];
        if (financials.length === 0) {
            const tr = document.createElement("tr");
            const td = document.createElement("td");
            td.colSpan = 4;
            td.textContent = "수집된 실적 데이터가 없습니다.";
            td.style.textAlign = "center";
            tr.appendChild(td);
            tbody.appendChild(tr);
        } else {
            financials.forEach((item) => {
                const tr = document.createElement("tr");
                if (item.is_consensus) tr.classList.add("consensus-row");

                const tdP = document.createElement("td");
                tdP.textContent = item.period || "-";
                if (item.is_consensus) {
                    const badge = document.createElement("span");
                    badge.className = "consensus-badge";
                    badge.textContent = "(E) 추정";
                    tdP.appendChild(badge);
                }

                const tdR = document.createElement("td");
                tdR.textContent = formatEok(item.revenue);

                const tdO = document.createElement("td");
                tdO.textContent = formatEok(item.operating_income);
                if (item.operating_income !== null && item.operating_income < 0) tdO.classList.add("down");

                const tdRoe = document.createElement("td");
                tdRoe.textContent = item.roe !== null && item.roe !== undefined ? `${item.roe.toFixed(2)}%` : "N/A";
                if (item.roe !== null && item.roe < 0) tdRoe.classList.add("down");

                tr.append(tdP, tdR, tdO, tdRoe);
                tbody.appendChild(tr);
            });
        }

        // 4. 최신 관련 뉴스 리스트
        const newsUl = document.getElementById("tab1-news-list");
        newsUl.innerHTML = "";
        const newsList = d.news || [];
        if (newsList.length === 0) {
            const li = document.createElement("li");
            li.className = "empty-message";
            li.textContent = "수집된 관련 뉴스가 없습니다.";
            newsUl.appendChild(li);
        } else {
            newsList.forEach((item) => {
                const li = document.createElement("li");
                li.className = "news-item";
                const a = document.createElement("a");
                a.className = "news-title";
                a.href = item.url && (item.url.startsWith("http://") || item.url.startsWith("https://")) ? item.url : "#";
                a.target = "_blank";
                a.rel = "noopener noreferrer";
                a.textContent = item.title || "제목 없음";
                li.appendChild(a);
                if (item.published) {
                    const dt = document.createElement("div");
                    dt.className = "news-date";
                    dt.textContent = item.published;
                    li.appendChild(dt);
                }
                newsUl.appendChild(li);
            });
        }

        jsonPreview.textContent = JSON.stringify(d, null, 2);
    }
}

/* ============================================================================
 * 탭 2: 리밸런싱 도우미 (Dify 없음 · 순수 Python + Chart.js)
 * ============================================================================ */
function initTab2Rebalance() {
    const form = document.getElementById("tab2-form");
    const codesInput = document.getElementById("tab2-codes-input");
    const calcBtn = document.getElementById("tab2-calc-btn");
    const loadingBox = document.getElementById("tab2-loading");
    const errorBox = document.getElementById("tab2-error");
    const resultBox = document.getElementById("tab2-result");

    let weightChart = null;
    let frontierChart = null;

    document.querySelectorAll(".preset-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            codesInput.value = btn.dataset.codes;
        });
    });

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const codes = codesInput.value
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean);

        if (codes.length < 2) {
            const msg = "최소 2개 이상의 종목코드를 쉼표(,)로 구분해 입력해 주세요.";
            console.error(`[ERROR] ${msg}`);
            showErrorBox(errorBox, [msg]);
            return;
        }

        console.log(`[SEARCH] 탭2 리밸런싱 계산 요청 (${codes.join(", ")})`);
        loadingBox.classList.remove("hidden");
        errorBox.classList.add("hidden");
        resultBox.classList.add("hidden");
        calcBtn.disabled = true;

        try {
            const resp = await fetch("/api/rebalance", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ codes })
            });
            const data = await resp.json();

            if (!data.ok) {
                console.error(`[ERROR] ${data.error}`);
                showErrorBox(errorBox, [data.error || "리밸런싱 계산에 실패했습니다."]);
                return;
            }

            console.log(`[COLLECT] FDR 최근 1년 계산 완료 (${data.trading_days}거래일, ${data.simulations}회 시뮬레이션)`);
            renderTab2Result(data);
            resultBox.classList.remove("hidden");
            console.log("[CHART] 리밸런싱 비중 및 효율적 프론티어 차트 렌더링 완료");
        } catch (err) {
            console.error("[ERROR] 탭2 요청 중 오류 발생:", err.message);
            showErrorBox(errorBox, ["서버와 통신하는 중 네트워크 오류가 발생했습니다."]);
        } finally {
            loadingBox.classList.add("hidden");
            calcBtn.disabled = false;
        }
    });

    function renderTab2Result(data) {
        document.getElementById("tab2-period").textContent =
            `분석 기간: ${data.period} (${data.trading_days}거래일 · ${data.simulations.toLocaleString("ko-KR")}회 시뮬레이션)`;

        const rationaleUl = document.getElementById("tab2-rationale");
        rationaleUl.innerHTML = "";
        (data.rationale || []).forEach((txt) => {
            const li = document.createElement("li");
            li.textContent = txt;
            rationaleUl.appendChild(li);
        });

        renderPortCard("tab2-sharpe", data.max_sharpe);
        renderPortCard("tab2-minvol", data.min_volatility);
        renderPortCard("tab2-equal", data.equal_weight);

        // 개별 종목 통계 표
        const tbody = document.getElementById("tab2-stats-tbody");
        tbody.innerHTML = "";
        (data.asset_stats || []).forEach((st) => {
            const tr = document.createElement("tr");
            const tdName = document.createElement("td");
            tdName.textContent = `${st.name} (${st.code})`;
            const tdPrice = document.createElement("td");
            tdPrice.textContent = formatNumber(st.latest_price, "원");
            const tdRet = document.createElement("td");
            tdRet.textContent = `${st.annual_return_pct}%`;
            if (st.annual_return_pct > 0) tdRet.classList.add("up");
            else if (st.annual_return_pct < 0) tdRet.classList.add("down");
            const tdVol = document.createElement("td");
            tdVol.textContent = `${st.annual_volatility_pct}%`;
            const tdMdd = document.createElement("td");
            tdMdd.textContent = `${st.mdd_pct}%`;
            tdMdd.classList.add("down");

            tr.append(tdName, tdPrice, tdRet, tdVol, tdMdd);
            tbody.appendChild(tr);
        });

        // 차트 1: 최대 샤프 비중 도넛 차트
        if (weightChart) weightChart.destroy();
        const wItems = data.max_sharpe.weights || [];
        weightChart = new Chart(document.getElementById("tab2-weight-chart"), {
            type: "doughnut",
            data: {
                labels: wItems.map((w) => `${w.name} (${w.weight_pct}%)`),
                datasets: [{
                    data: wItems.map((w) => w.weight_pct),
                    backgroundColor: ["#2563eb", "#16a34a", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "bottom" } }
            }
        });

        // 차트 2: 효율적 프론티어 산점도
        if (frontierChart) frontierChart.destroy();
        frontierChart = new Chart(document.getElementById("tab2-frontier-chart"), {
            type: "scatter",
            data: {
                datasets: [
                    {
                        label: "시뮬레이션 포트폴리오",
                        data: data.frontier_points || [],
                        backgroundColor: "rgba(100, 116, 139, 0.35)",
                        pointRadius: 3
                    },
                    {
                        label: "최대 샤프 비중",
                        data: [{ x: data.max_sharpe.volatility_pct, y: data.max_sharpe.expected_return_pct }],
                        backgroundColor: "#2563eb",
                        pointRadius: 8
                    },
                    {
                        label: "최소 변동성 비중",
                        data: [{ x: data.min_volatility.volatility_pct, y: data.min_volatility.expected_return_pct }],
                        backgroundColor: "#16a34a",
                        pointRadius: 8
                    },
                    {
                        label: "동일 비중 (1/N)",
                        data: [{ x: data.equal_weight.volatility_pct, y: data.equal_weight.expected_return_pct }],
                        backgroundColor: "#f59e0b",
                        pointRadius: 7
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { title: { display: true, text: "연 변동성 (%)" } },
                    y: { title: { display: true, text: "연 기대수익률 (%)" } }
                }
            }
        });
    }

    function renderPortCard(prefix, port) {
        const metricsEl = document.getElementById(`${prefix}-metrics`);
        const weightsEl = document.getElementById(`${prefix}-weights`);
        metricsEl.innerHTML = "";
        weightsEl.innerHTML = "";

        const mLines = [
            `연 기대수익률: ${port.expected_return_pct}%`,
            `연 변동성: ${port.volatility_pct}% | 샤프지수: ${port.sharpe_ratio}`,
            `1년 최대낙폭(MDD): ${port.mdd_pct}%`
        ];
        mLines.forEach((line) => {
            const div = document.createElement("div");
            div.textContent = line;
            metricsEl.appendChild(div);
        });

        (port.weights || []).forEach((w) => {
            const li = document.createElement("li");
            const nameSpan = document.createElement("span");
            nameSpan.textContent = `${w.name} (${w.code})`;
            const valSpan = document.createElement("strong");
            valSpan.textContent = `${w.weight_pct}%`;
            li.append(nameSpan, valSpan);
            weightsEl.appendChild(li);
        });
    }
}

/* ============================================================================
 * 탭 3: 기술지표 차트 + 숨은 숫자 주입 Dify 챗봇③
 * ============================================================================ */
function initTab3Tech() {
    const form = document.getElementById("tab3-form");
    const codeInput = document.getElementById("tab3-code-input");
    const loadBtn = document.getElementById("tab3-load-btn");
    const loadingBox = document.getElementById("tab3-loading");
    const errorBox = document.getElementById("tab3-error");
    const resultBox = document.getElementById("tab3-result");

    const chatMessages = document.getElementById("tab3-chat-messages");
    const chatForm = document.getElementById("tab3-chat-form");
    const chatInput = document.getElementById("tab3-chat-input");
    const chatSendBtn = document.getElementById("tab3-chat-send");
    const resetBtn = document.getElementById("tab3-chat-reset");

    let currentSummary = null;
    let currentCode = "";
    let conversationId = "";
    let priceChart = null;
    let rsiChart = null;
    let macdChart = null;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const code = codeInput.value.trim();

        if (!/^\d{6}$/.test(code)) {
            const msg = "종목코드는 6자리 숫자여야 합니다. (예: 000660)";
            console.error(`[ERROR] ${msg}`);
            showErrorBox(errorBox, [msg]);
            return;
        }

        console.log(`[SEARCH] 탭3 기술지표 계산 요청 (${code})`);
        loadingBox.classList.remove("hidden");
        errorBox.classList.add("hidden");
        resultBox.classList.add("hidden");
        loadBtn.disabled = true;

        try {
            const resp = await fetch("/api/indicators", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code })
            });
            const data = await resp.json();

            if (!data.ok) {
                console.error(`[ERROR] ${data.error}`);
                showErrorBox(errorBox, [data.error || "기술지표 계산에 실패했습니다."]);
                return;
            }

            currentSummary = data.latest_summary;
            currentCode = data.code;
            conversationId = "";
            console.log(`[COLLECT] 기술지표 계산 완료 (${data.name}, RSI14=${currentSummary.rsi14})`);

            renderTab3Charts(data);
            resultBox.classList.remove("hidden");
            console.log("[CHART] 주가·MA·볼린저·RSI·MACD 차트 렌더링 완료");
        } catch (err) {
            console.error("[ERROR] 탭3 조회 중 오류 발생:", err.message);
            showErrorBox(errorBox, ["서버와 통신하는 중 네트워크 오류가 발생했습니다."]);
        } finally {
            loadingBox.classList.add("hidden");
            loadBtn.disabled = false;
        }
    });

    resetBtn.addEventListener("click", () => {
        conversationId = "";
        chatMessages.innerHTML = "";
        appendChatMessage(chatMessages, "bot", "새 대화를 시작합니다. 차트의 지표 수치에 대해 질문해 주세요.");
    });

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const query = chatInput.value.trim();
        if (!query) return;

        if (!currentSummary) {
            showErrorBox(errorBox, ["먼저 종목코드로 차트 및 지표를 계산해 주세요."]);
            return;
        }

        errorBox.classList.add("hidden");
        appendChatMessage(chatMessages, "user", query);
        chatInput.value = "";
        chatSendBtn.disabled = true;

        const loadingMsg = appendChatMessage(chatMessages, "bot", "계산된 지표 수치를 기반으로 설명을 작성 중...");

        try {
            const resp = await fetch("/api/tech-chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    code: currentCode,
                    query,
                    latest_summary: currentSummary,
                    conversation_id: conversationId
                })
            });
            const data = await resp.json();

            if (!data.ok) {
                setBotMessageContent(loadingMsg, `오류: ${data.error || "답변을 가져오지 못했습니다."}`);
                console.error(`[ERROR] ${data.error}`);
                return;
            }

            conversationId = data.conversation_id || conversationId;
            setBotMessageContent(loadingMsg, data.answer || "(빈 응답)");
            chatMessages.scrollTop = chatMessages.scrollHeight;
            console.log("[CHAT] Dify 지표해석기 응답 수신 완료");
        } catch (err) {
            loadingMsg.textContent = "네트워크 오류가 발생했습니다.";
            console.error("[ERROR] 탭3 채팅 중 오류 발생:", err.message);
        } finally {
            chatSendBtn.disabled = false;
        }
    });

    function renderTab3Charts(data) {
        const s = data.latest_summary;
        const ser = data.series;

        document.getElementById("tab3-stock-title").textContent = `${data.name} (${data.code}) 최신 기술지표`;
        document.getElementById("tab3-latest-date").textContent = `기준일: ${s.date}`;

        const summaryBar = document.getElementById("tab3-summary-bar");
        summaryBar.innerHTML = "";
        const badges = [
            ["종가", formatNumber(s.close, "원")],
            ["MA 5 / 20", `${formatNumber(s.ma5)} / ${formatNumber(s.ma20)}`],
            ["MA 60", formatNumber(s.ma60, "원")],
            ["RSI (14)", s.rsi14 !== null ? `${s.rsi14}` : "N/A"],
            ["MACD / Signal", `${s.macd} / ${s.macd_signal}`],
            ["볼린저 상/하단", `${formatNumber(s.bb_upper)} / ${formatNumber(s.bb_lower)}`]
        ];
        badges.forEach(([label, val]) => {
            const item = document.createElement("div");
            item.className = "metric-item";
            const lbl = document.createElement("span");
            lbl.className = "metric-label";
            lbl.textContent = label;
            const v = document.createElement("span");
            v.className = "metric-value";
            v.textContent = val;
            item.append(lbl, v);
            summaryBar.appendChild(item);
        });

        // 1. 주가 + MA + 볼린저밴드 차트
        if (priceChart) priceChart.destroy();
        priceChart = new Chart(document.getElementById("tab3-price-chart"), {
            type: "line",
            data: {
                labels: ser.dates,
                datasets: [
                    { label: "종가", data: ser.close, borderColor: "#0f172a", borderWidth: 2, pointRadius: 0 },
                    { label: "MA5", data: ser.ma5, borderColor: "#ef4444", borderWidth: 1.3, pointRadius: 0 },
                    { label: "MA20", data: ser.ma20, borderColor: "#2563eb", borderWidth: 1.3, pointRadius: 0 },
                    { label: "MA60", data: ser.ma60, borderColor: "#16a34a", borderWidth: 1.3, pointRadius: 0 },
                    { label: "BB 상단", data: ser.bb_upper, borderColor: "#94a3b8", borderDash: [4, 4], borderWidth: 1, pointRadius: 0 },
                    { label: "BB 하단", data: ser.bb_lower, borderColor: "#94a3b8", borderDash: [4, 4], borderWidth: 1, pointRadius: 0 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false }
            }
        });

        // 2. RSI(14) 차트
        if (rsiChart) rsiChart.destroy();
        rsiChart = new Chart(document.getElementById("tab3-rsi-chart"), {
            type: "line",
            data: {
                labels: ser.dates,
                datasets: [
                    { label: "RSI(14)", data: ser.rsi14, borderColor: "#8b5cf6", borderWidth: 2, pointRadius: 0 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: { y: { min: 0, max: 100 } }
            }
        });

        // 3. MACD 차트
        if (macdChart) macdChart.destroy();
        macdChart = new Chart(document.getElementById("tab3-macd-chart"), {
            type: "bar",
            data: {
                labels: ser.dates,
                datasets: [
                    { type: "line", label: "MACD", data: ser.macd, borderColor: "#2563eb", borderWidth: 1.8, pointRadius: 0 },
                    { type: "line", label: "Signal", data: ser.macd_signal, borderColor: "#f59e0b", borderWidth: 1.5, pointRadius: 0 },
                    {
                        type: "bar",
                        label: "Histogram",
                        data: ser.macd_hist,
                        backgroundColor: (ser.macd_hist || []).map((v) => (v >= 0 ? "rgba(22, 163, 74, 0.5)" : "rgba(239, 68, 68, 0.5)"))
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }
}

/* ============================================================================
 * 기존 1차 수집기 (/test) 전용 초기화 (보존)
 * ============================================================================ */
function initTestCollectorPage() {
    const searchForm = document.getElementById("search-form");
    const codeInput = document.getElementById("stock-code-input");
    const searchBtn = document.getElementById("search-btn");
    const exampleBtns = document.querySelectorAll(".example-btn");
    const loadingBox = document.getElementById("loading-box");
    const errorBox = document.getElementById("error-box");
    const resultSection = document.getElementById("result-section");

    exampleBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
            const code = btn.dataset.code;
            codeInput.value = code;
            fetchStockData(code);
        });
    });

    searchForm.addEventListener("submit", (e) => {
        e.preventDefault();
        fetchStockData(codeInput.value.trim());
    });

    async function fetchStockData(code) {
        if (!/^\d{6}$/.test(code)) {
            const msg = "종목코드는 6자리 숫자여야 합니다. (예: 000660)";
            console.error(`[ERROR] 수집 중 오류 발생 (${msg})`);
            showErrorBox(errorBox, [msg]);
            resultSection.classList.add("hidden");
            return;
        }

        console.log(`[SEARCH] 종목 수집 요청 시작 (${code})`);
        loadingBox.classList.remove("hidden");
        errorBox.classList.add("hidden");
        resultSection.classList.add("hidden");
        searchBtn.disabled = true;

        try {
            const response = await fetch("/fetch", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code })
            });
            const data = await response.json();

            if (!data.name) {
                const errs = data.errors && data.errors.length > 0 ? data.errors : ["종목 데이터를 불러오지 못했습니다."];
                console.error("[ERROR] 수집 중 오류 발생:", errs);
                showErrorBox(errorBox, errs);
                return;
            }

            if (data.errors && data.errors.length > 0) {
                showErrorBox(errorBox, data.errors);
            }

            document.getElementById("stock-code").textContent = data.code || "-";
            document.getElementById("stock-name").textContent = data.name || "-";
            const snap = data.snapshot || {};
            const priceEl = document.getElementById("current-price");
            const rateEl = document.getElementById("change-rate");
            priceEl.textContent = formatNumber(snap.current_price, "원");
            priceEl.classList.remove("up", "down", "flat");
            rateEl.classList.remove("up", "down", "flat");

            const rate = snap.change_rate;
            if (rate === null || rate === undefined) {
                rateEl.textContent = "N/A";
                rateEl.classList.add("flat");
            } else if (rate > 0) {
                rateEl.textContent = `▲ +${rate.toFixed(2)}%`;
                priceEl.classList.add("up");
                rateEl.classList.add("up");
            } else if (rate < 0) {
                rateEl.textContent = `▼ ${rate.toFixed(2)}%`;
                priceEl.classList.add("down");
                rateEl.classList.add("down");
            } else {
                rateEl.textContent = "0.00%";
                rateEl.classList.add("flat");
            }

            document.getElementById("market-cap").textContent = formatMarketCap(snap.market_cap);
            document.getElementById("per").textContent = formatNumber(snap.per, "배");
            document.getElementById("cns-per").textContent = formatNumber(snap.cns_per, "배");
            document.getElementById("pbr").textContent = formatNumber(snap.pbr, "배");
            document.getElementById("eps").textContent = formatNumber(snap.eps, "원");
            document.getElementById("bps").textContent = formatNumber(snap.bps, "원");
            document.getElementById("dividend-yield").textContent = formatNumber(snap.dividend_yield, "%");

            const tbody = document.getElementById("financials-tbody");
            tbody.innerHTML = "";
            (data.financials || []).forEach((item) => {
                const tr = document.createElement("tr");
                if (item.is_consensus) tr.classList.add("consensus-row");
                const tdP = document.createElement("td");
                tdP.textContent = item.period || "-";
                if (item.is_consensus) {
                    const b = document.createElement("span");
                    b.className = "consensus-badge";
                    b.textContent = "(E) 추정";
                    tdP.appendChild(b);
                }
                const tdR = document.createElement("td");
                tdR.textContent = formatEok(item.revenue);
                const tdO = document.createElement("td");
                tdO.textContent = formatEok(item.operating_income);
                const tdRoe = document.createElement("td");
                tdRoe.textContent = item.roe !== null && item.roe !== undefined ? `${item.roe.toFixed(2)}%` : "N/A";
                tr.append(tdP, tdR, tdO, tdRoe);
                tbody.appendChild(tr);
            });

            const ul = document.getElementById("news-list");
            ul.innerHTML = "";
            (data.news || []).forEach((item) => {
                const li = document.createElement("li");
                li.className = "news-item";
                const a = document.createElement("a");
                a.className = "news-title";
                a.href = item.url && (item.url.startsWith("http://") || item.url.startsWith("https://")) ? item.url : "#";
                a.target = "_blank";
                a.rel = "noopener noreferrer";
                a.textContent = item.title || "제목 없음";
                li.appendChild(a);
                if (item.published) {
                    const dt = document.createElement("div");
                    dt.className = "news-date";
                    dt.textContent = item.published;
                    li.appendChild(dt);
                }
                ul.appendChild(li);
            });

            resultSection.classList.remove("hidden");
        } catch (err) {
            console.error("[ERROR] 수집 중 오류 발생:", err.message);
            showErrorBox(errorBox, ["서버와 통신하는 중 네트워크 오류가 발생했습니다."]);
        } finally {
            loadingBox.classList.add("hidden");
            searchBtn.disabled = false;
        }
    }
}
