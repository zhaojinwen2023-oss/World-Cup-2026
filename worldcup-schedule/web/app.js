const APP_DATA_URL = "../data/app_data.json";
const PREDICTIONS_DATA_URL = "../data/champion_predictions.json";
const FAVORITES_KEY = "worldcup2026.favoriteMatchIds.v3";
const REFRESH_INTERVAL_MS = 5 * 60 * 1000;

const TIME_ZONES = {
  beijing: { label: "北京时间", zone: "Asia/Shanghai" },
  eastern: { label: "美国东部", zone: "America/New_York" },
  western: { label: "美国西部", zone: "America/Los_Angeles" },
};

const TEAM_NAME_ZH = {
  Algeria: "阿尔及利亚",
  Argentina: "阿根廷",
  Australia: "澳大利亚",
  Austria: "奥地利",
  Belgium: "比利时",
  "Bosnia and Herzegovina": "波黑",
  Brazil: "巴西",
  Canada: "加拿大",
  "Cape Verde": "佛得角",
  Colombia: "哥伦比亚",
  Croatia: "克罗地亚",
  "Curaçao": "库拉索",
  "Czech Republic": "捷克",
  "DR Congo": "刚果（金）",
  Ecuador: "厄瓜多尔",
  Egypt: "埃及",
  England: "英格兰",
  France: "法国",
  Germany: "德国",
  Ghana: "加纳",
  Haiti: "海地",
  Iran: "伊朗",
  Iraq: "伊拉克",
  "Ivory Coast": "科特迪瓦",
  Japan: "日本",
  Jordan: "约旦",
  Mexico: "墨西哥",
  Morocco: "摩洛哥",
  Netherlands: "荷兰",
  "New Zealand": "新西兰",
  Norway: "挪威",
  Panama: "巴拿马",
  Paraguay: "巴拉圭",
  Portugal: "葡萄牙",
  Qatar: "卡塔尔",
  "Saudi Arabia": "沙特阿拉伯",
  Scotland: "苏格兰",
  Senegal: "塞内加尔",
  "South Africa": "南非",
  "South Korea": "韩国",
  Spain: "西班牙",
  Sweden: "瑞典",
  Switzerland: "瑞士",
  Tunisia: "突尼斯",
  Turkey: "土耳其",
  "United States": "美国",
  Uruguay: "乌拉圭",
  Uzbekistan: "乌兹别克斯坦",
};

const CALENDAR_MONTHS = [
  { year: 2026, month: 6, label: "2026年6月" },
  { year: 2026, month: 7, label: "2026年7月" },
];

const CALENDAR_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

const CALENDAR_TYPE_META = {
  rest: { label: "休息日", className: "calendar-rest" },
  group: { label: "小组赛", className: "calendar-group" },
  r32: { label: "32强", className: "calendar-r32" },
  r16: { label: "16强", className: "calendar-r16" },
  qf: { label: "1/4", className: "calendar-qf" },
  semi: { label: "半决赛", className: "calendar-semi" },
  third: { label: "三四名", className: "calendar-third" },
  final: { label: "决赛", className: "calendar-final" },
};

const CALENDAR_STAGE_ORDER = ["rest", "group", "r32", "r16", "qf", "semi", "third", "final"];

const BRACKET_HALVES = [
  {
    label: "上半区",
    semifinal: 101,
    quarterfinals: [
      { id: 97, r16: [89, 90], r32: [74, 77, 73, 75] },
      { id: 98, r16: [93, 94], r32: [83, 84, 81, 82] },
    ],
  },
  {
    label: "下半区",
    semifinal: 102,
    quarterfinals: [
      { id: 99, r16: [91, 92], r32: [76, 78, 79, 80] },
      { id: 100, r16: [95, 96], r32: [86, 88, 85, 87] },
    ],
  },
];

const PREDICTION_METRICS = {
  probability: {
    key: "champion_probability",
    label: "冠军概率",
    suffix: "%",
    digits: 1,
    caption: "模型输出，不对应任何博彩平台赔率",
  },
  strength: {
    key: "strength_score",
    label: "球队实力",
    suffix: "",
    digits: 0,
    caption: "综合阵容质量、长期表现与攻防效率",
  },
  path: {
    key: "path_score",
    label: "晋级路径",
    suffix: "",
    digits: 0,
    caption: "分值越高，模型评估的潜在晋级路径越有利",
  },
};

let appData = {};
let matches = [];
let standings = [];
let topScorers = [];
let knockout = [];
let bestThirds = [];
let predictionsData = {};
let favoriteIds = new Set();
let activeTab = "schedule";
let activeFilter = "all";
let searchTerm = "";
let scheduleView = "calendar";
let selectedDateKey = "";
let headToHeadTeamA = "";
let headToHeadTeamB = "";
let predictionMetric = "probability";

const panels = {
  schedule: document.querySelector("#schedulePanel"),
  live: document.querySelector("#livePanel"),
  standings: document.querySelector("#standingsPanel"),
  scorers: document.querySelector("#scorersPanel"),
  headToHead: document.querySelector("#headToHeadPanel"),
  knockout: document.querySelector("#knockoutPanel"),
  predictions: document.querySelector("#predictionsPanel"),
  favorites: document.querySelector("#favoritesPanel"),
};

const listEl = document.querySelector("#matchList");
const calendarViewEl = document.querySelector("#calendarView");
const dayViewEl = document.querySelector("#dayView");
const dayTitleEl = document.querySelector("#dayTitle");
const liveListEl = document.querySelector("#liveList");
const favoriteListEl = document.querySelector("#favoriteList");
const standingsListEl = document.querySelector("#standingsList");
const scorersListEl = document.querySelector("#scorersList");
const headToHeadListEl = document.querySelector("#headToHeadList");
const teamASelect = document.querySelector("#teamASelect");
const teamBSelect = document.querySelector("#teamBSelect");
const knockoutListEl = document.querySelector("#knockoutList");
const predictionLeadersEl = document.querySelector("#predictionLeaders");
const predictionRankingEl = document.querySelector("#predictionRanking");
const predictionResidualEl = document.querySelector("#predictionResidual");
const methodologyGridEl = document.querySelector("#methodologyGrid");
const predictionSystemFrame = document.querySelector("#predictionSystemFrame");
const counterEl = document.querySelector("#matchCounter");
const statusEl = document.querySelector("#statusMessage");
const searchInput = document.querySelector("#searchInput");
const lastUpdatedEl = document.querySelector("#lastUpdated");

