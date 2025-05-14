let currentSymbol = Object.values(symbols)[0];
let tradingRunning = true;
let exchangeHalted = false;

// Populate dropdown
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

function updateExchangeButton(isHalted) {
    const btn = document.getElementById('exchange-toggle');
    btn.textContent = isHalted ? "Resume Exchange" : "Halt Exchange";
    document.getElementById('exchange-status').textContent = isHalted ? "Exchange Halted" : "Exchange Active";
}

function updateTradingButton(isRunning) {
    const btn = document.getElementById('trading-toggle');
    btn.textContent = isRunning ? "Pause MyStrategy" : "Start MyStrategy";
    document.getElementById('trading-status').textContent = isRunning ? "MyStrategy Running" : "MyStrategy Paused";
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

            // Limit to 15 rows max
            const maxRows = 15;
            const rowsToShow = Math.min(maxRows, Math.max(bids.length, asks.length));
            let rows = '';
            for (let i = 0; i < rowsToShow; i++) {
                let bid = bids[i] || { qty: '', price: '' };
                let ask = asks[i] || { qty: '', price: '' };
                rows += `<tr>
                    <td class="bid">${bid.qty || ''}</td>
                    <td class="bid">${bid.price || ''}</td>
                    <td class="ask">${ask.price || ''}</td>
                    <td class="ask">${ask.qty || ''}</td>
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
            // Limit to 15 most recent trades
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

            // Utility functions for formatting
            const formatPercent = (v) => v !== undefined ? (v > 0 ? "+" : "") + v.toFixed(2) + "%" : "-";
            const formatEuro = (v) => v !== undefined ? (v > 0 ? "+" : "") + v.toFixed(2) : "-";

            strategies.forEach(name => {
                const m = data[name] || {};

                // Determine CSS classes for coloring positive/negative/neutral values
                const realizedClass = m.realized_pnl >= 0 ? "positive" : "negative";
                const unrealizedClass = m.unrealized_pnl >= 0 ? "positive" : "negative";
                const totalClass = m.total_pnl >= 0 ? "positive" : "negative";
                const inventoryPercentClass = m.inventory_percent >= 0 ? "positive" : "negative";

                rows += `<tr>
                    <td style="text-align:left;">
                        <span style="font-weight:bold;letter-spacing:1px;">${
                            name === "my_strategy" ? "MyStrategy"
                            : name === "passive_liquidity_provider" ? "Passive Liquidity Provider"
                            : name === "market_maker" ? "Market Maker"
                            : name === "momentum" ? "Momentum"
                            : name
                        }</span>
                    </td>
                    <td>${m.inventory !== undefined ? m.inventory : '-'}</td>
                    <td class="${realizedClass}">${formatPercent(m.realized_pnl_percent)}</td>
                    <td class="${unrealizedClass}">${formatPercent(m.unrealized_pnl_percent)}</td>
                    <td class="${totalClass}">${formatPercent(m.total_pnl_percent)}</td>
                    <td class="${totalClass}">${formatEuro(m.total_pnl)}</td>
                    <td class="${inventoryPercentClass}">${formatPercent(m.inventory_percent)}</td>
                    <td>${m.total_trades !== undefined ? m.total_trades : '-'}</td>
                </tr>`;
            });

            // Update table header and body
            document.getElementById('metrics-table').innerHTML = `
                <thead>
                    <tr>
                        <th>Strategy</th>
                        <th>Inventory</th>
                        <th>Realised P&amp;L (%)</th>
                        <th>Unrealised P&amp;L (%)</th>
                        <th>Total P&amp;L (%)</th>
                        <th>Total P&amp;L (&euro;)</th>
                        <th>Inventory (%)</th>
                        <th>Total Trades</th>
                    </tr>
                </thead>
                <tbody id="metrics-body">${rows}</tbody>
            `;
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
            data.forEach(d => {
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
                legend: {orientation: "h", x: 0, y: 1.15}
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

// ---- TAB LOGIC ----
function openTab(evt, tabName) {
    // Hide all tabcontent
    var tabcontent = document.getElementsByClassName("tabcontent");
    for (let i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }
    // Remove "active" class from all tablinks
    var tablinks = document.getElementsByClassName("tablinks");
    for (let i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }
    // Show the selected tab and set active
    document.getElementById(tabName).style.display = "block";
    evt.currentTarget.className += " active";
    refreshVisibleTab();
}

// Only refresh data for visible tab
function refreshVisibleTab() {
    // Always refresh status and symbol controls
    refreshStatus();

    // Determine which tab is visible
    const orderBookTab = document.getElementById('OrderBookTab');
    const tradeBlotterTab = document.getElementById('TradeBlotterTab');
    const analyticsTab = document.getElementById('AnalyticsTab');

    if (orderBookTab && orderBookTab.style.display === "block") {
        refreshOrderBook();
        refreshTrades();
        refreshMetrics();
    }
    if (tradeBlotterTab && tradeBlotterTab.style.display === "block") {
        refreshBlotter();
    }
    if (analyticsTab && analyticsTab.style.display === "block") {
        refreshOrderFlowHeatmap();
        refreshSpreadChart();
        refreshLatencyChart();
        refreshLiquidityChart();
        refreshDepthChart();
    }
}

function refreshDepthChart() {
    fetch(`/order_book?symbol=${currentSymbol}`)
        .then(response => response.json())
        .then(data => {
            let bids = data.bids || [];
            let asks = data.asks || [];

            // Sort bids descending, asks ascending by price
            bids = bids.slice().sort((a, b) => b.price - a.price);
            asks = asks.slice().sort((a, b) => a.price - b.price);

            // Calculate cumulative quantities
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

            // Plotly traces
            const traces = [
                {
                    x: bidPrices,
                    y: bidCumQty,
                    name: "Bids",
                    mode: "lines",
                    line: { color: "#27AE60", shape: "hv" }, // green, step
                    fill: "tozeroy"
                },
                {
                    x: askPrices,
                    y: askCumQty,
                    name: "Asks",
                    mode: "lines",
                    line: { color: "#E74C3C", shape: "hv" }, // red, step
                    fill: "tozeroy"
                }
            ];

            Plotly.newPlot('depth-chart', traces, {
                title: "",
                xaxis: { title: "Price" },
                yaxis: { title: "Cumulative Quantity" },
                legend: { orientation: "h", x: 0, y: 1.15 },
                margin: { t: 30, r: 20, l: 50, b: 40 },
                plot_bgcolor: "#23272E",
                paper_bgcolor: "#23272E",
                font: { color: "#F3F6F9" }
            }, {responsive: true});
        });
}


// Initial load: open default tab and refresh
window.onload = function() {
    document.getElementById("defaultOpen").click();
};

// Optionally, refresh visible tab every 2 seconds
setInterval(refreshVisibleTab, 2000);
