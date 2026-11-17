document.addEventListener("DOMContentLoaded", () => {
    console.log("[PAGE] 페이지 로드 완료");

    const searchForm = document.getElementById("search-form");
    const codeInput = document.getElementById("stock-code-input");
    const searchBtn = document.getElementById("search-btn");
    const exampleBtns = document.querySelectorAll(".example-btn");

    const loadingBox = document.getElementById("loading-box");
    const errorBox = document.getElementById("error-box");
    const resultSection = document.getElementById("result-section");

    // 예시 종목 버튼 클릭 시 즉시 조회
    exampleBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
            const code = btn.dataset.code;
            codeInput.value = code;
            fetchStockData(code);
        });
    });

    // 검색 폼 제출 이벤트
    searchForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const code = codeInput.value.trim();
        fetchStockData(code);
    });

    /**
     * 백엔드 POST /fetch 호출 및 결과 처리
     */
    async function fetchStockData(code) {
        // 6자리 숫자 문자열 검증
        if (!/^\d{6}$/.test(code)) {
            const msg = "종목코드는 6자리 숫자여야 합니다. (예: 000660)";
            console.error(`[ERROR] 수집 중 오류 발생 (${msg})`);
            showError([msg]);
            resultSection.classList.add("hidden");
            return;
        }

        console.log(`[SEARCH] 종목 수집 요청 시작 (${code})`);

        // UI 상태 초기화 (로딩 표시)
        loadingBox.classList.remove("hidden");
        errorBox.classList.add("hidden");
        resultSection.classList.add("hidden");
        searchBtn.disabled = true;

        try {
            const response = await fetch("/fetch", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ code })
            });

            const data = await response.json();

            // 종목명 자체를 가져오지 못한 치명적 오류 처리
            if (!data.name) {
                const errs = data.errors && data.errors.length > 0
                    ? data.errors
                    : ["종목 데이터를 불러오지 못했습니다."];
                console.error("[ERROR] 수집 중 오류 발생:", errs);
                showError(errs);
                return;
            }

            const currentPrice = data.snapshot ? data.snapshot.current_price : null;
            console.log(`[PARSED] 기본 정보 수집 완료 (${data.name}, 현재가: ${currentPrice})`);
            console.log(`[NEWS] 뉴스 수집 완료 (${(data.news || []).length}건)`);

            // 부분 오류(예: 뉴스 또는 실적 일부 실패)가 있는 경우 경고 표시 후 정상 영역은 렌더링
            if (data.errors && data.errors.length > 0) {
                console.warn("[ERROR] 일부 영역 수집 중 오류 발생:", data.errors);
                showError(data.errors);
            }

            renderResult(data);
            resultSection.classList.remove("hidden");
            console.log("[RENDER] 화면 데이터 카드 렌더링 완료");

        } catch (err) {
            console.error("[ERROR] 수집 중 오류 발생:", err.message);
            showError(["서버와 통신하는 중 네트워크 오류가 발생했습니다. Flask 서버가 실행 중인지 확인해 주세요."]);
        } finally {
            loadingBox.classList.add("hidden");
            searchBtn.disabled = false;
        }
    }

    /**
     * 오류 메시지 박스 렌더링 (XSS 방지용 textContent 사용)
     */
    function showError(messages) {
        errorBox.innerHTML = "";
        const title = document.createElement("strong");
        title.textContent = "안내 / 오류 발생";
        errorBox.appendChild(title);

        const ul = document.createElement("ul");
        messages.forEach((msg) => {
            const li = document.createElement("li");
            li.textContent = msg;
            ul.appendChild(li);
        });
        errorBox.appendChild(ul);
        errorBox.classList.remove("hidden");
    }

    /**
     * 수집된 JSON 데이터를 화면 카드, 실적 표, 뉴스 리스트에 렌더링
     */
    function renderResult(data) {
        renderSnapshot(data.code, data.name, data.snapshot || {});
        renderFinancials(data.financials || []);
        renderNews(data.news || []);
    }

    function renderSnapshot(code, name, snapshot) {
        document.getElementById("stock-code").textContent = code || "-";
        document.getElementById("stock-name").textContent = name || "-";

        const priceEl = document.getElementById("current-price");
        const rateEl = document.getElementById("change-rate");

        priceEl.textContent = formatNumber(snapshot.current_price, "원");

        // 등락률 색상 클래스 초기화 후 적용
        priceEl.classList.remove("up", "down", "flat");
        rateEl.classList.remove("up", "down", "flat");

        const rate = snapshot.change_rate;
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

        document.getElementById("market-cap").textContent = formatMarketCap(snapshot.market_cap);
        document.getElementById("per").textContent = formatNumber(snapshot.per, "배");
        document.getElementById("cns-per").textContent = formatNumber(snapshot.cns_per, "배");
        document.getElementById("pbr").textContent = formatNumber(snapshot.pbr, "배");
        document.getElementById("eps").textContent = formatNumber(snapshot.eps, "원");
        document.getElementById("bps").textContent = formatNumber(snapshot.bps, "원");
        document.getElementById("dividend-yield").textContent = formatNumber(snapshot.dividend_yield, "%");
    }

    function renderFinancials(financials) {
        const tbody = document.getElementById("financials-tbody");
        tbody.innerHTML = "";

        if (!financials || financials.length === 0) {
            const tr = document.createElement("tr");
            const td = document.createElement("td");
            td.colSpan = 4;
            td.textContent = "수집된 기업실적 데이터가 없습니다.";
            td.style.textAlign = "center";
            tr.appendChild(td);
            tbody.appendChild(tr);
            return;
        }

        financials.forEach((item) => {
            const tr = document.createElement("tr");
            if (item.is_consensus) {
                tr.classList.add("consensus-row");
            }

            // 1. 기간 (+ 추정치 뱃지)
            const tdPeriod = document.createElement("td");
            tdPeriod.textContent = item.period || "-";
            if (item.is_consensus) {
                const badge = document.createElement("span");
                badge.className = "consensus-badge";
                badge.textContent = "(E) 추정";
                tdPeriod.appendChild(badge);
            }
            tr.appendChild(tdPeriod);

            // 2. 매출액 (억원 단위 변환)
            const tdRev = document.createElement("td");
            tdRev.textContent = formatEok(item.revenue);
            tr.appendChild(tdRev);

            // 3. 영업이익 (억원 단위 변환)
            const tdOp = document.createElement("td");
            tdOp.textContent = formatEok(item.operating_income);
            if (item.operating_income !== null && item.operating_income < 0) {
                tdOp.classList.add("down");
            }
            tr.appendChild(tdOp);

            // 4. ROE (%)
            const tdRoe = document.createElement("td");
            tdRoe.textContent = item.roe !== null && item.roe !== undefined
                ? `${item.roe.toFixed(2)}%`
                : "N/A";
            if (item.roe !== null && item.roe < 0) {
                tdRoe.classList.add("down");
            }
            tr.appendChild(tdRoe);

            tbody.appendChild(tr);
        });
    }

    function renderNews(newsList) {
        const ul = document.getElementById("news-list");
        ul.innerHTML = "";

        if (!newsList || newsList.length === 0) {
            const li = document.createElement("li");
            li.className = "empty-message";
            li.textContent = "수집된 관련 뉴스가 없습니다.";
            ul.appendChild(li);
            return;
        }

        newsList.forEach((item) => {
            const li = document.createElement("li");
            li.className = "news-item";

            const link = document.createElement("a");
            link.className = "news-title";
            const safeUrl = item.url && (item.url.startsWith("http://") || item.url.startsWith("https://"))
                ? item.url
                : "#";
            link.href = safeUrl;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = item.title || "제목 없음";
            li.appendChild(link);

            if (item.description) {
                const desc = document.createElement("p");
                desc.className = "news-desc";
                desc.textContent = item.description;
                li.appendChild(desc);
            }

            if (item.published) {
                const dateEl = document.createElement("div");
                dateEl.className = "news-date";
                dateEl.textContent = item.published;
                li.appendChild(dateEl);
            }

            ul.appendChild(li);
        });
    }

    // 숫자 포맷팅 헬퍼
    function formatNumber(val, unit = "") {
        if (val === null || val === undefined) return "N/A";
        return `${val.toLocaleString("ko-KR")}${unit}`;
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
});
