# Claude Code /goal 执行指令：JetPhotos New Tab 扩展

> **使用方式**：在 Claude Code 终端中执行 `/goal` 后，将本文档的对应 Phase 内容粘贴作为目标描述。
> 按 Phase 顺序执行，每个 Phase 完成验证后再进入下一个。

---

## 全局上下文

你正在开发一款 Chrome 浏览器扩展「Aviation Gallery — New Tab」。

架构对标 Google Earth View：扩展本体只内置一个 `photoIds[]` 数组（极轻量），元数据 JSON 文件托管在 GitHub Pages，图片运行时从 JetPhotos CDN 加载。三层完全解耦。

```
Extension (photo-ids.js)
    → fetch GitHub Pages (photos/{id}.json)
        → load image from JetPhotos CDN
```

项目根目录：`~/jetphotos-newtab/`，包含两个子项目：

```
~/jetphotos-newtab/
├── extension/          # Chrome 扩展源码
├── data-builder/       # Python build 脚本 + 输出的 JSON 数据
└── README.md
```

---

## Phase 0：可行性验证（先跑这个，决定后续能不能做）

### /goal 指令

```
目标：验证 JetPhotos New Tab 扩展的两个核心可行性假设。

## 假设 1：JetPhotos CDN 图片能在 Chrome 扩展的 newtab 页面中加载

操作：
1. 在 ~/jetphotos-newtab/extension/ 下创建一个最小化 Manifest V3 扩展：
   - manifest.json（chrome_url_overrides.newtab 指向 test.html）
   - test.html 页面中嵌入 5 张 JetPhotos CDN 图片，覆盖三种尺寸：
     - https://cdn.jetphotos.com/full/... (2-3 张)
     - https://cdn.jetphotos.com/400/... (1-2 张)
     - https://cdn.jetphotos.com/200/... (1 张)
   - 每张图下方用 <p> 标注尺寸和 URL，方便肉眼确认加载状态
2. 在 test.html 中加入一段 JS，监听每张图片的 load/error 事件，
   在页面底部输出加载结果表格（URL | 尺寸 | 状态 | 耗时ms）
3. 输出加载扩展的操作说明（chrome://extensions → 开发者模式 → 加载已解压扩展）

获取测试图片 URL 的方法：
- 用 curl 请求 https://www.jetphotos.com/photo/11354279（或任意热门照片页面）
- 从 HTML 中提取 cdn.jetphotos.com 的图片 URL
- 如果直接 curl JetPhotos 页面不可行，就硬编码几个已知的 CDN URL 格式进行测试
- 同时测试带和不带 Referer 头的情况

## 假设 2：JetPhotos 照片页面的 HTML 结构可解析

操作：
1. 用 curl 请求 3 个 JetPhotos 照片页面 URL：
   - https://www.jetphotos.com/photo/11354279
   - https://www.jetphotos.com/photo/11340000
   - https://www.jetphotos.com/photo/11300000
2. 将返回的 HTML 保存到 ~/jetphotos-newtab/data-builder/samples/ 目录
3. 分析 HTML 结构，找到以下字段的提取方式（CSS selector 或正则）：
   - 飞机机型（aircraft type）
   - 航空公司（airline）
   - 注册号（registration）
   - 摄影师姓名（photographer name）
   - CDN 图片 URL（full 尺寸）
   - 拍摄机场/地点（location）
4. 将分析结果写入 ~/jetphotos-newtab/data-builder/PARSING_GUIDE.md，格式：
   ```
   ## 字段提取规则
   ### aircraft_type
   - Selector: ...
   - 示例值: "Boeing 747-8"
   ### airline
   - Selector: ...
   ```

## 输出物
- ~/jetphotos-newtab/extension/manifest.json（最小测试扩展）
- ~/jetphotos-newtab/extension/test.html（CDN 加载测试页）
- ~/jetphotos-newtab/data-builder/samples/（3 个 HTML 样本）
- ~/jetphotos-newtab/data-builder/PARSING_GUIDE.md（解析规则文档）
- ~/jetphotos-newtab/PHASE0_RESULT.md（验证结论汇总）

## 验证标准
- 至少有一种 CDN 尺寸（full/400/200）可以在扩展 newtab 中加载
- 至少能从 HTML 中提取出 aircraft_type、photographer、image_url 三个核心字段
- PHASE0_RESULT.md 中明确写出：可行 / 不可行 / 需要调整策略
```

### 人工验证检查点

Phase 0 完成后，你需要手动做以下事情：

