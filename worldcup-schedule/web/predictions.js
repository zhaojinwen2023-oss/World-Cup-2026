const DATA_URL = "../data/tournament_predictions.json";
const TEAM_NAME_ZH = {
  Algeria: "阿尔及利亚", Argentina: "阿根廷", Australia: "澳大利亚", Austria: "奥地利", Belgium: "比利时", "Bosnia and Herzegovina": "波黑", Brazil: "巴西", Canada: "加拿大", "Cape Verde": "佛得角", Colombia: "哥伦比亚", Croatia: "克罗地亚", "Curaçao": "库拉索", "Czech Republic": "捷克", "DR Congo": "刚果（金）", Ecuador: "厄瓜多尔", Egypt: "埃及", England: "英格兰", France: "法国", Germany: "德国", Ghana: "加纳", Haiti: "海地", Iran: "伊朗", Iraq: "伊拉克", "Ivory Coast": "科特迪瓦", Japan: "日本", Jordan: "约旦", Mexico: "墨西哥", Morocco: "摩洛哥", Netherlands: "荷兰", "New Zealand": "新西兰", Norway: "挪威", Panama: "巴拿马", Paraguay: "巴拉圭", Portugal: "葡萄牙", Qatar: "卡塔尔", "Saudi Arabia": "沙特阿拉伯", Scotland: "苏格兰", Senegal: "塞内加尔", "South Africa": "南非", "South Korea": "韩国", Spain: "西班牙", Sweden: "瑞典", Switzerland: "瑞士", Tunisia: "突尼斯", Turkey: "土耳其", "United States": "美国", Uruguay: "乌拉圭", Uzbekistan: "乌兹别克斯坦",
};
const STAGES = [
  ["round_of_32", "32强"], ["round_of_16", "16强"], ["quarterfinal", "8强"], ["semifinal", "4强"], ["final", "决赛"], ["champion", "冠军"],
];
let modelData = {};
let activeView = "overview";
let championChart;
let groupChart;

document.addEventListener("DOMContentLoaded", init);

async function init() {
  if (new URLSearchParams(window.location.search).get("embedded") === "1") document.body.classList.add("embedded");
  bindControls();
  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    modelData = await response.json();
    document.querySelector("#loadingState").hidden = true;
    document.querySelectorAll(".dashboard-view").forEach((panel) => { panel.hidden = panel.dataset.panel !== activeView; });
    renderAll();
    notifyParentHeight();
  } catch (error) {
    document.querySelector("#loadingState").textContent = "预测数据暂不可用，请先运行完整预测脚本";
    console.error(error);
  }
}

function bindControls() {
  document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  document.querySelector("#groupSelect").addEventListener("change", renderGroup);
  document.querySelector("#pathTeamSelect").addEventListener("change", renderPath);
  document.querySelector("#teamSearch").addEventListener("input", renderStageTable);
  window.addEventListener("resize", () => { championChart?.resize(); groupChart?.resize(); });
}

