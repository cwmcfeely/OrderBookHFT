let currentSymbol = Object.values(symbols)[0];
let tradingRunning = true;
let exchangeHalted = false;

const symbolSelect = document.getElementById('symbol-select');
for (const [key, val] of Object.entries(symbols)) {
    let opt = document.createElement('option');
    opt.value = val;
    opt.text = `${key} (${val})`;
    symbolSelect.appendChild(opt);
}
symbolSelect.value = currentSymbol;
symbolSelect.onchange = function() {
    currentSymbol = this.value;
    selectSymbol(currentSymbol);
    refreshVisibleTab();
};

function fetchWithRetry(url, options = {}, retries = 2) {
    return fetch(url, options).then(response => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
    }).catch(err => {
        if (retries > 0) {
            return fetchWithRetry(url, options, retries - 1);
        } else {
            throw err;
        }
    });
}

function selectSymbol(symbol) {
    fetch('/select_symbol', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: symbol })
    }).catch(err => {
        alert("Failed to select symbol: " + err.message);
    });
}

function toggleExchange() {
    fetchWithRetry('/toggle_exchange', { method: 'POST' })
        .then(data => {
            exchangeHalted = data.exchange_halted;
            updateExchangeButton(exchangeHalted);
            refreshStatus();
        })
        .catch(err => showExchangeError("Failed to toggle exchange: " + err.message));
}

function toggleMyStrategy() {
    fetchWithRetry('/toggle_my_strategy', { method: 'POST' })
        .then(data => {
            tradingRunning = data.my_strategy_enabled;
            updateTradingButton(tradingRunning);
            refreshStatus();
        })
        .catch(err => showStatusError("Failed to toggle trading: " + err.message));
}

function cancelMyStrategyOrders() {
    const symbol = document.getElementById('symbol-select').value;
    fetch('/cancel_mystrategy_orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: symbol })
    })
    .then(response => response.json())
    .then(data => {
        alert("All MyStrategy orders cancelled.");
        refreshOrderBook();
    })
    .catch(err => {
        alert("Failed to cancel orders: " + err.message);
    });
}

function updateExchangeButton(isHalted) {
    const btn = document.getElementById('exchange-toggle');
    btn.textContent = isHalted ? "Resume Exchange" : "Halt Exchange";
    document.getElementById('exchange-status').textContent = "";
}

function updateTradingButton(isRunning) {
    const btn = document.getElementById('trading-toggle');
    btn.textContent = isRunning ? "Pause MyStrategy" : "Start MyStrategy";
    document.getElementById('trading-status').textContent = "";
}

function refreshStatus() {
    fetchWithRetry('/status')
        .then(data => {
            exchangeHalted = data.exchange_halted;
            tradingRunning = data.my_strategy_enabled;
            updateExchangeButton(exchangeHalted);
            updateTradingButton(tradingRunning);
        })
        .catch(err => showStatusError("Status error: " + err.message));
}

function showStatusError(msg) {
    const el = document.getElementById('trading-status');
    el.textContent = msg;
    el.classList.add('error');
}

function showExchangeError(msg) {
    const el = document.getElementById('exchange-status');
    el.textContent = msg;
    el.classList.add('error');
}

function hideStatusError() {
    document.getElementById('trading-status').classList.remove('error');
}