document.addEventListener("DOMContentLoaded", init);

async function init() {
  bindControls();
  registerServiceWorker();
  await loadData();
  window.setInterval(() => loadData(true), REFRESH_INTERVAL_MS);
}

function bindControls() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });

  document.querySelectorAll(".filter-chip").forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter;
      document.querySelectorAll(".filter-chip").forEach((item) => item.classList.toggle("active", item === button));
      renderSchedule();
    });
  });

  searchInput?.addEventListener("input", (event) => {
    searchTerm = event.target.value.trim().toLowerCase();
    renderSchedule();
  });

  teamASelect?.addEventListener("change", (event) => {
    headToHeadTeamA = event.target.value;
    renderHeadToHead();
  });

  teamBSelect?.addEventListener("change", (event) => {
    headToHeadTeamB = event.target.value;
    renderHeadToHead();
  });

  document.body.addEventListener("click", (event) => {
    const calendarButton = event.target.closest("[data-calendar-date]");
    if (calendarButton) {
      openScheduleDay(calendarButton.dataset.calendarDate);
      return;
    }

    const backButton = event.target.closest("[data-back-calendar]");
    if (backButton) {
      showScheduleCalendar();
      return;
    }

    const metricButton = event.target.closest("[data-prediction-metric]");
    if (metricButton) {
      predictionMetric = metricButton.dataset.predictionMetric;
      renderPredictions();
      return;
    }

    const button = event.target.closest("[data-favorite-id]");
    if (!button) return;
    toggleFavorite(button.dataset.favoriteId);
  });

  document.querySelector("#exportIcsBtn").addEventListener("click", exportFavoritesIcs);
  document.querySelector("#exportCsvBtn").addEventListener("click", exportFavoritesCsv);

  window.addEventListener("message", (event) => {
    if (event.source !== predictionSystemFrame?.contentWindow || event.data?.type !== "worldcup-prediction-height") return;
    const height = Math.min(5000, Math.max(640, Number(event.data.height) || 0));
    const nextHeight = `${height}px`;
    if (predictionSystemFrame.style.height !== nextHeight) predictionSystemFrame.style.height = nextHeight;
  });
}

function registerServiceWorker() {
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    navigator.serviceWorker.register("./service-worker.js").catch((error) => console.warn("Service worker registration failed", error));
  }
}

async function loadData(isBackground = false) {
  try {
    const [response, predictionResponse] = await Promise.all([
      fetch(APP_DATA_URL, { cache: "no-store" }),
      fetch(PREDICTIONS_DATA_URL, { cache: "no-store" }).catch(() => null),
    ]);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    appData = await response.json();
    if (predictionResponse?.ok) predictionsData = await predictionResponse.json();
    matches = (appData.matches || []).map(enrichClientMatch).sort((a, b) => a.kickoff - b.kickoff);
    standings = appData.standings || [];
    topScorers = normalizeTopScorers(appData.top_scorers || []);
    knockout = appData.knockout || [];
    bestThirds = appData.best_thirds || [];
    favoriteIds = loadFavoriteIds(matches);
    syncHeadToHeadSelectors();
    lastUpdatedEl.textContent = appData.generated_at || appData.live_last_updated || "-";
    hideStatus();
    renderActiveTab();
  } catch (error) {
    console.error(error);
    if (!matches.length || !isBackground) {
      showStatus("暂时无法获取最新比分，当前显示上次更新数据");
    }
  }
}

function enrichClientMatch(match) {
  const kickoff = new Date(match.kickoff_utc);
  return {
    ...match,
    matchId: String(match.match_id),
    kickoff,
    dateKeys: {
      beijing: dateKey(kickoff, TIME_ZONES.beijing.zone),
      eastern: dateKey(kickoff, TIME_ZONES.eastern.zone),
      western: dateKey(kickoff, TIME_ZONES.western.zone),
    },
  };
}

function loadFavoriteIds(seedMatches) {
  const saved = localStorage.getItem(FAVORITES_KEY);
  if (saved) {
    try {
      return new Set(JSON.parse(saved).map(String));
    } catch {
      localStorage.removeItem(FAVORITES_KEY);
    }
  }
  return new Set(seedMatches.filter((match) => match.is_favorite).map((match) => String(match.match_id)));
}

function saveFavoriteIds() {
  localStorage.setItem(FAVORITES_KEY, JSON.stringify([...favoriteIds]));
}

function toggleFavorite(matchId) {
  if (favoriteIds.has(matchId)) {
    favoriteIds.delete(matchId);
  } else {
    favoriteIds.add(matchId);
  }
  saveFavoriteIds();
  renderActiveTab();
}

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.tab === tab));
  Object.entries(panels).forEach(([key, panel]) => panel.classList.toggle("active", key === tab));
  renderActiveTab();
}

function renderActiveTab() {
  if (activeTab === "schedule") renderSchedule();
  if (activeTab === "live") renderLive();
  if (activeTab === "standings") renderStandings();
  if (activeTab === "scorers") renderScorers();
  if (activeTab === "headToHead") renderHeadToHead();
  if (activeTab === "knockout") renderKnockout();
  if (activeTab === "predictions") renderPredictions();
  if (activeTab === "favorites") renderFavorites();
}

function renderSchedule() {
  if (scheduleView === "day" && selectedDateKey) {
    renderScheduleDay();
    return;
  }
  renderScheduleCalendar();
}

function renderScheduleCalendar() {
  const visibleMatches = filterMatches();
  counterEl.textContent = searchTerm || activeFilter !== "all" ? `${visibleMatches.length} 场` : "月历";
  calendarViewEl.hidden = false;
  dayViewEl.hidden = true;
  listEl.innerHTML = "";
  hideStatus();
  const matchesByDate = groupBy(visibleMatches, (match) => match.dateKeys.beijing);
  calendarViewEl.innerHTML = `${renderCalendarLegend()}${CALENDAR_MONTHS.map((month) => renderMonthCalendar(month, matchesByDate)).join("")}`;
}