1. 在 Chrome 中加载测试扩展，打开新标签页，肉眼确认图片是否显示
2. 阅读 PHASE0_RESULT.md 的结论
3. 如果 CDN full 尺寸被拦截，确认 400 或 200 是否可用
4. 确认 PARSING_GUIDE.md 中的提取规则是否准确

> ⚠️ 只有 Phase 0 验证通过后，才继续 Phase 1。如果不可行，需要调整图片获取策略。

---

## Phase 1：Build 脚本开发

### /goal 指令

```
目标：开发 JetPhotos 数据采集 build 脚本，将人工策展的照片 URL 转换为结构化 JSON 元数据。

## 上下文
参考 ~/jetphotos-newtab/data-builder/PARSING_GUIDE.md 中已验证的 HTML 解析规则。
这是一个一次性 build 工具，不是持续运行的爬虫。

## 实现要求

### 1. 项目结构
```
~/jetphotos-newtab/data-builder/
├── requirements.txt        # requests, beautifulsoup4, lxml
├── curated-urls.txt         # 输入：每行一个 JetPhotos 照片页 URL
├── scraper.py               # 主脚本
├── classifier.py            # 机型自动分类
├── validator.py             # CDN URL 存活验证
├── PARSING_GUIDE.md         # Phase 0 产出的解析规则
├── samples/                 # Phase 0 产出的 HTML 样本
└── output/                  # 生成的 JSON 文件
    ├── index.json
    ├── photos/
    │   ├── {id}.json
    │   └── ...
    └── categories/
        ├── widebody.json
        ├── narrowbody.json
        └── ...
```

### 2. scraper.py 核心逻辑

输入：curated-urls.txt（每行一个 URL，如 https://www.jetphotos.com/photo/11354279）
输出：output/photos/{id}.json

对每个 URL：
a) 提取 photo ID（URL 最后的数字部分）
b) 请求页面 HTML（带 User-Agent，带 Referer: https://www.jetphotos.com/）
c) 按 PARSING_GUIDE.md 的规则解析提取字段
d) 调用 classifier.py 自动分类（widebody/narrowbody/military/cargo/retro/bizjet/special_livery）
e) 调用 validator.py 验证 CDN URL 可访问性（HEAD 请求）
f) 写入 output/photos/{id}.json
g) 每次请求间隔 3-5 秒随机（time.sleep）
h) 控制台打印进度：[15/150] ✓ 11354279 - Boeing 747-8 - Lufthansa

### 3. 单张 JSON 数据结构

```json
{
  "id": "11354279",
  "jetphotos_url": "https://www.jetphotos.com/photo/11354279",
  "image_url": "https://cdn.jetphotos.com/full/...",
  "thumb_url": "https://cdn.jetphotos.com/400/...",
  "fallback_url": "https://cdn.jetphotos.com/200/...",
  "aircraft": {
    "type": "Boeing 747-8",
    "registration": "D-ABYA",
    "airline": "Lufthansa"
  },
  "photographer": {
    "name": "John Doe",
    "profile_url": "https://www.jetphotos.com/photographer/..."
  },
  "location": {
    "airport": "Frankfurt Airport",
    "icao": "EDDF",
    "iata": "FRA",
    "country": "Germany"
  },
  "meta": {
    "category": "widebody",
    "tags": [],
    "cdn_verified": true,
    "scraped_at": "2025-06-01T00:00:00Z"
  }
}
```

### 4. classifier.py 分类规则

```python
CLASSIFICATION_RULES = {
    "widebody": ["747", "777", "787", "A330", "A340", "A350", "A380", "DC-10", "MD-11", "L-1011"],
    "narrowbody": ["737", "A320", "A319", "A321", "A220", "E-Jet", "E170", "E175", "E190", "E195", "CRJ", "717", "757"],
    "military": ["F-22", "F-35", "F/A-18", "F-16", "F-15", "C-17", "C-130", "B-52", "B-2", "Eurofighter", "Rafale", "Su-"],
    "cargo": ["Freighter", "747F", "777F", "767F", "A330F", "Beluga", "Dreamlifter", "AN-124", "AN-225", "Il-76"],
    "retro": ["DC-3", "Concorde", "707", "727", "DC-8", "Caravelle", "Comet", "Tu-144", "VC10"],
    "bizjet": ["Gulfstream", "Global", "Falcon", "Learjet", "Citation", "Challenger", "Phenom", "Hawker"],
    "special_livery": []  # 需要人工标记或通过涂装关键词判断
}
```

根据 aircraft.type 字段匹配，匹配不到的归为 "other"。

### 5. 索引生成

scraper.py 最后自动生成：
- output/index.json：
  ```json
  {
    "version": "1.0.0",
    "updated_at": "...",
    "total": 150,
    "photo_ids": ["11354279", "11354280", ...]
  }
  ```
- output/categories/{category}.json：
  ```json
  {
    "category": "widebody",
    "count": 47,
    "photo_ids": ["11354279", ...]
  }
  ```

### 6. 容错要求

- 单个 URL 抓取失败不中断整体流程，记录到 errors.log
- 支持 --incremental 参数：只处理 output/photos/ 中不存在的 ID
- 支持 --verify-only 参数：只跑 CDN URL 验证，不抓取
- 支持 --dry-run 参数：只解析不写文件，打印结果到终端

### 7. curated-urls.txt 初始内容

先填入 20 个示例 URL 用于测试。在 JetPhotos 上搜索以下机型的高评分照片：
Boeing 747, Airbus A380, Boeing 787, Airbus A350, Concorde（各 4 张）。
格式每行一个 URL。

## 验证标准

运行以下命令验证：
```bash
cd ~/jetphotos-newtab/data-builder
pip install -r requirements.txt
python scraper.py --dry-run  # 先 dry run 确认解析正确
python scraper.py             # 正式运行
ls output/photos/ | wc -l    # 应输出 20（或接近，允许个别失败）
cat output/index.json | python -m json.tool  # JSON 格式正确
cat output/photos/$(ls output/photos/ | head -1) | python -m json.tool  # 单张数据结构正确
python validator.py           # CDN URL 验证通过率 > 80%
```
```

