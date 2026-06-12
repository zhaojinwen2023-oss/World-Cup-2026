# 2026 世界杯动态赛程

这个项目包含两个独立可用版本：

- Excel 分享版：`output/worldcup_2026_schedule.xlsx`
- 手机 PWA 网页 App：`web/index.html`

当前 `data/static_schedule.csv` 已放入公开发布的 2026 世界杯固定赛程，共 104 场。2026 年 6 月 10 日时比赛还没开踢，所以 `data/live_results.json` 默认全部是 `scheduled`，没有真实比分。之后可以通过 API、Google Sheet/CSV 或本地 JSON 更新比分，再重新生成 Excel 和 App 数据。

## 项目结构

```text
worldcup-schedule/
├── README.md
├── data/
│   ├── static_schedule.csv
│   ├── live_results.json
│   ├── standings.json
│   ├── knockout_bracket.json
│   ├── app_data.json
│   └── last_updated.json
├── scripts/
│   ├── build_excel.py
│   ├── build_ics.py
│   ├── build_app_data.py
│   ├── calculate_standings.py
│   ├── resolve_knockout.py
│   ├── update_live_data.py
│   ├── fetch_live_data.py
│   ├── validate_schedule.py
│   ├── import_public_fixtures.py
│   └── providers/
├── web/
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   ├── manifest.json
│   └── service-worker.js
└── output/
    ├── worldcup_2026_schedule.xlsx
    └── worldcup_favorites.ics
```

## 安装

建议 Python 3.11+：

```bash
cd worldcup-schedule
python3 -m venv .venv
source .venv/bin/activate
pip install pandas openpyxl
```

## 一键刷新

本地 JSON 模式：

```bash
python scripts/update_live_data.py --source local
```

这条命令会完成：

- 读取 `data/static_schedule.csv`
- 读取或合并 `data/live_results.json`
- 按比分重新计算 `data/standings.json`
- 解析 `data/knockout_bracket.json`
- 生成 `data/app_data.json`
- 生成 `output/worldcup_2026_schedule.xlsx`
- 生成 `output/worldcup_favorites.ics`
- 写入 `data/last_updated.json`

兼容入口也可以用：

```bash
python scripts/fetch_live_data.py --source local
```

## 数据文件

`data/static_schedule.csv` 保存官方固定赛程：

```csv
match_id,stage,round,group,home_placeholder,away_placeholder,home_team,away_team,stadium,city,country,local_datetime,local_timezone,is_favorite,notes
```

`data/live_results.json` 保存实时比分：

```json
{
  "last_updated": "2026-06-12T05:10:00+08:00",
  "results": [
    {
      "match_id": 1,
      "home_team": "Mexico",
      "away_team": "South Africa",
      "home_score": 2,
      "away_score": 1,
      "home_penalty_score": "",
      "away_penalty_score": "",
      "status": "finished",
      "minute": 90,
      "winner": "Mexico",
      "loser": "South Africa",
      "is_finished": true,
      "last_updated": "2026-06-12T05:10:00+08:00"
    }
  ]
}
```

`status` 可取：

- `scheduled`
- `live`
- `halftime`
- `extra_time`
- `penalties`
- `finished`
- `postponed`
- `cancelled`

`data/standings.json` 保存小组积分榜。默认由 `calculate_standings.py` 根据已结束小组赛比分重新计算。

`data/knockout_bracket.json` 保存淘汰赛对阵。默认由 `resolve_knockout.py` 根据积分榜和上一轮胜者自动解析。

## 手动修正比分

编辑 `data/live_results.json` 中对应 `match_id`：

```json
{
  "match_id": 1,
  "home_score": 2,
  "away_score": 1,
  "status": "finished",
  "minute": 90,
  "winner": "Mexico",
  "last_updated": "2026-06-12T05:10:00+08:00"
}
```

然后运行：

```bash
python scripts/update_live_data.py --source local
```

如果你想手动维护 `standings.json` 或 `knockout_bracket.json`，运行：

```bash
python scripts/update_live_data.py --source local --standings-mode provider --knockout-mode provider
```

默认推荐用 `--standings-mode auto`，让脚本从比赛结果自动计算积分榜。