function renderScheduleDay() {
  const originalDayMatches = matchesForDate(selectedDateKey, matches);
  const dayMatches = matchesForDate(selectedDateKey, filterMatches());
  counterEl.textContent = `${dayMatches.length} 场`;
  calendarViewEl.hidden = true;
  dayViewEl.hidden = false;
  dayTitleEl.textContent = formatDateTitle(selectedDateKey);
  listEl.innerHTML = "";
  if (!dayMatches.length) {
    showStatus(originalDayMatches.length ? "当前筛选条件下没有比赛" : "这一天没有比赛");
    return;
  }
  hideStatus();
  dayMatches.forEach((match) => listEl.appendChild(renderMatchCard(match)));
}

function renderLive() {
  const liveMatches = matches.filter((match) => match.is_live);
  liveListEl.innerHTML = "";
  if (liveMatches.length) {
    counterEl.textContent = `${liveMatches.length} 场`;
    liveMatches.forEach((match) => liveListEl.appendChild(renderMatchCard(match)));
    return;
  }
  const next = matches.find((match) => match.status === "scheduled" && match.kickoff > new Date());
  counterEl.textContent = next ? "下一场" : "0 场";
  liveListEl.innerHTML = next ? `<section class="empty-state">当前没有进行中的比赛</section>` : `<section class="empty-state">当前没有进行中的比赛</section>`;
  if (next) liveListEl.appendChild(renderMatchCard(next));
}

function renderFavorites() {
  const selected = favoriteMatches();
  counterEl.textContent = `${selected.length} 场`;
  favoriteListEl.innerHTML = "";
  if (!selected.length) {
    favoriteListEl.innerHTML = `<section class="empty-state">还没有关注的比赛</section>`;
    return;
  }
  selected.forEach((match) => favoriteListEl.appendChild(renderMatchCard(match)));
}

function renderStandings() {
  counterEl.textContent = `${standings.length} 队`;
  const groups = groupBy(standings, (row) => row.group);
  const bestByTeam = Object.fromEntries(bestThirds.map((row) => [row.team, row]));
  standingsListEl.innerHTML = "";
  Object.keys(groups)
    .sort()
    .forEach((group) => {
      const card = document.createElement("section");
      card.className = "group-card";
      const rows = groups[group].sort((a, b) => a.rank - b.rank);
      card.innerHTML = `
        <h2>${escapeHtml(group)}组</h2>
        <table class="standings-table">
          <thead><tr><th>#</th><th>球队</th><th>积分</th><th>净胜</th><th>进球</th></tr></thead>
          <tbody>${rows.map((row) => standingsRow(row, bestByTeam[row.team])).join("")}</tbody>
        </table>
      `;
      standingsListEl.appendChild(card);
    });
}

function standingsRow(row, bestThird) {
  const classes = [];
  const showBestThird = bestThird && (Number(row.played || 0) >= 3 || row.qualified_status === "qualified" || row.qualified_status === "eliminated");
  if (row.qualified_status === "qualified") classes.push("qualified");
  if (row.qualified_status === "possible") classes.push("pending");
  if (row.qualified_status === "eliminated") classes.push("eliminated");
  if (showBestThird && bestThird?.best_third_qualified) classes.push("best");
  const mark = showBestThird ? `<span class="best-third">第三第${bestThird.best_third_rank}${bestThird.best_third_qualified ? " 晋级区" : ""}</span>` : "";
  return `
    <tr class="${classes.join(" ")}">
      <td>${escapeHtml(row.rank)}</td>
      <td>${escapeHtml(displayTeamName(row.team))} ${mark}</td>
      <td>${escapeHtml(row.points)}</td>
      <td>${escapeHtml(row.goal_difference)}</td>
      <td>${escapeHtml(row.goals_for)}</td>
    </tr>
  `;
}

function renderScorers() {
  counterEl.textContent = `${topScorers.length} 人`;
  scorersListEl.innerHTML = "";
  if (!topScorers.length) {
    scorersListEl.innerHTML = `<section class="empty-state">暂无射手榜数据；比赛开始并且 API-Football 返回球员进球数据后会自动显示</section>`;
    return;
  }
  scorersListEl.innerHTML = `
    <section class="scorers-card">
      <div class="scorers-head">
        <h2>射手榜</h2>
        <span>${escapeHtml(appData.top_scorers_last_updated || appData.generated_at || "")}</span>
      </div>
      <table class="scorers-table">
        <thead><tr><th>#</th><th>球员</th><th>国家</th><th>进球</th><th>助攻</th></tr></thead>
        <tbody>${topScorers.map(scorerRow).join("")}</tbody>
      </table>
    </section>
  `;
}

function scorerRow(row) {
  return `
    <tr>
      <td>${escapeHtml(row.rank)}</td>
      <td>
        <strong>${escapeHtml(row.player)}</strong>
        ${row.minutes ? `<span>${escapeHtml(row.minutes)} 分钟</span>` : ""}
      </td>
      <td>${escapeHtml(displayTeamName(row.team))}</td>
      <td><strong>${escapeHtml(row.goals)}</strong></td>
      <td>${escapeHtml(row.assists)}</td>
    </tr>
  `;
}

function renderHeadToHead() {
  const selected = headToHeadMatches();
  counterEl.textContent = `${selected.length} 场`;
  headToHeadListEl.innerHTML = "";
  if (!selected.length) {
    headToHeadListEl.innerHTML = `<section class="empty-state">当前筛选下没有找到对决战果</section>`;
    return;
  }
  const summary = headToHeadSummary(selected);
  headToHeadListEl.innerHTML = `
    <section class="h2h-summary-card">
      <h2>${escapeHtml(summary.title)}</h2>
      <div class="h2h-summary-grid">
        <span>${summary.total} 场</span>
        <span>${summary.finished} 场已结束</span>
        <span>${summary.live} 场进行中</span>
      </div>
    </section>
    ${selected.map(headToHeadRow).join("")}
  `;
}

function headToHeadRow(match) {
  return `
    <article class="h2h-card">
      <div>
        <div class="stage-line">
          <span class="stage-badge ${stageClass(match)}">${escapeHtml(match.stage_label)}</span>
          <span class="match-id">#${escapeHtml(match.matchId)}</span>
          <span class="status-badge ${statusClass(match)}">${escapeHtml(statusText(match))}</span>
        </div>
        <h2 class="h2h-title">${escapeHtml(matchTitle(match))}</h2>
      </div>
      <strong class="h2h-score">${escapeHtml(match.score || scoreFallback(match))}</strong>
      <div class="h2h-meta">${escapeHtml(formatInZone(match.kickoff, TIME_ZONES.beijing.zone))} / ${escapeHtml(match.city)} / ${escapeHtml(match.stadium)}</div>
    </article>
  `;
}