function refreshOrderBook() {
    document.getElementById('orderbook-feedback').style.display = '';
    document.getElementById('orderbook-error').style.display = 'none';
    fetchWithRetry(`/order_book?symbol=${currentSymbol}`)
    .then(data => {
        document.getElementById('orderbook-feedback').style.display = 'none';
        let bids = data.bids || [];
        let asks = data.asks || [];
        const maxRows = 15;
        const rowsToShow = Math.min(maxRows, Math.max(bids.length, asks.length));
        let rows = '';
        for (let i = 0; i < rowsToShow; i++) {
            let bid = bids[i] || { qty: '', price: '', sources: [] };
            let ask = asks[i] || { qty: '', price: '', sources: [] };
            const bidBold = (bid.sources && bid.sources.includes('my_strategy')) ? ' style="font-weight:bold;"' : '';
            const askBold = (ask.sources && ask.sources.includes('my_strategy')) ? ' style="font-weight:bold;"' : '';
            rows += `<tr>
                <td${bidBold}>${bid.qty || ''}</td>
                <td class="bid"${bidBold}>${bid.price || ''}</td>
                <td class="ask"${askBold}>${ask.price || ''}</td>
                <td${askBold}>${ask.qty || ''}</td>
            </tr>`;
        }
        document.getElementById('orderbook-body').innerHTML = rows;
        document.getElementById('last-price').textContent = data.last_price || '-';
    })
    .catch(err => {
        document.getElementById('orderbook-feedback').style.display = 'none';
        document.getElementById('orderbook-error').style.display = '';
        document.getElementById('orderbook-error').textContent = "Order book error: " + err.message;
    });
}

function refreshTrades() {
    document.getElementById('trades-feedback').style.display = '';
    document.getElementById('trades-error').style.display = 'none';
    fetchWithRetry(`/trades?symbol=${currentSymbol}`)
    .then(trades => {
        document.getElementById('trades-feedback').style.display = 'none';
        let rows = '';
        (trades || []).slice(-15).reverse().forEach(trade => {
            rows += `<tr>
                <td>${trade.time || '-'}</td>
                <td>${trade.price}</td>
                <td>${trade.qty}</td>
                <td>${trade.side || '-'}</td>
                <td>${trade.source || '-'}</td>
            </tr>`;
        });
        document.getElementById('trades-body').innerHTML = rows;
    })
    .catch(err => {
        document.getElementById('trades-feedback').style.display = 'none';
        document.getElementById('trades-error').style.display = '';
        document.getElementById('trades-error').textContent = "Trades error: " + err.message;
    });
}