## 接入 Google Sheet / 在线 CSV

把 Google Sheet 发布为 CSV，然后提供 URL：

```bash
python scripts/update_live_data.py \
  --source google_sheet \
  --live-url "https://docs.google.com/spreadsheets/d/.../pub?gid=0&single=true&output=csv"
```

如果 Google Sheet 里也维护积分榜或淘汰赛，可以加：

```bash
python scripts/update_live_data.py \
  --source google_sheet \
  --live-url "https://..." \
  --standings-url "https://..." \
  --knockout-url "https://..." \
  --standings-mode provider \
  --knockout-mode provider
```

CSV 字段名尽量和 `live_results.json`、`standings.json`、`knockout_bracket.json` 保持一致。

## 接入体育 API

项目预留了 provider：

- `api_football`
- `sportmonks`
- `livescore`
- `worldcupapi`
- `google_sheet`
- `local`

不要把 API key 写进代码。可以写到 `.env`：

```bash
API_FOOTBALL_KEY=你的_key
API_FOOTBALL_WORLD_CUP_LEAGUE_ID=1
API_FOOTBALL_WORLD_CUP_SEASON=2026
API_FOOTBALL_FIXTURES_URL=https://... # 可选：覆盖默认 fixtures endpoint
SPORTMONKS_KEY=你的_key
SPORTMONKS_WORLD_CUP_LEAGUE_ID=732
SPORTMONKS_FIXTURES_URL=https://...   # 可选：覆盖默认 fixtures endpoint
SPORTMONKS_STANDINGS_URL=https://...  # 可选
LIVESCORE_API_KEY=你的_key
WORLDCUP_API_URL=https://...
WORLDCUP_LIVE_URL=https://...
WORLDCUP_STANDINGS_URL=https://...
WORLDCUP_KNOCKOUT_URL=https://...
```

运行示例：

```bash
python scripts/update_live_data.py --source worldcupapi
python scripts/update_live_data.py --source api_football
python scripts/update_live_data.py --source sportmonks
```

API-SPORTS / API-Football provider 默认会请求：

```text
https://v3.football.api-sports.io/fixtures?league=1&season=2026
```

其中 `league=1` 是 API-SPORTS 的 World Cup。provider 会把 API fixtures 按球队名、开球 UTC 时间、球场信息匹配回本项目的 `match_id`，只更新比分、状态、分钟、点球和胜者，不覆盖 `static_schedule.csv`。

注意：API-SPORTS Free 计划目前不能访问 2026 World Cup fixtures/standings，接口会提示只能访问较早赛季。key 有效也不代表套餐包含 2026 数据；需要升级套餐或等 API 放开 2026 赛季。

SportMonks provider 默认会请求：

```text
https://api.sportmonks.com/v3/football/fixtures/between/2026-06-11/2026-07-20
```

并使用 `fixtureLeagues:732` 过滤 World Cup。它会把 SportMonks fixtures 按球队名、开球 UTC 时间、球场信息匹配回本项目的 `match_id`，再生成 `live_results.json`、`standings.json`、`knockout_bracket.json`、`app_data.json`。

注意：SportMonks token 必须包含 Football / World Cup 数据权限。如果返回 “No result(s) found ... or you don't have access”，说明 token 有效但当前订阅还不能访问对应 football/World Cup endpoint。免费 API 不稳定时，仍可用 Google Sheet 或本地 JSON 兜底。

## 自动刷新，不手动维护

项目根目录已提供 GitHub Actions 模板：

```text
.github/workflows/update-worldcup-schedule.yml
```

部署到 GitHub 后：

1. 进入仓库 `Settings` -> `Secrets and variables` -> `Actions`。
2. 新增 Repository secret：

```text
API_FOOTBALL_KEY
SPORTMONKS_KEY
```

3. 在 Repository variables 配置数据源和 league id：

```text
LIVE_DATA_SOURCE=api_football
API_FOOTBALL_WORLD_CUP_LEAGUE_ID=1
API_FOOTBALL_WORLD_CUP_SEASON=2026
SPORTMONKS_WORLD_CUP_LEAGUE_ID=732
```

