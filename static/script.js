
let socket = null;
const previousValues = {};
const spreadStats = {};
let selectedSymbol = 'EURUSD';
let previousSymbol = null;
let selectedChartType = 'spread';
let selectedTimeRange = 60;

let highchart = null;
const chartSeriesData = [];

const seriesOptions = {
  spread: { name: 'Spread (pips)', color: '#3a86ff' },
  bid: { name: 'Bid Price', color: '#38b000' },
  ask: { name: 'Ask Price', color: '#d90429' }
};

function pipFactor(price) {
  if (price < 5) return 10000;
  if (price < 50) return 1000;
  if (price < 500) return 100;
  if (price < 5000) return 10;
  if (price < 50000) return 1;
  return 0.1;
}

function formatPrice(value) {
  const num = parseFloat(value);
  if (isNaN(num)) return { mainPart: '0.00', tail: '', lastDigit: '' };

  const [intPart, decPart = ''] = num.toString().split('.');
  const dec = decPart.padEnd(5, '0');
  
  if (num < 5) {
    return { 
      mainPart: `${intPart}.${dec.slice(0, 2)}`,
      tail: dec.slice(2, 4),
      lastDigit: dec.slice(4, 5)
    };
  }
  if (num < 50) {
    return { 
      mainPart: `${intPart}.${dec.slice(0, 1)}`,
      tail: dec.slice(1, 3),
      lastDigit: dec.slice(3, 4)
    };
  }
  if (num < 500) {
    return { 
      mainPart: `${intPart}.`,
      tail: dec.slice(0, 2),
      lastDigit: dec.slice(2, 3)
    };
  }
  if (num < 5000) {
    return { 
      mainPart: intPart.slice(0, -1),
      tail: intPart.slice(-1) + '.' + dec.slice(0, 1),
      lastDigit: dec.slice(1, 2)
    };
  }
  return { 
    mainPart: intPart.slice(0, -2),
    tail: intPart.slice(-2),
    lastDigit: "." + dec.slice(0, 2)
  };
}