function renderKnockout() {
  counterEl.textContent = `${knockout.length} 场`;
  knockoutListEl.innerHTML = "";
  const matchById = Object.fromEntries(matches.map((match) => [match.match_id, match]));
  knockoutListEl.insertAdjacentHTML("beforeend", renderKnockoutGraphic(matchById));
  knockout.forEach((slot) => {
    knockoutListEl.appendChild(renderKnockoutCard(slot, matchById[slot.match_id] || {}));
  });
}

function renderPredictions() {
  if (predictionSystemFrame) {
    counterEl.textContent = "50,000 次";
    predictionSystemFrame.contentWindow?.postMessage({ type: "worldcup-prediction-visible" }, "*");
    return;
  }
  const teams = Array.isArray(predictionsData.teams) ? predictionsData.teams : [];
  counterEl.textContent = teams.length ? `${teams.length} 队` : "模型";
  if (!teams.length) {
    predictionLeadersEl.innerHTML = "";
    predictionRankingEl.innerHTML = `<section class="empty-state">预测数据暂不可用</section>`;
    return;
  }

  const metric = PREDICTION_METRICS[predictionMetric] || PREDICTION_METRICS.probability;
  const sorted = [...teams].sort((a, b) => Number(b[metric.key] || 0) - Number(a[metric.key] || 0));
  const maximum = Number(sorted[0][metric.key] || 1);

  document.querySelectorAll("[data-prediction-metric]").forEach((button) => {
    const active = button.dataset.predictionMetric === predictionMetric;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });

  document.querySelector("#predictionVersion").textContent = predictionsData.model_version || "统计模型";
  document.querySelector("#predictionUpdated").textContent = `更新：${formatPredictionDate(predictionsData.generated_at)}`;
  document.querySelector("#predictionSource").textContent = predictionsData.source_label || "统计模型";
  document.querySelector("#predictionRankingTitle").textContent = `${metric.label}排名`;
  document.querySelector("#predictionRankingCaption").textContent = metric.caption;
  document.querySelector("#predictionHeroLead").innerHTML = `
    <span>模型最高冠军概率</span>
    <strong>${formatPredictionValue(sortedByProbability(teams)[0].champion_probability, PREDICTION_METRICS.probability)}</strong>
    <p>${escapeHtml(displayTeamName(sortedByProbability(teams)[0].team))}</p>
  `;

  predictionLeadersEl.innerHTML = sorted
    .slice(0, 3)
    .map(
      (team, index) => `
        <article class="prediction-leader">
          <span>0${index + 1}</span>
          <div>
            <h3>${escapeHtml(displayTeamName(team.team))}</h3>
            <p>${escapeHtml(team.summary)}</p>
          </div>
          <strong>${formatPredictionValue(team[metric.key], metric)}</strong>
        </article>
      `,
    )
    .join("");

  predictionRankingEl.innerHTML = sorted
    .map((team, index) => predictionRow(team, index, metric, maximum))
    .join("");

  predictionResidualEl.hidden = predictionMetric !== "probability";
  predictionResidualEl.innerHTML = predictionMetric === "probability" ? `<span>其余球队合计</span><strong>${formatPredictionValue(predictionsData.other_probability || 0, PREDICTION_METRICS.probability)}</strong>` : "";

  methodologyGridEl.innerHTML = (predictionsData.methodology || [])
    .map(
      (item) => `
        <article class="methodology-item">
          <div><h3>${escapeHtml(item.label)}</h3><strong>${escapeHtml(item.weight)}%</strong></div>
          <div class="methodology-track" aria-hidden="true"><span style="--method-weight: ${Number(item.weight) || 0}%"></span></div>
          <p>${escapeHtml(item.description)}</p>
        </article>
      `,
    )
    .join("");
}

function predictionRow(team, index, metric, maximum) {
  const value = Number(team[metric.key] || 0);
  const width = maximum ? Math.max(4, (value / maximum) * 100) : 0;
  return `
    <article class="prediction-row">
      <span class="prediction-rank">${String(index + 1).padStart(2, "0")}</span>
      <div class="prediction-team">
        <div><strong>${escapeHtml(displayTeamName(team.team))}</strong><span>${escapeHtml(team.summary)}</span></div>
        <div class="prediction-bar" aria-hidden="true"><span style="--prediction-width: ${width.toFixed(1)}%"></span></div>
      </div>
      <strong class="prediction-value">${formatPredictionValue(value, metric)}</strong>
    </article>
  `;
}

function sortedByProbability(teams) {
  return [...teams].sort((a, b) => Number(b.champion_probability || 0) - Number(a.champion_probability || 0));
}

function formatPredictionValue(value, metric) {
  return `${Number(value || 0).toFixed(metric.digits)}${metric.suffix}`;
}

function formatPredictionDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value || "-");
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: TIME_ZONES.beijing.zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

function filterMatches() {
  const today = dateKey(new Date(), TIME_ZONES.beijing.zone);
  const tomorrow = dateKey(new Date(Date.now() + 24 * 60 * 60 * 1000), TIME_ZONES.beijing.zone);
  return matches.filter((match) => {
    const isFavorite = favoriteIds.has(match.matchId);
    const filterOk =
      activeFilter === "all" ||
      (activeFilter === "today" && match.dateKeys.beijing === today) ||
      (activeFilter === "tomorrow" && match.dateKeys.beijing === tomorrow) ||
      (activeFilter === "live" && match.is_live) ||
      (activeFilter === "finished" && match.is_finished) ||
      (activeFilter === "scheduled" && match.status === "scheduled") ||
      (activeFilter === "favorites" && isFavorite);
    if (!filterOk) return false;

    const haystack = [
      match.home_team,
      match.away_team,
      displayTeamName(match.home_team),
      displayTeamName(match.away_team),
      match.home_placeholder,
      match.away_placeholder,
      displayTeamName(match.home_placeholder),
      displayTeamName(match.away_placeholder),
      match.city,
      match.country,
      match.stadium,
      match.stage,
      match.stage_label,
      match.status_label,
    ]
      .join(" ")
      .toLowerCase();
    return !searchTerm || haystack.includes(searchTerm);
  });
}