### 人工验证检查点

1. 打开 3-5 个生成的 `photos/{id}.json`，对照 JetPhotos 原页面核实字段准确性
2. 确认 `index.json` 的 photo_ids 数量与 photos/ 目录文件数一致
3. 确认 `categories/` 下的分类是否合理
4. 查看 `errors.log` 是否有需要关注的失败

---

## Phase 2：数据策展（人工操作 + 脚本执行）

### /goal 指令

```
目标：扩充 curated-urls.txt 到 150 条，并运行 build 脚本生成完整数据集。

## 策展指南

在 JetPhotos.com 上按以下分布收集照片页 URL，追加到 curated-urls.txt：

| 类别 | 机型关键词 | 目标数量 | 筛选标准 |
|------|-----------|---------|---------|
| widebody | 747, A380, 787, A350, 777, A330 | 45 | 4星+, 多角度 |
| narrowbody | 737, A320, A321, A220, E190/195 | 25 | 4星+, 多航司 |
| military | F-22, F-35, Blue Angels, Thunderbirds, C-17 | 15 | 高清, 动态感 |
| cargo | 747F, Beluga, AN-124, AN-225 | 12 | 独特涂装 |
| retro | Concorde, DC-3, 707, Tu-144 | 12 | 历史感 |
| bizjet | Gulfstream G700, Global 7500, Falcon 8X | 8 | 优雅构图 |
| special_livery | 星战涂装, 彩绘, 联名, 国旗涂装 | 20 | 视觉冲击 |
| helicopter | AH-64, CH-47, S-92, EC135 | 8 | 动态, 空对空 |
| other | SR-71, U-2, B-2, Solar Impulse | 5 | 稀有机型 |

每个机型确保角度多样性：
- 正侧面：经典 ramp shot
- 起飞/着陆：动态瞬间
- 空对空：空中编队
- 日出/日落：金色光线
- 特殊天气：雨中/雪中/云上

### 操作步骤

1. 我（用户）会手动将 150 个 URL 填入 curated-urls.txt
2. 你运行 build 脚本：
   ```bash
   cd ~/jetphotos-newtab/data-builder
   python scraper.py --incremental
   ```
3. 运行完成后生成统计报告：
   ```bash
   python scraper.py --stats  # 输出各分类数量、CDN 验证通过率
   ```
4. 将 output/ 目录准备好用于 GitHub Pages 部署

## 验证标准

- output/photos/ 下有 140+ 个 JSON 文件（允许 ~10 个失败）
- CDN URL 验证通过率 > 80%
- 每个分类至少有 5 张图片
- index.json 中 photo_ids 数量与实际文件数一致
```

### 人工验证检查点

1. 抽查 10 张不同分类的图片，确认元数据准确
2. 确认 widebody 和 special_livery 这两个"主力分类"的数量达标
3. 记下 CDN 验证失败的条目，评估是否需要替换