function formatTime(ts) {
  let timestamp = Number(ts);
  if (timestamp < 10000000000) timestamp *= 1000;
  const date = new Date(timestamp);
  const timeStr = date.toLocaleTimeString('en-GB', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
  const milliseconds = String(date.getMilliseconds()).padStart(3, '0');
  return `${timeStr}.${milliseconds}`;
}

function createHighchart() {
  highchart = Highcharts.stockChart('priceChart', {
    chart: { type: 'line', animation: false },
    time: { useUTC: false },
    title: { text: `${seriesOptions[selectedChartType].name} – ${selectedSymbol}` },
    xAxis: {
      type: 'datetime',
      labels: { format: '{value:%H:%M:%S.%L}' }
    },
    yAxis: { title: { text: null } },
    tooltip: {
      xDateFormat: '%H:%M:%S.%L',
      shared: true
    },
    rangeSelector: { enabled: false },
    series: [{
      name: seriesOptions[selectedChartType].name,
      color: seriesOptions[selectedChartType].color,
      data: [],
      turboThreshold: 0
    }]
  });
}

function resetChart() {
  chartSeriesData.length = 0;
  if (!highchart) {
    createHighchart();
  } else {
    highchart.series[0].update({
      name: seriesOptions[selectedChartType].name,
      color: seriesOptions[selectedChartType].color
    }, false);
    highchart.setTitle({ text: `${seriesOptions[selectedChartType].name} – ${selectedSymbol}` });
    highchart.series[0].setData([], true);
  }
}
function updateChart(data) {
  if (data.symbol !== selectedSymbol) return;

  if (previousSymbol !== selectedSymbol) {
    resetChart();
    previousSymbol = selectedSymbol;
  }

  const bid = parseFloat(data.bid);
  const ask = parseFloat(data.ask);
  const factor = pipFactor(bid);
  const spreadPips = parseFloat(((ask - bid) * factor).toFixed(2));
  const ts = Number(data.ts) || Date.now();

  let value;
  switch (selectedChartType) {
    case 'spread': value = spreadPips; break;
    case 'bid': value = bid; break;
    case 'ask': value = ask; break;
  }

  const point = [ts, value];
  chartSeriesData.push(point);

  const cutoff = Date.now() - selectedTimeRange * 1000;
  while (chartSeriesData.length > 0 && chartSeriesData[0][0] < cutoff) {
    chartSeriesData.shift();
  }

  if (highchart && highchart.series[0]) {
    highchart.series[0].addPoint(point, true, false);
  }
}

function updateTable(data) {
  const tbody = document.getElementById('tableBody');
  let row = document.getElementById('row-' + data.symbol);
  const isNew = !row;

  const bid = parseFloat(data.bid);
  const ask = parseFloat(data.ask);
  const factor = pipFactor(bid);
  const spreadPips = parseFloat(((ask - bid) * factor).toFixed(2));
  const spreadPercent = ((ask - bid) / bid * 100).toFixed(4);

  if (!spreadStats[data.symbol]) {
    spreadStats[data.symbol] = { high: spreadPips, low: spreadPips };
  } else {
    spreadStats[data.symbol].high = Math.max(spreadStats[data.symbol].high, spreadPips);
    spreadStats[data.symbol].low = Math.min(spreadStats[data.symbol].low, spreadPips);
  }

  const bidFormatted = formatPrice(bid);
  const askFormatted = formatPrice(ask);

  const bidColor = previousValues[data.symbol]?.bid < bid ? 'green' :
                   previousValues[data.symbol]?.bid > bid ? 'red' : '';
  const askColor = previousValues[data.symbol]?.ask < ask ? 'green' :
                   previousValues[data.symbol]?.ask > ask ? 'red' : '';
  const bidBg = bidColor === 'green' ? '#d4edda' : bidColor === 'red' ? '#f8d7da' : '';
  const askBg = askColor === 'green' ? '#d4edda' : askColor === 'red' ? '#f8d7da' : '';

  previousValues[data.symbol] = { bid, ask };

  if (isNew) {
    row = document.createElement('tr');
    row.id = 'row-' + data.symbol;
    row.onclick = () => {
      selectedSymbol = data.symbol;
      resetChart();
      document.getElementById('chart-title').innerText = selectedSymbol;
    };
    tbody.appendChild(row);
  }

  row.innerHTML = `
    <td>${data.symbol}</td>
    <td >${bidFormatted.mainPart}<span style="font-size:20px;margin-left:1px; color:${bidColor};"><strong>${bidFormatted.tail}</strong></span><span class="last-digit">${bidFormatted.lastDigit}</span></td>
    <td >${askFormatted.mainPart}<span style="font-size:20px;margin-left:1px;color:${askColor};"><strong>${askFormatted.tail}</strong></span><span class="last-digit">${askFormatted.lastDigit}</span></td>
    <td>${spreadPips}</td>
    <td>${spreadPercent}%</td>
    <td>${spreadStats[data.symbol].high}</td>
    <td>${spreadStats[data.symbol].low}</td>
    <td>${formatTime(data.ts)}</td>
  `;
}

function startConnection() {
  if (socket?.connected) return;

  socket = io();

  socket.on('connect', () => {
    document.getElementById('connectBtn').disabled = true;
    document.getElementById('disconnectBtn').disabled = false;
  });

  socket.on('disconnect', () => {
    document.getElementById('connectBtn').disabled = false;
    document.getElementById('disconnectBtn').disabled = true;
  });

  socket.on('market_update', (data) => {
    updateTable(data);
    if (data.symbol === selectedSymbol) {
      updateChart(data);
    }
  });

  socket.on('initial_data', (data) => {
    for (const symbol in data) {
      updateTable(data[symbol]);
    }
    resetChart();
  });
}

function stopConnection() {
  if (socket) {
    socket.disconnect();
    socket = null;
  }
}

document.getElementById('connectBtn').onclick = startConnection;
document.getElementById('disconnectBtn').onclick = stopConnection;

document.getElementById('chartTypeSelector').addEventListener('change', function () {
  selectedChartType = this.value;
  resetChart();
});

const themeBtn = document.querySelector('button[onclick="toggleDarkMode()"]');

function toggleDarkMode() {
const isDark = document.body.classList.toggle('dark-mode');
themeBtn.textContent = isDark ? '☀️' : '🌙';
localStorage.setItem('theme', isDark ? 'dark' : 'light');
}

// Set theme on page load
document.addEventListener('DOMContentLoaded', () => {
const savedTheme = localStorage.getItem('theme') || 'dark';
const isDark = savedTheme === 'dark';
document.body.classList.toggle('dark-mode', isDark);
themeBtn.textContent = isDark ? '☀️' : '🌙';
});
// Add this to your existing JavaScript
function updateConnectionStatus(status) {
    const dot = document.getElementById('connectionDot');
    const statusText = document.getElementById('connectionStatus');
    const connectBtn = document.getElementById('connectBtn');
    const disconnectBtn = document.getElementById('disconnectBtn');
    
    dot.className = 'status-dot ' + status;
    
    switch(status) {
      case 'connected':
        statusText.textContent = 'Connected';
        statusText.style.color = 'var(--success)';
        connectBtn.disabled = true;
        disconnectBtn.disabled = false;
        break;
      case 'disconnected':
        statusText.textContent = 'Disconnected';
        statusText.style.color = 'var(--danger)';
        connectBtn.disabled = false;
        disconnectBtn.disabled = true;
        break;
      case 'connecting':
        statusText.textContent = 'Connecting...';
        statusText.style.color = '#f6c23e';
        connectBtn.disabled = true;
        disconnectBtn.disabled = true;
        break;
    }
}
  
// Connect button event handler
document.getElementById('connectBtn').addEventListener('click', function() {
  updateConnectionStatus('connecting');
  
  // Simulate connection delay
  setTimeout(() => {
    updateConnectionStatus('connected');
    // Your existing connection code here
  }, 1500);
});

// Disconnect button event handler
document.getElementById('disconnectBtn').addEventListener('click', function() {
  updateConnectionStatus('disconnected');
  // Your existing disconnection code here
});

// Initialize with connected status since system connects on start
document.addEventListener('DOMContentLoaded', function() {
  updateConnectionStatus('connected');
  updateServerTime();
});
window.addEventListener('DOMContentLoaded', startConnection);