function switchView(view) {
  activeView = view;
  document.querySelectorAll("[data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  document.querySelectorAll("[data-panel]").forEach((panel) => { panel.hidden = panel.dataset.panel !== view; });
  if (view === "groups") renderGroup();
  if (view === "paths") renderPath();
  requestAnimationFrame(() => { championChart?.resize(); groupChart?.resize(); notifyParentHeight(); });
}

function renderAll() {
  const teams = modelData.team_probabilities || [];
  const leader = teams[0];
  document.querySelector("#modelMeta").textContent = `${modelData.model_version} · 更新 ${formatDate(modelData.generated_at)}`;
  document.querySelector("#championLeader").textContent = leader ? `${displayTeam(leader.team)} ${formatPercent(leader.champion)}` : "-";
  document.querySelector("#summaryStrip").innerHTML = [
    ["模拟次数", Number(modelData.simulations || 0).toLocaleString("zh-CN"), "完整赛事路径"],
    ["已纳入球队", teams.length, "12组共48队"],
    ["最高冠军概率", leader ? formatPercent(leader.champion) : "-", leader ? displayTeam(leader.team) : "-"],
    ["剩余单场预测", (modelData.match_predictions || []).length, "未结束小组赛"],
  ].map(([label, value, note]) => `<div class="summary-item"><span>${label}</span><strong>${value}</strong><p>${note}</p></div>`).join("");
  renderChampionChart();
  renderStageTable();
  populateSelectors();
  renderGroup();
  renderPath();
  renderMatches();
  renderUpsets();
  document.querySelector("#modelMethod").textContent = `${modelData.methodology?.match_model || ""} ${modelData.methodology?.knockout || ""}`;
}

function renderChampionChart() {
  if (!window.echarts) {
    document.querySelector("#championChart").textContent = "图表组件未加载，完整数据请查看下方概率表。";
    return;
  }
  const teams = (modelData.team_probabilities || []).slice(0, 16).reverse();
  championChart = window.echarts.init(document.querySelector("#championChart"));
  championChart.setOption({
    animationDuration: 450,
    grid: { left: 76, right: 42, top: 16, bottom: 24 },
    xAxis: { type: "value", axisLabel: { formatter: "{value}%", color: "#667370" }, splitLine: { lineStyle: { color: "#edf0ee" } } },
    yAxis: { type: "category", data: teams.map((team) => displayTeam(team.team)), axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: "#1d2827", fontWeight: 700 } },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value) => `${Number(value).toFixed(1)}%` },
    series: [{ type: "bar", data: teams.map((team) => team.champion), barMaxWidth: 15, itemStyle: { color: "#21534a", borderRadius: [0, 3, 3, 0] }, label: { show: true, position: "right", formatter: "{c}%", color: "#21534a", fontWeight: 800 } }],
  });
}

function renderStageTable() {
  const query = document.querySelector("#teamSearch").value.trim().toLowerCase();
  const rows = (modelData.team_probabilities || []).filter((team) => !query || `${team.team}${displayTeam(team.team)}`.toLowerCase().includes(query));
  document.querySelector("#stageTableBody").innerHTML = rows.map((team) => `<tr><td><strong>${displayTeam(team.team)}</strong></td><td>${team.group}</td><td>${formatPercent(team.round_of_32)}</td><td>${formatPercent(team.round_of_16)}</td><td>${formatPercent(team.quarterfinal)}</td><td>${formatPercent(team.semifinal)}</td><td>${formatPercent(team.final)}</td><td><strong>${formatPercent(team.champion)}</strong></td><td>${escapeHtml(team.most_likely_path)}</td></tr>`).join("");
}

function populateSelectors() {
  document.querySelector("#groupSelect").innerHTML = (modelData.group_probabilities || []).map((group) => `<option value="${group.group}">${group.group}组</option>`).join("");
  document.querySelector("#pathTeamSelect").innerHTML = (modelData.team_probabilities || []).map((team) => `<option value="${escapeHtml(team.team)}">${displayTeam(team.team)}</option>`).join("");
}

function renderGroup() {
  const groupName = document.querySelector("#groupSelect").value || "A";
  const group = (modelData.group_probabilities || []).find((item) => item.group === groupName);
  if (!group) return;
  document.querySelector("#groupTableBody").innerHTML = group.teams.map((team) => { const p = team.group_position_probabilities; return `<tr><td><strong>${displayTeam(team.team)}</strong></td><td>${formatPercent(p["1"])}</td><td>${formatPercent(p["2"])}</td><td>${formatPercent(p["3"])}</td><td>${formatPercent(p["4"])}</td><td><strong>${formatPercent(team.round_of_32)}</strong></td></tr>`; }).join("");
  if (!window.echarts) return;
  groupChart ||= window.echarts.init(document.querySelector("#groupChart"));
  groupChart.setOption({
    grid: { left: 78, right: 28, top: 34, bottom: 32 },
    legend: { data: ["第一", "第二", "第三", "第四"], top: 0, textStyle: { color: "#667370" } },
    xAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" }, splitLine: { lineStyle: { color: "#edf0ee" } } },
    yAxis: { type: "category", data: group.teams.map((team) => displayTeam(team.team)), axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: "#1d2827", fontWeight: 700 } },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value) => `${Number(value).toFixed(1)}%` },
    series: ["1", "2", "3", "4"].map((position, index) => ({ name: ["第一", "第二", "第三", "第四"][index], type: "bar", stack: "rank", data: group.teams.map((team) => team.group_position_probabilities[position]), itemStyle: { color: ["#21534a", "#4f7d72", "#b98217", "#cfd6d2"][index] } })),
  });
}