function renderMatchCard(match) {
  const isFavorite = favoriteIds.has(match.matchId);
  const card = document.createElement("article");
  card.className = `match-card${isFavorite ? " favorite" : ""}`;
  card.innerHTML = `
    <div class="card-header">
      <div>
        <div class="stage-line">
          <span class="stage-badge ${stageClass(match)}">${escapeHtml(match.stage_label)}</span>
          <span class="match-id">#${escapeHtml(match.matchId)}</span>
          <span class="status-badge ${statusClass(match)}">${escapeHtml(statusText(match))}</span>
        </div>
        <h2 class="match-title">${escapeHtml(matchTitle(match))}</h2>
      </div>
      <button class="favorite-button" type="button" aria-label="关注比赛" aria-pressed="${isFavorite}" data-favorite-id="${escapeHtml(match.matchId)}">${isFavorite ? "★" : "☆"}</button>
    </div>
    ${match.score ? `<div class="score-line">${escapeHtml(match.score)}${match.winner ? ` / 晋级：${escapeHtml(displayTeamName(match.winner))}` : ""}</div>` : ""}
    <div class="time-grid">${timeRows(match)}</div>
    <div class="location">${escapeHtml(match.city)} / ${escapeHtml(match.stadium)}</div>
    ${slotNote(match)}
    ${match.notes ? `<div class="notes">${escapeHtml(match.notes)}</div>` : ""}
  `;
  return card;
}

function renderKnockoutCard(slot, match) {
  const matchId = String(slot.match_id);
  const isFavorite = favoriteIds.has(matchId);
  const winner = slot.winner || match.winner || "";
  const card = document.createElement("article");
  card.className = `knockout-card${isFavorite ? " favorite" : ""}`;
  card.innerHTML = `
    <div class="knockout-head">
      <div class="stage-line">
        <span class="stage-badge ${stageClass(match)}">${escapeHtml(slot.round)}</span>
        <span class="match-id">#${escapeHtml(matchId)}</span>
        <span class="status-badge ${statusClass(match)}">${escapeHtml(statusText(match))}</span>
      </div>
      <button class="favorite-button" type="button" aria-label="关注淘汰赛" aria-pressed="${isFavorite}" data-favorite-id="${escapeHtml(matchId)}">${isFavorite ? "★" : "☆"}</button>
    </div>
    <div class="bracket-matchup">
      ${teamLine(slot.home_team, match.home_score, winner)}
      ${teamLine(slot.away_team, match.away_score, winner)}
    </div>
    ${match.score ? `<div class="score-line">${escapeHtml(match.score)}${winner ? ` / 晋级：${escapeHtml(displayTeamName(winner))}` : ""}</div>` : ""}
    <div class="slot-note">${escapeHtml(slot.home_source)} vs ${escapeHtml(slot.away_source)}</div>
  `;
  return card;
}

function statusText(match) {
  if (!match) return "未开始";
  const base = match.status_label || match.match_status || "未开始";
  return match.minute ? `${base} ${match.minute}'` : base;
}

function teamLine(team, score, winner) {
  const classes = [];
  if (winner && team === winner) classes.push("winner");
  if (winner && team !== winner) classes.push("eliminated");
  return `<div class="team-line ${classes.join(" ")}"><span>${escapeHtml(displayTeamName(shortBracketTeam(team)))}</span><strong>${score ?? ""}</strong></div>`;
}