function refreshMetrics() {
    document.getElementById('metrics-feedback').style.display = '';
    document.getElementById('metrics-error').style.display = 'none';
    fetch(`/strategy_status?symbol=${encodeURIComponent(currentSymbol)}`)
    .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status} - ${response.statusText}`);
        return response.json();
    })
    .then(data => {
        document.getElementById('metrics-feedback').style.display = 'none';
        let rows = '';
        const strategies = ["my_strategy", "passive_liquidity_provider", "market_maker", "momentum"];
        const formatPercent = (v) => v !== undefined ? (v > 0 ? "+" : "") + v.toFixed(2) + "%" : "-";
        const formatEuro = (v) => v !== undefined ? (v > 0 ? "+" : "") + v.toFixed(2) : "-";
        strategies.forEach(name => {
            const m = data[name] || {};
            const realisedClass = m.realised_pnl >= 0 ? "positive" : "negative";
            const unrealisedClass = m.unrealised_pnl >= 0 ? "positive" : "negative";
            const totalClass = m.total_pnl >= 0 ? "positive" : "negative";
            const inventoryPercentClass = m.inventory_percent >= 0 ? "positive" : "negative";
            rows += `<tr>
                <td>${name === "my_strategy" ? "MyStrategy"
                    : name === "passive_liquidity_provider" ? "Passive Liquidity Provider"
                    : name === "market_maker" ? "Market Maker"
                    : name === "momentum" ? "Momentum"
                    : name}</td>
                <td>${m.inventory !== undefined ? m.inventory : '-'}</td>
                <td class="${realisedClass}">${formatPercent(m.realised_pnl_percent)}</td>
                <td class="${unrealisedClass}">${formatPercent(m.unrealised_pnl_percent)}</td>
                <td class="${totalClass}">${formatPercent(m.total_pnl_percent)}</td>
                <td class="${totalClass}">${formatEuro(m.total_pnl)}</td>
                <td class="${inventoryPercentClass}">${formatPercent(m.inventory_percent)}</td>
                <td>${m.total_trades !== undefined ? m.total_trades : '-'}</td>
            </tr>`;
        });
        document.getElementById('metrics-table').innerHTML = `<tr>
            <th>Strategy</th>
            <th>Inventory</th>
            <th>Realised P&L (%)</th>
            <th>Unrealised P&L (%)</th>
            <th>Total P&L (%)</th>
            <th>Total P&L (€)</th>
            <th>Inventory (%)</th>
            <th>Total Trades</th>
        </tr>${rows}`;
    })
    .catch(err => {
        document.getElementById('metrics-feedback').style.display = 'none';
        const errorEl = document.getElementById('metrics-error');
        errorEl.style.display = '';
        errorEl.textContent = "Metrics error: " + err.message;
    });
}

function refreshOrderFlowHeatmap() {
    fetch(`/order_book_history?symbol=${currentSymbol}`)
    .then(r => r.json())
    .then(data => {
        if (!data || !data.length) {
            Plotly.newPlot('orderflow-heatmap', [{z: [[0, 0], [0, 0]]}], {title: "No Data"});
            return;
        }
        let z = data.map(row => row.quantities);
        let x = data[0].price_levels;
        let y = data.map(row => row.time);
        Plotly.newPlot('orderflow-heatmap', [{
            z: z, x: x, y: y, type: 'heatmap', colorscale: 'YlGnBu'
        }], {height: 300, margin: {t: 30}});
    });
}

function refreshSpreadChart() {
    fetch(`/spread_history?symbol=${currentSymbol}`)
    .then(r => r.json())
    .then(data => {
        let x = data.map(d => d.time);
        let mid = data.map(d => d.mid);
        let spread = data.map(d => d.spread);
        Plotly.newPlot('spread-chart', [
            {x: x, y: mid, name: 'Mid Price', type: 'scatter', line: {color: '#90caf9'}},
            {x: x, y: spread, name: 'Spread', yaxis: 'y2', type: 'scatter', line: {color: '#E74C3C'}}
        ], {
            height: 300,
            margin: {t: 30},
            yaxis: {title: 'Mid Price', side: 'left'},
            yaxis2: {title: 'Spread', overlaying: 'y', side: 'right'}
        });
    });
}

function refreshLiquidityChart() {
    fetch(`/liquidity_history?symbol=${currentSymbol}`)
    .then(r => r.json())
    .then(data => {
        let x = data.map(d => d.time);
        let y = data.map(d => d.liquidity);
        Plotly.newPlot('liquidity-chart', [{
            x: x, y: y, name: 'Liquidity', type: 'scatter', fill: 'tozeroy', line: {color: '#27AE60'}
        }], {
            height: 300,
            margin: {t: 30},
            yaxis: {title: 'Total Depth'}
        });
    });
}

function refreshBlotter() {
    fetch(`/trades?symbol=${currentSymbol}`)
    .then(r => r.json())
    .then(trades => {
        let filter = document.getElementById('trade-filter').value.toLowerCase();
        let rows = '';
        (trades || []).reverse().forEach(trade => {
            if (
                (!filter) ||
                (trade.side && trade.side.toLowerCase().includes(filter)) ||
                (trade.source && trade.source.toLowerCase().includes(filter)) ||
                (trade.price && trade.price.toString().includes(filter))
            ) {
                rows += `<tr>
                    <td>${trade.time || '-'}</td>
                    <td>${trade.price}</td>
                    <td>${trade.qty}</td>
                    <td>${trade.side || '-'}</td>
                    <td>${trade.source || '-'}</td>
                </tr>`;
            }
        });
        document.getElementById('blotter-body').innerHTML = rows;
    });
}
document.getElementById('trade-filter').oninput = refreshBlotter;

function refreshExecutionReports() {
    document.getElementById('exec-reports-feedback').style.display = '';
    document.getElementById('exec-reports-error').style.display = 'none';
    fetchWithRetry(`/execution_reports?symbol=${currentSymbol}`)
    .then(reports => {
        document.getElementById('exec-reports-feedback').style.display = 'none';
        let rows = '';
        (reports || []).reverse().forEach(rep => {
            rows += `<tr>
                <td>${rep.time || '-'}</td>
                <td>${rep.cl_ord_id || '-'}</td>
                <td>${rep.exec_id || '-'}</td>
                <td>${rep.ord_status || '-'}</td>
                <td>${rep.exec_type || '-'}</td>
                <td>${rep.side || '-'}</td>
                <td>${rep.last_qty !== undefined ? rep.last_qty : '-'}</td>
                <td>${rep.last_px !== undefined ? rep.last_px : '-'}</td>
                <td>${rep.price !== undefined ? rep.price : '-'}</td>
                <td>${rep.source || '-'}</td>
            </tr>`;
        });
        document.getElementById('exec-reports-body').innerHTML = rows;
        filterExecReportsTable();
    })
    .catch(err => {
        document.getElementById('exec-reports-feedback').style.display = 'none';
        document.getElementById('exec-reports-error').style.display = '';
        document.getElementById('exec-reports-error').textContent = "Execution reports error: " + err.message;
    });
}

function filterExecReportsTable() {
    var input = document.getElementById("exec-filter");
    if (!input) return;
    var filter = input.value.toUpperCase();
    var table = document.getElementById("exec-reports-table");
    var tr = table.getElementsByTagName("tr");
    for (var i = 1; i < tr.length; i++) {
        var rowText = tr[i].textContent || tr[i].innerText;
        tr[i].style.display = rowText.toUpperCase().indexOf(filter) > -1 ? "" : "none";
    }
}

function openTab(evt, tabName) {
    var tabcontent = document.getElementsByClassName("tabcontent");
    for (let i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }
    var tablinks = document.getElementsByClassName("tablinks");
    for (let i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }
    document.getElementById(tabName).style.display = "block";
    evt.currentTarget.className += " active";
    refreshVisibleTab();
}

function refreshLatencyChart() {
    fetch(`/order_latency_history?symbol=${currentSymbol}`)
    .then(r => r.json())
    .then(data => {
        if (!data || !data.length) {
            Plotly.newPlot('latency-chart', [{x: [0], y: [0], type: 'scatter'}], {title: "No Data"});
            return;
        }
        const stratColors = {
            "my_strategy": "#1976d2",
            "passive_liquidity_provider": "#ff9800",
            "market_maker": "#43a047",
            "momentum": "#e53935"
        };
        const stratNames = {
            "my_strategy": "MyStrategy",
            "passive_liquidity_provider": "Passive Liquidity Provider",
            "market_maker": "Market Maker",
            "momentum": "Momentum"
        };
        const grouped = {};
        // Filter out 'system' entries
        const filtered = data.filter(d => d.strategy !== "system");

        filtered.forEach(d => {
            const strat = d.strategy || "Unknown";
            if (!grouped[strat]) grouped[strat] = {x: [], y: []};
            grouped[strat].x.push(d.time);
            grouped[strat].y.push(d.latency_ms);
        });

        const traces = Object.keys(grouped).map(strat => ({
            x: grouped[strat].x,
            y: grouped[strat].y,
            name: stratNames[strat] || strat,
            type: 'scatter',
            mode: 'lines+markers',
            line: {color: stratColors[strat] || '#888'}
        }));
        Plotly.newPlot('latency-chart', traces, {
            height: 300,
            margin: {t: 30},
            yaxis: {title: 'Latency (ms)'},
            xaxis: {title: 'Time'},
            legend: {orientation: "h", x: 0, y: 1.15},
            plot_bgcolor: "#23272E",
            paper_bgcolor: "#23272E",
            font: { color: "#F3F6F9" }
        }, {responsive: true});
    });
}

function refreshDepthChart() {
    fetch(`/order_book?symbol=${currentSymbol}`)
    .then(response => response.json())
    .then(data => {
        let bids = data.bids || [];
        let asks = data.asks || [];
        bids = bids.slice().sort((a, b) => b.price - a.price);
        asks = asks.slice().sort((a, b) => a.price - b.price);
        let bidPrices = [], bidCumQty = [], cum = 0;
        bids.forEach(b => {
            cum += b.qty;
            bidPrices.push(b.price);
            bidCumQty.push(cum);
        });
        let askPrices = [], askCumQty = [], cumAsk = 0;
        asks.forEach(a => {
            cumAsk += a.qty;
            askPrices.push(a.price);
            askCumQty.push(cumAsk);
        });
        const traces = [
            {x: bidPrices, y: bidCumQty, name: "Bids", mode: "lines", line: { color: "#27AE60", shape: "hv" }, fill: "tozeroy"},
            {x: askPrices, y: askCumQty, name: "Asks", mode: "lines", line: { color: "#E74C3C", shape: "hv" }, fill: "tozeroy"}
        ];
        Plotly.newPlot('depth-chart', traces, {
            height: 300,
            margin: { t: 30 },
            yaxis: { title: 'Cumulative Quantity' },
            xaxis: { title: 'Price' },
            legend: { orientation: "h", x: 0, y: 1.15 },
            plot_bgcolor: "#23272E",
            paper_bgcolor: "#23272E",
            font: { color: "#F3F6F9" }
        }, { responsive: true });
    })
    .catch(err => {
        Plotly.newPlot('depth-chart', [{ x: [], y: [], type: 'scatter' }], { title: "No Data" });
    });
}

function refreshCompetitionLogs() {
    fetch('/competition_logs?symbol=' + encodeURIComponent(currentSymbol))
    .then(r => r.json())
    .then(logs => {
        const tbody = document.getElementById('competition-logs-body');
        if (!tbody) return;
        tbody.innerHTML = (logs || []).map(log => `
            <tr>
                <td>${log.time}</td>
                <td>${log.taker_strategy}</td>
                <td>${log.maker_strategy}</td>
                <td>${typeof log.price === "number" ? log.price.toFixed(2) : log.price}</td>
                <td>${log.qty}</td>
            </tr>
        `).join('');
    });
}

function refreshVisibleTab() {
    refreshStatus();
    const orderBookTab = document.getElementById('OrderBookTab');
    const tradeBlotterTab = document.getElementById('TradeBlotterTab');
    const analyticsTab = document.getElementById('AnalyticsTab');
    const execReportTab = document.getElementById('ExecutionReportTab');
    const competitionLogsTab = document.getElementById('CompetitionLogsTab');
    if (orderBookTab && orderBookTab.style.display === "block") {
        refreshOrderBook();
        refreshTrades();
        refreshMetrics();
        refreshDepthChart();
    }
    if (tradeBlotterTab && tradeBlotterTab.style.display === "block") {
        refreshBlotter();
    }
    if (analyticsTab && analyticsTab.style.display === "block") {
        refreshOrderFlowHeatmap();
        refreshSpreadChart();
        refreshLatencyChart();
        refreshLiquidityChart();
    }
    if (execReportTab && execReportTab.style.display === "block") {
        refreshExecutionReports();
    }
    if (competitionLogsTab && competitionLogsTab.style.display === "block") {
        refreshCompetitionLogs();
    }
}

window.onload = function() {
    document.getElementById("defaultOpen").click();
};

setInterval(refreshVisibleTab, 2000);

const bidClass = (bid.sources && bid.sources.includes('my_strategy')) ? 'my-strategy-order' : '';
const askClass = (ask.sources && ask.sources.includes('my_strategy')) ? 'my-strategy-order' : '';
rows += `<tr>
    <td class="${bidClass}">${bid.qty || ''}</td>
    <td class="bid ${bidClass}">${bid.price || ''}</td>
    <td class="ask ${askClass}">${ask.price || ''}</td>
    <td class="${askClass}">${ask.qty || ''}</td>
</tr>`;