function renderPath() {
  const teamName = document.querySelector("#pathTeamSelect").value || modelData.team_probabilities?.[0]?.team;
  const team = (modelData.team_probabilities || []).find((item) => item.team === teamName);
  if (!team) return;
  document.querySelector("#pathSummary").textContent = team.most_likely_path;
  document.querySelector("#pathRail").innerHTML = STAGES.map(([key, label]) => `<div class="path-stage ${team[key] >= 50 ? "active" : ""}"><span>${label}</span><strong>${formatPercent(team[key])}</strong></div>`).join("");
  const strength = team.strength || {};
  document.querySelector("#teamMetrics").innerHTML = [["Elo", strength.elo ?? "-"], ["FIFA排名", strength.fifa_rank ?? "未导入"], ["进攻强度", Number(strength.attack || 0).toFixed(2)], ["防守系数", Number(strength.defense || 0).toFixed(2)], ["近期状态", formatPercent(Number(strength.form || 0) * 100)]].map(([label, value]) => `<div class="metric-cell"><span>${label}</span><strong>${value}</strong></div>`).join("");
}

function renderMatches() {
  document.querySelector("#matchTableBody").innerHTML = (modelData.match_predictions || []).map((match) => `<tr><td><strong>${displayTeam(match.home_team)} vs ${displayTeam(match.away_team)}</strong></td><td>${match.group}</td><td>${match.expected_home_goals} - ${match.expected_away_goals}</td><td>${formatPercent(match.home_win_probability)}</td><td>${formatPercent(match.draw_probability)}</td><td>${formatPercent(match.away_win_probability)}</td><td><strong>${match.most_likely_score}</strong></td></tr>`).join("");
}

function renderUpsets() {
  document.querySelector("#upsetList").innerHTML = (modelData.upset_matches || []).map((match, index) => `<article class="upset-row"><span class="upset-rank">${String(index + 1).padStart(2, "0")}</span><div class="upset-match"><strong>${displayTeam(match.underdog)} 挑战 ${displayTeam(match.favorite)}</strong><span>第${match.match_id}场 · 评分差 ${match.rating_difference}</span></div><span class="upset-score">最可能 ${match.most_likely_score}</span><strong class="upset-probability">${formatPercent(match.upset_probability)}</strong></article>`).join("");
}

function displayTeam(team) { return TEAM_NAME_ZH[team] || team; }
function formatPercent(value) { return `${Number(value || 0).toFixed(1)}%`; }
function formatDate(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value || "-") : new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", dateStyle: "medium", timeStyle: "short" }).format(date); }
function escapeHtml(value) { const node = document.createElement("span"); node.textContent = String(value ?? ""); return node.innerHTML; }

function notifyParentHeight() {
  if (window.parent === window) return;
  const shell = document.querySelector(".dashboard-shell");
  const height = Math.ceil(shell?.getBoundingClientRect().height || document.body.scrollHeight) + 8;
  window.setTimeout(() => window.parent.postMessage({ type: "worldcup-prediction-height", height }, "*"), 0);
}

window.addEventListener("message", (event) => {
  if (event.data?.type !== "worldcup-prediction-visible") return;
  requestAnimationFrame(() => { championChart?.resize(); groupChart?.resize(); notifyParentHeight(); });
});

if ("ResizeObserver" in window) new ResizeObserver(notifyParentHeight).observe(document.documentElement);