function renderMonthCalendar(month, matchesByDate) {
  const first = new Date(Date.UTC(month.year, month.month - 1, 1));
  const daysInMonth = new Date(Date.UTC(month.year, month.month, 0)).getUTCDate();
  const leadingBlanks = (first.getUTCDay() + 6) % 7;
  const cells = [];
  for (let index = 0; index < leadingBlanks; index += 1) {
    cells.push('<div class="calendar-blank" aria-hidden="true"></div>');
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    const key = `${month.year}-${String(month.month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const dayMatches = (matchesByDate[key] || []).sort((a, b) => a.kickoff - b.kickoff);
    cells.push(renderCalendarDay(day, key, dayMatches));
  }
  const monthCount = Object.keys(matchesByDate).filter((key) => key.startsWith(`${month.year}-${String(month.month).padStart(2, "0")}`)).reduce((sum, key) => sum + matchesByDate[key].length, 0);
  return `
    <section class="month-card">
      <div class="month-head">
        <h2>${escapeHtml(month.label)}</h2>
        <span>${monthCount} 场</span>
      </div>
      <div class="weekday-row">${CALENDAR_WEEKDAYS.map((day) => `<span>${day}</span>`).join("")}</div>
      <div class="calendar-grid">${cells.join("")}</div>
    </section>
  `;
}

function renderCalendarDay(day, key, dayMatches) {
  const hasMatches = dayMatches.length > 0;
  const isToday = key === dateKey(new Date(), TIME_ZONES.beijing.zone);
  const type = calendarDayType(dayMatches);
  const meta = CALENDAR_TYPE_META[type];
  const classes = ["calendar-day", meta.className];
  if (hasMatches) classes.push("has-matches");
  if (dayMatches.some((match) => match.is_live)) classes.push("live");
  if (isToday) classes.push("is-today");
  const dayStatus = hasMatches ? `${dayMatches.length}场比赛` : "无比赛";
  const label = `${key}，${isToday ? "今天，" : ""}${dayStatus}`;
  const firstMatch = dayMatches[0];
  return `
    <button class="${classes.join(" ")}" data-calendar-date="${escapeHtml(key)}" type="button" ${hasMatches ? "" : "disabled"} ${isToday ? 'aria-current="date"' : ""} aria-label="${escapeHtml(label)}">
      <span class="day-number">${day}</span>
      ${hasMatches ? `<span class="day-count">${dayMatches.length}场</span><span class="day-preview">${escapeHtml(dayPreview(firstMatch))}</span>` : '<span class="day-preview">休息</span>'}
    </button>
  `;
}

function renderCalendarLegend() {
  return `
    <section class="calendar-legend" aria-label="月历颜色说明">
      ${CALENDAR_STAGE_ORDER.map((type) => `<span class="legend-item ${CALENDAR_TYPE_META[type].className}">${CALENDAR_TYPE_META[type].label}</span>`).join("")}
    </section>
  `;
}

function calendarDayType(dayMatches) {
  if (!dayMatches.length) return "rest";
  const types = dayMatches.map((match) => calendarTypeForStage(match.stage_label));
  return types.sort((a, b) => CALENDAR_STAGE_ORDER.indexOf(b) - CALENDAR_STAGE_ORDER.indexOf(a))[0] || "group";
}

function calendarTypeForStage(stageLabel) {
  if (stageLabel === "小组赛") return "group";
  if (stageLabel === "32强") return "r32";
  if (stageLabel === "16强") return "r16";
  if (stageLabel === "1/4决赛") return "qf";
  if (stageLabel === "半决赛") return "semi";
  if (stageLabel === "三四名") return "third";
  if (stageLabel === "决赛") return "final";
  return "group";
}

function dayPreview(match) {
  if (!match) return "";
  return match.stage === "Group Stage" && match.group ? `Group ${match.group}` : match.stage_label;
}

function openScheduleDay(dateKeyValue) {
  scheduleView = "day";
  selectedDateKey = dateKeyValue;
  activeTab = "schedule";
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.tab === "schedule"));
  Object.entries(panels).forEach(([key, panel]) => panel.classList.toggle("active", key === "schedule"));
  renderSchedule();
}

function showScheduleCalendar() {
  scheduleView = "calendar";
  selectedDateKey = "";
  renderSchedule();
}

function matchesForDate(key, sourceMatches = matches) {
  return sourceMatches.filter((match) => match.dateKeys.beijing === key).sort((a, b) => a.kickoff - b.kickoff);
}

function formatDateTitle(key) {
  const [year, month, day] = key.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  const weekday = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][date.getUTCDay()];
  return `${month}月${day}日 ${weekday}`;
}

function displayTeamName(name) {
  const text = String(name ?? "").trim();
  return TEAM_NAME_ZH[text] || text;
}

function normalizeTopScorers(rows) {
  return rows
    .map((row, index) => ({
      rank: Number(row.rank || index + 1),
      player: String(row.player || row.name || "").trim(),
      team: String(row.team || "").trim(),
      goals: Number(row.goals || 0),
      assists: row.assists ?? "",
      minutes: row.minutes ?? "",
    }))
    .filter((row) => row.player)
    .sort((a, b) => b.goals - a.goals || Number(b.assists || 0) - Number(a.assists || 0) || a.rank - b.rank)
    .map((row, index) => ({ ...row, rank: index + 1 }));
}

function syncHeadToHeadSelectors() {
  const teams = teamOptions();
  renderTeamSelect(teamASelect, teams, headToHeadTeamA);
  renderTeamSelect(teamBSelect, teams, headToHeadTeamB);
  if (!teams.some((team) => team.value === headToHeadTeamA)) headToHeadTeamA = "";
  if (!teams.some((team) => team.value === headToHeadTeamB)) headToHeadTeamB = "";
  if (teamASelect) teamASelect.value = headToHeadTeamA;
  if (teamBSelect) teamBSelect.value = headToHeadTeamB;
}

function renderTeamSelect(select, teams, selectedValue) {
  if (!select) return;
  select.innerHTML = [`<option value="">全部球队</option>`, ...teams.map((team) => `<option value="${escapeHtml(team.value)}">${escapeHtml(team.label)}</option>`)].join("");
  select.value = selectedValue;
}

function teamOptions() {
  const names = new Set();
  matches.forEach((match) => {
    if (isResolvedTeam(match.home_team)) names.add(match.home_team);
    if (isResolvedTeam(match.away_team)) names.add(match.away_team);
  });
  return [...names]
    .map((name) => ({ value: name, label: displayTeamName(name) }))
    .sort((a, b) => a.label.localeCompare(b.label, "zh-CN"));
}

function isResolvedTeam(name) {
  const text = String(name || "").trim();
  return Boolean(text) && !text.startsWith("待定") && !/Winner|Runner-up|Loser|3rd|Third/i.test(text);
}

function headToHeadMatches() {
  return matches
    .filter((match) => {
      const home = match.home_team;
      const away = match.away_team;
      if (!isResolvedTeam(home) || !isResolvedTeam(away)) return false;
      if (headToHeadTeamA && headToHeadTeamB) return new Set([home, away]).size === 2 && [home, away].includes(headToHeadTeamA) && [home, away].includes(headToHeadTeamB);
      if (headToHeadTeamA) return home === headToHeadTeamA || away === headToHeadTeamA;
      if (headToHeadTeamB) return home === headToHeadTeamB || away === headToHeadTeamB;
      return true;
    })
    .sort((a, b) => a.kickoff - b.kickoff);
}

function headToHeadSummary(selected) {
  const labelA = headToHeadTeamA ? displayTeamName(headToHeadTeamA) : "";
  const labelB = headToHeadTeamB ? displayTeamName(headToHeadTeamB) : "";
  const title = labelA && labelB ? `${labelA} vs ${labelB}` : labelA || labelB || "全部对决战果";
  return {
    title,
    total: selected.length,
    finished: selected.filter((match) => match.is_finished).length,
    live: selected.filter((match) => match.is_live).length,
  };
}

function scoreFallback(match) {
  if (match.status === "scheduled") return "未开始";
  if (match.home_score !== "" && match.away_score !== "") return `${match.home_score}-${match.away_score}`;
  return statusText(match);
}

function matchTitle(match) {
  return `${displayTeamName(match.home_team)} vs ${displayTeamName(match.away_team)}`;
}

function renderKnockoutGraphic(matchById) {
  const knockoutById = Object.fromEntries(knockout.map((slot) => [slot.match_id, slot]));
  const boxes = [];
  const connectors = [];
  const boxWidth = 188;
  const boxHeight = 38;
  const columns = {
    r32: 26,
    r16: 258,
    qf: 490,
    sf: 722,
    final: 958,
  };
  const halfTops = [76, 536];
  const r32Gap = 52;
  const finalY = 444;
  const thirdY = 504;

  BRACKET_HALVES.forEach((half, halfIndex) => {
    const top = halfTops[halfIndex];
    const r32Ys = Array.from({ length: 8 }, (_, index) => top + index * r32Gap);
    const r16Ys = pairCenters(r32Ys, boxHeight);
    const qfYs = pairCenters(r16Ys, boxHeight);
    const sfY = pairCenters(qfYs, boxHeight)[0];
    boxes.push(sectionLabel(half.label, 26, top - 34));

    const r32Ids = half.quarterfinals.flatMap((quarter) => quarter.r32);
    r32Ids.forEach((id, index) => boxes.push(matchBox(id, columns.r32, r32Ys[index], knockoutById, matchById, boxWidth, boxHeight, "bracket-r32")));

    const r16Ids = half.quarterfinals.flatMap((quarter) => quarter.r16);
    r16Ids.forEach((id, index) => boxes.push(matchBox(id, columns.r16, r16Ys[index], knockoutById, matchById, boxWidth, boxHeight, "bracket-r16")));

    half.quarterfinals.forEach((quarter, index) => {
      boxes.push(matchBox(quarter.id, columns.qf, qfYs[index], knockoutById, matchById, boxWidth, boxHeight, "bracket-qf"));
    });
    boxes.push(matchBox(half.semifinal, columns.sf, sfY, knockoutById, matchById, boxWidth, boxHeight, "bracket-semi"));

    connectPairs(connectors, columns.r32, r32Ys, columns.r16, r16Ys, boxWidth, boxHeight);
    connectPairs(connectors, columns.r16, r16Ys, columns.qf, qfYs, boxWidth, boxHeight);
    connectPairs(connectors, columns.qf, qfYs, columns.sf, [sfY], boxWidth, boxHeight);
    connectors.push(connector(columns.sf + boxWidth, sfY + boxHeight / 2, columns.final, finalY + boxHeight / 2));
  });

  boxes.push(sectionLabel("决赛", columns.final, finalY - 34));
  boxes.push(matchBox(104, columns.final, finalY, knockoutById, matchById, boxWidth, boxHeight, "bracket-final"));
  boxes.push(matchBox(103, columns.final, thirdY, knockoutById, matchById, boxWidth, boxHeight, "bracket-third"));

  return `
    <section class="knockout-graphic-card" aria-label="淘汰赛晋级图">
      <div class="graphic-head">
        <div>
          <h2>淘汰赛晋级图</h2>
          <p>32强分上下半区，胜者逐轮进入决赛</p>
        </div>
        <span>可横向滑动</span>
      </div>
      <div class="bracket-scroll">
        <svg class="bracket-svg" viewBox="0 0 1168 946" role="img" aria-labelledby="bracketTitle bracketDesc">
          <title id="bracketTitle">2026 世界杯淘汰赛晋级图</title>
          <desc id="bracketDesc">从32强到16强、1/4决赛、半决赛和决赛的上下半区晋级关系</desc>
          <rect width="1168" height="946" rx="18" fill="#fbfcfb"></rect>
          <g class="bracket-connectors">${connectors.join("")}</g>
          <g class="bracket-boxes">${boxes.join("")}</g>
        </svg>
      </div>
    </section>
  `;
}

function sectionLabel(label, x, y) {
  return `<text class="bracket-section-label" x="${x}" y="${y}">${escapeHtml(label)}</text>`;
}

function pairCenters(ys, boxHeight) {
  const centers = [];
  for (let index = 0; index < ys.length; index += 2) {
    centers.push((ys[index] + boxHeight / 2 + ys[index + 1] + boxHeight / 2) / 2 - boxHeight / 2);
  }
  return centers;
}

function connectPairs(connectors, fromX, fromYs, toX, toYs, boxWidth, boxHeight) {
  toYs.forEach((targetY, index) => {
    connectors.push(connector(fromX + boxWidth, fromYs[index * 2] + boxHeight / 2, toX, targetY + boxHeight / 2));
    connectors.push(connector(fromX + boxWidth, fromYs[index * 2 + 1] + boxHeight / 2, toX, targetY + boxHeight / 2));
  });
}

function connector(x1, y1, x2, y2) {
  const midX = x1 + (x2 - x1) / 2;
  return `<path d="M ${x1} ${y1} H ${midX} V ${y2} H ${x2}" fill="none"></path>`;
}

function matchBox(matchId, x, y, knockoutById, matchById, width, height, extraClass) {
  const slot = knockoutById[matchId] || {};
  const match = matchById[matchId] || {};
  const label = bracketMatchLabel(slot, match, matchId);
  const title = `${label.id} ${label.detail}`;
  return `
    <g class="bracket-box ${extraClass}" tabindex="0">
      <title>${escapeHtml(title)}</title>
      <rect x="${x}" y="${y}" width="${width}" height="${height}" rx="7"></rect>
      <text x="${x + 10}" y="${y + 15}" class="bracket-id">${escapeHtml(label.id)}</text>
      <text x="${x + 10}" y="${y + 30}" class="bracket-team">${escapeHtml(label.detail)}</text>
    </g>
  `;
}

function bracketMatchLabel(slot, match, matchId) {
  const home = displayTeamName(shortBracketTeam(slot.home_team || match.home_team || slot.home_source || ""));
  const away = displayTeamName(shortBracketTeam(slot.away_team || match.away_team || slot.away_source || ""));
  return {
    id: `#${matchId}`,
    detail: truncateText(`${home} vs ${away}`, 22),
  };
}