---

## Phase 3：Chrome 扩展开发

### /goal 指令

```
目标：开发 Aviation Gallery — New Tab Chrome 扩展，架构对标 Google Earth View。

## 核心架构

扩展本体只含 photoIds 数组。运行时：
随机选 ID → fetch GitHub Pages 上的 {id}.json → 用元数据中的 image_url 加载全屏图。

## 目录结构

```
~/jetphotos-newtab/extension/
├── manifest.json
├── newtab.html
├── newtab.css
├── newtab.js            # 主逻辑（ES module）
├── photo-ids.js         # 核心：export default ["11354279", ...]
├── config.js            # DATA_BASE_URL 等配置
├── cache.js             # chrome.storage.local 缓存管理
├── service-worker.js    # 后台预缓存任务
├── icons/
│   ├── icon-16.png      # 用 canvas 生成一个简单的飞机轮廓图标
│   ├── icon-48.png
│   └── icon-128.png
└── assets/
    └── placeholder.jpg  # 一张深色渐变兜底图，50KB 以内
```

注意：删除 Phase 0 的 test.html，只保留正式文件。

## 1. manifest.json

```json
{
  "manifest_version": 3,
  "name": "Aviation Gallery — New Tab",
  "version": "1.0.0",
  "description": "A stunning aviation photo every time you open a new tab. Powered by JetPhotos.",
  "permissions": ["storage"],
  "chrome_url_overrides": {
    "newtab": "newtab.html"
  },
  "background": {
    "service_worker": "service-worker.js",
    "type": "module"
  },
  "icons": {
    "16": "icons/icon-16.png",
    "48": "icons/icon-48.png",
    "128": "icons/icon-128.png"
  }
}
```

## 2. config.js

```javascript
export default {
  DATA_BASE_URL: "https://YOUR_USERNAME.github.io/jetphotos-data",
  PREFETCH_COUNT: 3,
  HISTORY_SIZE: 30,
  FETCH_TIMEOUT_MS: 3000,
  IMAGE_TIMEOUT_MS: 8000,
  CACHE_MAX_ITEMS: 5,
  CACHE_TTL_MS: 24 * 60 * 60 * 1000,  // 24h
};
```

## 3. photo-ids.js

从 Phase 2 生成的 index.json 中提取 photo_ids 数组：

```javascript
export default [
  // 从 ~/jetphotos-newtab/data-builder/output/index.json 的 photo_ids 字段复制
  "11354279",
  "11354280",
  // ...
];
```

编写一个小脚本 ~/jetphotos-newtab/scripts/sync-photo-ids.sh：
```bash
#!/bin/bash
# 从 data-builder 的 index.json 生成 extension 的 photo-ids.js
cd "$(dirname "$0")/.."
IDS=$(cat data-builder/output/index.json | python3 -c "
import sys, json
ids = json.load(sys.stdin)['photo_ids']
print('export default ' + json.dumps(ids, indent=2) + ';')
")
echo "$IDS" > extension/photo-ids.js
echo "Synced $(cat data-builder/output/index.json | python3 -c 'import sys,json; print(len(json.load(sys.stdin)["photo_ids"]))')" photo IDs
```

## 4. newtab.html

简洁的 HTML 骨架：
- 一个全屏 div#photo-container（背景图）
- 一个 div#info-bar（底部半透明信息浮层）
- 一个 button#refresh-btn（换一张按钮，右下角）
- 一个 div#loading-indicator（加载指示器，优雅的脉冲动画）
- 引入 newtab.css 和 newtab.js（type="module"）

不要使用任何 CDN 引入的外部资源，全部自包含。

## 5. newtab.css 设计规范

整体风格：深色沉浸式，让照片本身成为主角。

```
- 背景色：#0a0a0a（深黑）
- 全屏图片：background-size: cover; background-position: center;
- 信息浮层：底部固定，背景 rgba(0,0,0,0.6) + backdrop-filter: blur(12px)
- 文字颜色：rgba(255,255,255,0.9)
- 次要文字：rgba(255,255,255,0.6)
- 字体：system-ui, -apple-system, sans-serif（不引入外部字体）
- 过渡动画：opacity 0.6s ease-in-out（图片 crossfade）
- 「换一张」按钮：右下角，半透明圆形，hover 时高亮
- 信息浮层自动在 3 秒后半隐藏（opacity 降到 0.3），hover 时恢复
- placeholder 状态：显示一个微弱的飞机轮廓 + 脉冲加载动画
```

## 6. newtab.js 核心逻辑

严格对标 Google Earth View 的运行时流程：

```
init()
├── showPlaceholder()                        // 立即显示兜底图
├── tryLoadFromCache()                       // 检查 chrome.storage 预缓存
│   ├── 有缓存 → renderPhoto(cached)         // < 100ms
│   └── 无缓存 → onlineFlow()
│       ├── pickRandomId(PHOTO_IDS, history) // 随机选取（排除历史）
│       ├── fetchMetadata(id)                // fetch {DATA_BASE_URL}/photos/{id}.json
│       │   ├── 成功 → loadImage(metadata.image_url)
│       │   │          ├── full 加载成功 → renderPhoto()
│       │   │          ├── full 失败 → 尝试 thumb_url
│       │   │          └── 全部失败 → showFallback()
│       │   └── 失败 → showFallback()
│       └── renderPhoto(metadata)            // crossfade + 信息浮层
└── prefetchNext(PREFETCH_COUNT)             // 后台静默预缓存
```

关键函数签名：

```javascript
// 随机选取，排除最近 HISTORY_SIZE 张
async function pickRandomId(): Promise<string>

// fetch 元数据 JSON，带超时
async function fetchMetadata(photoId: string): Promise<PhotoMetadata | null>

// 加载图片，带多尺寸降级
async function loadImage(metadata: PhotoMetadata): Promise<string>  // 返回成功加载的 URL

// 渲染：设置背景图 + 更新信息浮层 + crossfade 动画
function renderPhoto(metadata: PhotoMetadata, imageUrl: string): void

// 更新信息浮层内容
function updateInfoBar(metadata: PhotoMetadata): void

// 预缓存：后台加载 N 张的元数据 + 缩略图
async function prefetchNext(count: number): Promise<void>

// 展示历史管理（chrome.storage.local）
async function getHistory(): Promise<string[]>
async function addToHistory(id: string): Promise<void>
```

## 7. cache.js 缓存管理

```javascript
// 缓存数据结构
interface CacheEntry {
  metadata: PhotoMetadata;
  imageDataUrl: string;  // base64 data URL
  cachedAt: number;      // timestamp
}

// API
export async function getCached(): Promise<CacheEntry | null>
export async function setCached(entries: CacheEntry[]): Promise<void>
export async function clearExpired(): Promise<void>
```

chrome.storage.local 配额 10MB，每张缩略图（400px）约 50-100KB，
存 5 张缓存约 500KB，完全在配额内。

## 8. service-worker.js

Manifest V3 的 Service Worker，负责：
- 监听 chrome.runtime.onInstalled：首次安装时触发一次预缓存
- 监听 chrome.alarms：每 4 小时刷新一次预缓存
- 不做其他事情，保持极简

## 9. 信息浮层 HTML 结构

```html
<div id="info-bar">
  <div class="info-main">
    <span class="icon">✈</span>
    <span id="aircraft-type">Boeing 747-8</span>
    <span class="separator">·</span>
    <span id="airline">Lufthansa</span>
    <span class="separator">·</span>
    <span id="registration">D-ABYA</span>
  </div>
  <div class="info-secondary">
    <span class="icon">📷</span>
    <span id="photographer">John Doe</span>
    <span class="separator">·</span>
    <span id="location">Frankfurt Airport</span>
  </div>
  <div class="info-actions">
    <span class="powered-by">Powered by JetPhotos</span>
    <a id="view-original" href="#" target="_blank" rel="noopener">
      查看原图 ↗
    </a>
  </div>
</div>
```

## 10. 键盘快捷键

| 按键 | 行为 |
|------|------|
| Space | 换一张 |
| → (Right Arrow) | 换一张 |
| ← (Left Arrow) | 上一张（从本地历史读取） |
| F | 收藏当前图片（存入 chrome.storage） |
| I | 展开/收起信息浮层 |
| Escape | 收起信息浮层 |

## 11. 图标生成

用 HTML Canvas 生成简单的飞机剪影图标（16/48/128px），保存为 PNG。
风格：深色背景 + 白色飞机轮廓，圆角正方形。
不需要复杂设计，简洁可辨识即可。

## 验证标准

完成后运行以下检查：

1. 目录结构检查：
   ```bash
   ls -la ~/jetphotos-newtab/extension/
   # 应包含：manifest.json, newtab.html, newtab.css, newtab.js,
   #          photo-ids.js, config.js, cache.js, service-worker.js,
   #          icons/, assets/
   ```

2. manifest.json 合法性：
   ```bash
   cat ~/jetphotos-newtab/extension/manifest.json | python3 -m json.tool
   # 无报错，manifest_version 为 3
   ```

3. photo-ids.js 非空：
   ```bash
   grep -c '"' ~/jetphotos-newtab/extension/photo-ids.js
   # 应 > 20（至少有 20 个 photoId）
   ```

4. 无外部 CDN 依赖：
   ```bash
   grep -r "cdnjs\|unpkg\|jsdelivr\|googleapis.com/ajax" ~/jetphotos-newtab/extension/
   # 应无输出
   ```

5. 所有 JS 文件语法检查：
   ```bash
   for f in ~/jetphotos-newtab/extension/*.js; do
     node --check "$f" 2>&1 && echo "✓ $f" || echo "✗ $f"
   done
   ```
```

### 人工验证检查点

1. 在 Chrome 中加载扩展，打开新标签页
2. 确认图片是否加载成功（可能需要将 config.js 的 DATA_BASE_URL 临时指向本地文件）
3. 测试「换一张」按钮和键盘快捷键
4. 打开 DevTools Console 确认无报错
5. 测试 crossfade 动画是否流畅
6. 确认信息浮层的字段显示正确
7. 测试网络断开时的 fallback 表现

---

## Phase 4：本地集成测试

### /goal 指令

```
目标：将 data-builder 的输出数据与 Chrome 扩展进行本地集成测试，不依赖 GitHub Pages。

## 操作

### 1. 本地数据服务器

创建 ~/jetphotos-newtab/scripts/serve-data.sh：
```bash
#!/bin/bash
# 用 Python 的 HTTP server 在本地 8080 端口提供 JSON 数据
cd "$(dirname "$0")/../data-builder/output"
echo "Serving data at http://localhost:8080"
echo "CORS enabled for Chrome extension testing"
python3 -c "
from http.server import HTTPServer, SimpleHTTPRequestHandler

class CORSHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

HTTPServer(('localhost', 8080), CORSHandler).serve_forever()
"
```

### 2. 指向本地的 config

创建 ~/jetphotos-newtab/extension/config.dev.js：
```javascript
export default {
  DATA_BASE_URL: "http://localhost:8080",
  PREFETCH_COUNT: 2,
  HISTORY_SIZE: 5,   // 小值，方便测试重复逻辑
  FETCH_TIMEOUT_MS: 3000,
  IMAGE_TIMEOUT_MS: 8000,
  CACHE_MAX_ITEMS: 3,
  CACHE_TTL_MS: 60 * 1000,  // 1 分钟，方便测试缓存过期
};
```

并修改 newtab.js 的 import，使开发时指向 config.dev.js。
添加注释说明发布前需要改回 config.js。

### 3. 自动化测试脚本

创建 ~/jetphotos-newtab/scripts/test-integration.sh：
```bash
#!/bin/bash
set -e
echo "=== JetPhotos New Tab 集成测试 ==="

# 1. 检查数据文件存在
echo "[1/6] 检查数据文件..."
DATA_DIR="$(dirname "$0")/../data-builder/output"
test -f "$DATA_DIR/index.json" || { echo "FAIL: index.json 不存在"; exit 1; }
PHOTO_COUNT=$(ls "$DATA_DIR/photos/" | wc -l)
echo "  photos 数量: $PHOTO_COUNT"
test "$PHOTO_COUNT" -ge 10 || { echo "FAIL: photos 数量 < 10"; exit 1; }

# 2. 检查 JSON 格式
echo "[2/6] 验证 JSON 格式..."
python3 -m json.tool "$DATA_DIR/index.json" > /dev/null
for f in $(ls "$DATA_DIR/photos/" | head -5); do
  python3 -m json.tool "$DATA_DIR/photos/$f" > /dev/null
done
echo "  JSON 格式验证通过"

# 3. 检查 photo-ids.js 与 index.json 一致
echo "[3/6] 检查 ID 同步..."
EXT_DIR="$(dirname "$0")/../extension"
EXT_IDS=$(grep -o '"[0-9]*"' "$EXT_DIR/photo-ids.js" | wc -l)
INDEX_IDS=$(python3 -c "import json; print(len(json.load(open('$DATA_DIR/index.json'))['photo_ids']))")
echo "  extension photo-ids.js: $EXT_IDS IDs"
echo "  data index.json: $INDEX_IDS IDs"

# 4. 检查扩展文件完整性
echo "[4/6] 检查扩展文件..."
for f in manifest.json newtab.html newtab.css newtab.js photo-ids.js config.js cache.js service-worker.js; do
  test -f "$EXT_DIR/$f" || { echo "FAIL: $f 不存在"; exit 1; }
done
echo "  扩展文件完整"

# 5. manifest.json 验证
echo "[5/6] 验证 manifest.json..."
python3 -c "
import json
m = json.load(open('$EXT_DIR/manifest.json'))
assert m['manifest_version'] == 3, 'manifest_version != 3'
assert 'newtab' in m.get('chrome_url_overrides', {}), '缺少 newtab override'
assert 'storage' in m.get('permissions', []), '缺少 storage 权限'
print('  manifest.json 验证通过')
"

# 6. 模拟 fetch 元数据
echo "[6/6] 模拟数据加载..."
FIRST_ID=$(python3 -c "import json; print(json.load(open('$DATA_DIR/index.json'))['photo_ids'][0])")
python3 -c "
import json
data = json.load(open('$DATA_DIR/photos/$FIRST_ID.json'))
assert 'id' in data, '缺少 id 字段'
assert 'image_url' in data, '缺少 image_url 字段'
assert 'aircraft' in data, '缺少 aircraft 字段'
assert 'photographer' in data, '缺少 photographer 字段'
print(f'  测试图片: {data[\"aircraft\"][\"type\"]} - {data[\"aircraft\"].get(\"airline\", \"N/A\")}')
print(f'  CDN URL: {data[\"image_url\"][:60]}...')
"

echo ""
echo "=== 全部通过 ✓ ==="
echo ""
echo "下一步："
echo "  1. 运行 scripts/serve-data.sh 启动本地数据服务"
echo "  2. 在 Chrome 中加载 extension/ 目录"
echo "  3. 打开新标签页验证效果"
```

## 验证标准

```bash
cd ~/jetphotos-newtab
bash scripts/test-integration.sh  # 全部 ✓
bash scripts/serve-data.sh &      # 后台启动数据服务
curl -s http://localhost:8080/index.json | python3 -m json.tool  # JSON 可访问
curl -s http://localhost:8080/photos/$(curl -s http://localhost:8080/index.json | python3 -c "import sys,json; print(json.load(sys.stdin)['photo_ids'][0])").json | python3 -m json.tool  # 单张数据可访问
```
```

### 人工验证检查点

1. 启动本地数据服务，在 Chrome 中加载扩展
2. 打开 5-10 个新标签页，确认：
   - 每次显示不同图片
   - 信息浮层数据与图片匹配
   - crossfade 动画流畅
   - 「换一张」按钮工作正常
3. 断开网络，再开新标签页，确认预缓存生效
4. 打开 DevTools → Application → Storage，确认 chrome.storage 中有缓存数据

---

## Phase 5：部署 + 发布准备

### /goal 指令

```
目标：将数据部署到 GitHub Pages，更新扩展配置指向线上地址，并准备发布。

## 1. GitHub Pages 数据仓库

创建 ~/jetphotos-newtab/scripts/deploy-data.sh：
```bash
#!/bin/bash
# 将 data-builder/output 部署到 GitHub Pages
set -e

DATA_DIR="$(dirname "$0")/../data-builder/output"
DEPLOY_DIR="$(dirname "$0")/../data-builder/gh-pages"

# 准备部署目录
rm -rf "$DEPLOY_DIR"
mkdir -p "$DEPLOY_DIR"

# 复制数据
cp -r "$DATA_DIR/index.json" "$DEPLOY_DIR/"
cp -r "$DATA_DIR/photos" "$DEPLOY_DIR/"
cp -r "$DATA_DIR/categories" "$DEPLOY_DIR/"

# 添加 CORS 头（GitHub Pages 默认支持 CORS，但加个 _headers 以防万一）
cat > "$DEPLOY_DIR/_headers" << 'EOF'
/*
  Access-Control-Allow-Origin: *
  Cache-Control: public, max-age=3600
EOF

# 添加 .nojekyll 文件（避免 GitHub Pages 忽略下划线开头的文件）
touch "$DEPLOY_DIR/.nojekyll"

echo "部署目录准备完成: $DEPLOY_DIR"
echo ""
echo "下一步手动操作："
echo "  1. 在 GitHub 创建仓库 jetphotos-data"
echo "  2. cd $DEPLOY_DIR"
echo "  3. git init && git add . && git commit -m 'Initial data deploy'"
echo "  4. git remote add origin https://github.com/YOUR_USERNAME/jetphotos-data.git"
echo "  5. git push -u origin main"
echo "  6. 在仓库 Settings → Pages → Source 选择 main branch"
echo "  7. 等待部署完成，验证 https://YOUR_USERNAME.github.io/jetphotos-data/index.json"
```

## 2. 更新扩展 config.js

将 DATA_BASE_URL 从 localhost 切换到 GitHub Pages 线上地址。
确保 newtab.js 的 import 从 config.dev.js 改回 config.js。

## 3. 打包扩展

创建 ~/jetphotos-newtab/scripts/package.sh：
```bash
#!/bin/bash
set -e

EXT_DIR="$(dirname "$0")/../extension"
BUILD_DIR="$(dirname "$0")/../build"
VERSION=$(python3 -c "import json; print(json.load(open('$EXT_DIR/manifest.json'))['version'])")

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# 复制文件（排除 dev 配置）
cp "$EXT_DIR/manifest.json" "$BUILD_DIR/"
cp "$EXT_DIR/newtab.html" "$BUILD_DIR/"
cp "$EXT_DIR/newtab.css" "$BUILD_DIR/"
cp "$EXT_DIR/newtab.js" "$BUILD_DIR/"
cp "$EXT_DIR/photo-ids.js" "$BUILD_DIR/"
cp "$EXT_DIR/config.js" "$BUILD_DIR/"
cp "$EXT_DIR/cache.js" "$BUILD_DIR/"
cp "$EXT_DIR/service-worker.js" "$BUILD_DIR/"
cp -r "$EXT_DIR/icons" "$BUILD_DIR/"
cp -r "$EXT_DIR/assets" "$BUILD_DIR/"

# 不复制 config.dev.js 和 test.html 等开发文件

# 打包 zip
cd "$BUILD_DIR"
zip -r "../aviation-gallery-newtab-v${VERSION}.zip" .

echo "打包完成: aviation-gallery-newtab-v${VERSION}.zip"
echo "大小: $(du -sh "../aviation-gallery-newtab-v${VERSION}.zip" | cut -f1)"
```

## 4. README.md

在 ~/jetphotos-newtab/README.md 写入项目说明：
- 项目简介
- 架构说明（三层解耦，对标 Earth View）
- 本地开发指南
- 数据更新流程
- 版权声明

## 验证标准

```bash
# 打包大小 < 100KB
du -sh ~/jetphotos-newtab/aviation-gallery-newtab-v*.zip

# 打包内容检查
unzip -l ~/jetphotos-newtab/aviation-gallery-newtab-v*.zip

# 不包含开发文件
unzip -l ~/jetphotos-newtab/aviation-gallery-newtab-v*.zip | grep -E "config\.dev|test\.html|samples"
# 应无输出
```
```

### 人工验证检查点

1. 将数据推送到 GitHub Pages，等待部署完成
2. 浏览器访问 `https://YOUR_USERNAME.github.io/jetphotos-data/index.json`，确认可访问
3. 用打包后的 zip 文件重新加载扩展（模拟用户安装），测试完整流程
4. 确认线上数据加载正常，图片显示正常

---

## 执行备忘

### 执行顺序

```
Phase 0 → 人工验证 → Phase 1 → 人工验证 → Phase 2（人工策展 + 脚本）
    → Phase 3 → Phase 4（集成测试）→ 人工验证 → Phase 5（部署）
```

### 每个 Phase 的 /goal 使用方式

```bash
# 在 Claude Code 终端中
/goal

# 然后粘贴对应 Phase 的指令内容（从 "目标：" 开始到 "验证标准" 结束）
# Claude Code 会自动规划并执行
```

### 关键决策点

| 检查点 | 决策 |
|--------|------|
| Phase 0 CDN 测试失败 | 评估降级策略（400/200），或改为 thumbnail + 跳转模式 |
| Phase 0 HTML 解析不可行 | 考虑 Puppeteer 渲染后解析，或改为人工录入元数据 |
| Phase 1 抓取成功率 < 70% | 检查是否被反爬，调整 delay 和 headers |
| Phase 3 CSP 拦截图片 | 调整 manifest.json 的 content_security_policy |
| Phase 4 预缓存不生效 | 检查 Service Worker 注册和 chrome.storage 配额 |

### 回滚策略

如果线上出问题：
1. 扩展内置 fallback —— 即使 GitHub Pages 挂了也能显示 placeholder
2. 数据回滚 —— `git revert` 即可恢复上一版数据
3. 扩展回滚 —— Chrome Web Store 支持版本回退