如果你改用 SportMonks，把 `LIVE_DATA_SOURCE` 设成 `sportmonks`。

4. workflow 会每 15 分钟运行一次，也可以手动点 `Run workflow`。

它会自动：

- 调用配置的数据源
- 刷新 `data/*.json`
- 重新生成 Excel 和 `.ics`
- 校验数据
- 自动提交变更

不要把 `.env` 提交到 GitHub。项目里的 `.gitignore` 已经忽略 `.env`。

## 淘汰赛自动解析

小组赛结束前，淘汰赛会显示占位符：

```text
待定：A组第一 vs 待定：C/E/F/H/I组第三之一
```

当积分榜或比赛结果更新后，运行刷新命令会把占位符替换为真实球队：

```text
Argentina vs Japan
```

后续轮次用上一轮 `winner` 自动填入。点球大战时，脚本优先使用 `winner`；如果没有手写 `winner`，会比较 `home_penalty_score` 和 `away_penalty_score`。

当前积分榜排序已实现：

- 积分
- 净胜球
- 进球数
- 公平竞赛分
- 队名兜底

限制：相互战绩和抽签没有完整实现。真正涉及同分极端情况时，建议人工核对并在 `standings.json` 里修正。

## Excel

生成：

```bash
python scripts/build_excel.py
```

Excel 包含：

- `完整赛程`
- `重点比赛`
- `小组积分榜`
- `最佳小组第三`
- `淘汰赛对阵`
- `比赛结果`
- `使用说明`

Excel 不会真正“实时联网”。它是给查看、截图和分享用的文件；比分变化后，需要重新运行 `python scripts/update_live_data.py --source local` 或对应数据源命令来生成新版。

## 手机 PWA

不要直接用 `file://.../web/index.html` 打开，因为浏览器会限制读取 `data/app_data.json`。请在项目根目录启动本地服务器：

```bash
python3 -m http.server 8000
```

打开：

```text
http://localhost:8000/web/
```

PWA 功能：

- 底部导航：赛程、实时、积分榜、淘汰赛、我的关注
- `赛程` 首页是 2026 年 6-7 月月历，点击有比赛的日期进入当天比赛列表
- 打开页面时加载 `data/app_data.json`
- 每 5 分钟自动刷新一次
- 显示最后更新时间
- 刷新失败时显示“暂时无法获取最新比分，当前显示上次更新数据”
- 收藏比赛保存在浏览器 `localStorage`
- 导出重点比赛 `.ics`
- 导出重点比赛 CSV

在 iPhone / Android 浏览器里打开后，可以用浏览器菜单添加到主屏幕。PWA 名称是“世界杯赛程”。

## 提醒文件

生成：

```bash
python scripts/build_ics.py
```

提醒规则：

- 开赛前 2 小时提醒
- 开赛前 30 分钟提醒

如果收藏的是待定淘汰赛，导出时会使用 `app_data.json` 里的最新队名和最新开球时间。

## 时区

Python 使用 `zoneinfo`，前端使用 `Intl.DateTimeFormat`。项目使用 IANA 时区：

- `Asia/Shanghai`
- `America/New_York`
- `America/Los_Angeles`

没有写死时差，所以能正确处理 2026 年 6-7 月美国夏令时。

## 校验

```bash
python scripts/validate_schedule.py
python -m py_compile scripts/*.py scripts/providers/*.py
node --check web/app.js
```

## 部署到 GitHub Pages

1. 把整个项目提交并推送到 GitHub。
2. 进入仓库 `Settings` -> `Pages`。
3. `Build and deployment` 选择 `Deploy from a branch`。
4. 分支选择 `main`，目录选择 `/ (root)`，然后保存。
5. 等待 GitHub Pages 部署完成后访问：

```text
https://zhaojinwen2023-oss.github.io/World-Cup-2026/
```

仓库根目录的 `index.html` 会自动跳转到：

```text
https://zhaojinwen2023-oss.github.io/World-Cup-2026/worldcup-schedule/web/
```

部署后，更新比分的流程是：先在本地或自动任务里运行 `update_live_data.py`，提交更新后的 `data/app_data.json`、Excel 和相关 JSON，再让 GitHub Pages 发布新版。