function shortBracketTeam(value) {
  const text = String(value || "").replace(/^待定：/, "").replace(/之一$/, "").trim();
  const winnerMatch = text.match(/^Winner Match (\d+)$/i);
  if (winnerMatch) return `#${winnerMatch[1]}胜者`;
  const loserMatch = text.match(/^Loser Match (\d+)$/i);
  if (loserMatch) return `#${loserMatch[1]}负者`;
  const winnerGroup = text.match(/^Winner Group ([A-L])$/i);
  if (winnerGroup) return `${winnerGroup[1].toUpperCase()}组第一`;
  const runnerGroup = text.match(/^Runner-up Group ([A-L])$/i);
  if (runnerGroup) return `${runnerGroup[1].toUpperCase()}组第二`;
  const thirdGroup = text.match(/^(3rd|Third)(?: place)? Group ([A-L](?:\/[A-L])*)$/i);
  if (thirdGroup) return `${thirdGroup[2].toUpperCase()}组第三`;
  return text;
}

function truncateText(value, maxLength) {
  const text = String(value || "");
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function timeRows(match) {
  return [
    ["beijing", "北京时间"],
    ["eastern", "美国东部"],
    ["western", "美国西部"],
  ]
    .map(([key, label]) => {
      const value = formatInZone(match.kickoff, TIME_ZONES[key].zone);
      const early = key === "beijing" && isEarlyMorning(match.kickoff, TIME_ZONES.beijing.zone);
      return `<div class="time-row ${key === "beijing" ? "primary" : ""}"><div class="time-label">${label}</div><div class="time-value">${escapeHtml(value)}${early ? '<span class="beijing-early">凌晨</span>' : ""}</div></div>`;
    })
    .join("");
}

function slotNote(match) {
  if (!match || match.stage === "Group Stage") return "";
  if (match.home_slot_resolved && match.away_slot_resolved) return "";
  return `<div class="slot-note">${escapeHtml(match.home_slot_label)} vs ${escapeHtml(match.away_slot_label)}</div>`;
}

function stageClass(match) {
  if (!match) return "knockout";
  if (match.stage_label === "决赛") return "final";
  if (match.stage === "Group Stage") return "group";
  return "knockout";
}

function statusClass(match) {
  if (!match) return "";
  if (match.is_live || ["live", "halftime", "extra_time", "penalties"].includes(match.status)) return "live";
  if (match.is_finished || match.status === "finished") return "finished";
  if (["postponed", "cancelled"].includes(match.status)) return match.status;
  return "";
}

function favoriteMatches() {
  return matches.filter((match) => favoriteIds.has(match.matchId)).sort((a, b) => a.kickoff - b.kickoff);
}

function showStatus(message) {
  statusEl.hidden = false;
  statusEl.textContent = message;
}

function hideStatus() {
  statusEl.hidden = true;
  statusEl.textContent = "";
}

function getParts(date, timeZone) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  })
    .formatToParts(date)
    .reduce((parts, item) => {
      if (item.type !== "literal") parts[item.type] = item.value;
      return parts;
    }, {});
}

