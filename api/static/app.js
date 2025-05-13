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
    refreshAll();
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
            let maxRows = Math.max(bids.length, asks.length, 10);
            let rows = '';
            for (let i = 0; i < maxRows; i++) {
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
            (trades || []).slice(-20).reverse().forEach(trade => {
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
            // data is an object with keys like 'my_strategy', 'passive_liquidity_provider', etc.
            const strategies = ["my_strategy", "passive_liquidity_provider", "market_maker", "momentum"];
            strategies.forEach(name => {
                const m = data[name] || {};
                const pnlClass = m.daily_pnl > 0 ? "positive" : (m.daily_pnl < 0 ? "negative" : "neutral");
                rows += `<tr>
                    <td style="text-align:left;">
                        <span style="font-weight:bold;letter-spacing:1px;">${name === "my_strategy" ? "MyStrategy" : 
                            name === "passive_liquidity_provider" ? "Passive Liquidity Provider" : 
                            name === "market_maker" ? "Market Maker" : 
                            name === "momentum" ? "Momentum" : name}</span>
                    </td>
                    <td>${m.inventory !== undefined ? m.inventory : '-'}</td>
                    <td class="${pnlClass}">${m.daily_pnl !== undefined ? (m.daily_pnl > 0 ? "+" : "") + m.daily_pnl.toFixed(2) : '-'}</td>
                    <td>${m.win_rate !== undefined ? (m.win_rate * 100).toFixed(1) + "%" : '-'}</td>
                    <td>${m.total_trades !== undefined ? m.total_trades : '-'}</td>
                </tr>`;
            });
            document.getElementById('metrics-body').innerHTML = rows;
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
            let x = data.map(d => d.time);      // time of execution
            let y = data.map(d => d.latency_ms); // latency in ms
            Plotly.newPlot('latency-chart', [{
                x: x, y: y, name: 'Order Latency', type: 'scatter', mode: 'lines+markers', line: {color: '#ff9800'}
            }], {
                height: 300,
                margin: {t: 30},
                yaxis: {title: 'Latency (ms)'},
                xaxis: {title: 'Time'}
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

function refreshAll() {
    refreshStatus();
    refreshOrderBook();
    refreshTrades();
    refreshMetrics();
    refreshOrderFlowHeatmap();
    refreshSpreadChart();
    refreshLiquidityChart();
    refreshBlotter();
    refreshLatencyChart();
}

// Initial load
selectSymbol(currentSymbol);
refreshAll();
setInterval(refreshAll, 2000); // auto-refresh every 2s