function formatInZone(date, timeZone) {
  const parts = getParts(date, timeZone);
  return `${parts.year}-${parts.month}-${parts.day} ${parts.weekday} ${parts.hour}:${parts.minute}`;
}

function dateKey(date, timeZone) {
  const parts = getParts(date, timeZone);
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function isEarlyMorning(date, timeZone) {
  return Number(getParts(date, timeZone).hour) < 6;
}

function exportFavoritesIcs() {
  const selected = favoriteMatches();
  if (!selected.length) {
    alert("还没有关注的比赛");
    return;
  }
  downloadFile("worldcup_favorites.ics", buildIcs(selected), "text/calendar;charset=utf-8");
}

function exportFavoritesCsv() {
  const selected = favoriteMatches();
  if (!selected.length) {
    alert("还没有关注的比赛");
    return;
  }
  const headers = ["match_id", "stage", "home_team", "away_team", "status", "minute", "score", "beijing_time", "eastern_time", "western_time", "city", "stadium", "notes"];
  const rows = selected.map((match) => [match.matchId, match.stage_label, displayTeamName(match.home_team), displayTeamName(match.away_team), match.status_label, match.minute, match.score, formatInZone(match.kickoff, TIME_ZONES.beijing.zone), formatInZone(match.kickoff, TIME_ZONES.eastern.zone), formatInZone(match.kickoff, TIME_ZONES.western.zone), match.city, match.stadium, match.notes]);
  downloadFile("worldcup_favorites.csv", [headers, ...rows].map((row) => row.map(csvEscape).join(",")).join("\n"), "text/csv;charset=utf-8");
}

function buildIcs(selected) {
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//World Cup Schedule PWA//Dynamic Favorites//CN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:世界杯重点比赛"];
  const stamp = formatIcsDate(new Date());
  selected.forEach((match) => {
    const end = new Date(match.kickoff.getTime() + 2 * 60 * 60 * 1000);
    const title = matchTitle(match);
    const description = [`比赛阶段: ${match.stage_label}`, `比赛状态: ${statusText(match)}`, `比分: ${match.score || ""}`, `北京时间: ${formatInZone(match.kickoff, TIME_ZONES.beijing.zone)}`, `美国东部时间: ${formatInZone(match.kickoff, TIME_ZONES.eastern.zone)}`, `美国西部时间: ${formatInZone(match.kickoff, TIME_ZONES.western.zone)}`, `城市 / 球场: ${match.city} / ${match.stadium}`, `备注: ${match.notes || ""}`].join("\n");
    lines.push("BEGIN:VEVENT", `UID:worldcup-2026-match-${match.matchId}@pwa`, `DTSTAMP:${stamp}`, `DTSTART:${formatIcsDate(match.kickoff)}`, `DTEND:${formatIcsDate(end)}`, `SUMMARY:${icsEscape(`世界杯：${title}`)}`, `LOCATION:${icsEscape(`${match.city}, ${match.stadium}`)}`, `DESCRIPTION:${icsEscape(description)}`, "BEGIN:VALARM", "TRIGGER:-PT2H", "ACTION:DISPLAY", `DESCRIPTION:${icsEscape(`世界杯 2 小时后开赛：${title}`)}`, "END:VALARM", "BEGIN:VALARM", "TRIGGER:-PT30M", "ACTION:DISPLAY", `DESCRIPTION:${icsEscape(`世界杯 30 分钟后开赛：${title}`)}`, "END:VALARM", "END:VEVENT");
  });
  lines.push("END:VCALENDAR");
  return lines.flatMap(foldIcsLine).join("\r\n") + "\r\n";
}

function formatIcsDate(date) {
  return date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}

function icsEscape(value) {
  return String(value).replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\n/g, "\\n");
}

function foldIcsLine(line) {
  const encoder = new TextEncoder();
  if (encoder.encode(line).length <= 75) return [line];
  const folded = [];
  let current = "";
  for (const char of line) {
    const limit = folded.length ? 74 : 75;
    if (encoder.encode(current + char).length > limit) {
      folded.push(folded.length ? ` ${current}` : current);
      current = char;
    } else {
      current += char;
    }
  }
  if (current) folded.push(folded.length ? ` ${current}` : current);
  return folded;
}

function csvEscape(value) {
  const text = String(value ?? "");
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadFile(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function groupBy(items, keyFn) {
  return items.reduce((groups, item) => {
    const key = keyFn(item);
    groups[key] ||= [];
    groups[key].push(item);
    return groups;
  }, {});
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
