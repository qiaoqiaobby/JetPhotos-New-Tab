# JetPhotos New Tab 浏览器扩展 — 方案 B：Earth View 架构复刻

## 1. 项目概述

### 1.1 产品定义

开发一款 Chrome 浏览器扩展，用户每次打开新标签页时，全屏展示一张来自 JetPhotos.com 的经典飞机摄影作品。架构完全复刻 Google Earth View 的设计模式：扩展只内置 photoId 数组（极轻量），元数据和图片在运行时按需加载。

### 1.2 架构灵感：Google Earth View 怎么做的

Google Earth View 的核心设计极其优雅：

```
扩展本体 (165KB)
  └─ 只包含一个 photoIds 数组: ["1003", "1004", "1006", ...]
  └─ 不打包任何图片，不打包任何元数据

运行时（每次开新 Tab）
  └─ 从 photoIds 中随机选一个 ID
  └─ fetch("https://www.gstatic.com/prettyearth/assets/data/v3/{id}.json")
  └─ 拿到元数据（坐标、地名、图片 URL）
  └─ 用元数据中的 image URL 加载全屏卫星图
```

Google 能这么做，是因为它同时拥有内容和 CDN。我们的 JetPhotos 版本需要适配一个关键差异：**我们不拥有内容**。所以需要自建元数据层。

### 1.3 我们的适配方案

```
Earth View 的做法          →  我们的做法
─────────────────────────────────────────────────────────
扩展内置 photoIds[]        →  扩展内置 photoIds[]（一样）
gstatic.com 托管元数据 JSON →  GitHub Pages 托管元数据 JSON
gstatic.com 托管图片        →  指向 JetPhotos CDN（不代理）
Google 自有版权             →  标注摄影师 + 导流回 JetPhotos
```

### 1.4 这个架构的核心优势

- 扩展本体极小（< 50KB），审核快、安装快
- 元数据与扩展解耦：更新图片库只需 push JSON 到 GitHub，不需要重新发布扩展
- 一次性 build 脚本生成所有数据，后续维护只需 `git push`
- 完全复刻经过 2500+ 图片、60 万用户验证的成熟架构

---

## 2. 系统架构

### 2.1 三层解耦架构

```
┌─ Layer 1: Chrome Extension (< 50KB) ─────────────────┐
│                                                       │
│  manifest.json                                        │
│  newtab.html / .css / .js                             │
│  service-worker.js                                    │
│  config.js  ← DATA_BASE_URL 指向 GitHub Pages         │
│  photo-ids.js  ← 只有一个数组: ["11354279", ...]      │
│  assets/placeholder.jpg  ← 一张兜底图（本地内置）       │
│                                                       │
└───────────────────────┬───────────────────────────────┘
                        │ fetch("{DATA_BASE_URL}/{id}.json")
                        ▼
┌─ Layer 2: GitHub Pages (元数据托管) ─────────────────┐
│                                                       │
│  jetphotos-data/                                      │
│  ├── index.json          ← 全量 photoId 索引(备用)    │
│  ├── photos/                                          │
│  │   ├── 11354279.json   ← 单张图片的完整元数据        │
│  │   ├── 11354280.json                                │
│  │   ├── ...                                          │
│  │   └── 11398765.json                                │
│  └── categories/                                      │
│      ├── widebody.json   ← 分类索引（photoId 列表）    │
│      ├── narrowbody.json                              │
│      └── military.json                                │
│                                                       │
└───────────────────────┬───────────────────────────────┘
                        │ 元数据中的 image_url
                        ▼
┌─ Layer 3: JetPhotos CDN (图片源) ───────────────────┐
│                                                       │
│  cdn.jetphotos.com/full/5/12345_1234567890.jpg        │
│  （扩展直连，不代理，不缓存原图到自有服务器）              │
│                                                       │
└───────────────────────────────────────────────────────┘
```

### 2.2 运行时数据流（复刻 Earth View）

```
用户打开新 Tab
    │
    ▼
[1] 从 photo-ids.js 读取 photoIds 数组
    │
    ▼
[2] 随机选取一个 id（排除最近 30 张历史）
    │
    ▼
[3] 检查 chrome.storage.local 是否有该 id 的预缓存
    │
    ├─ 有缓存 → 直接渲染（< 50ms）
    │
    └─ 无缓存 → fetch("{DATA_BASE_URL}/photos/{id}.json")
                    │
                    ▼
               [4] 拿到元数据：
                   {
                     image_url: "https://cdn.jetphotos.com/full/...",
                     aircraft_type: "Boeing 747-8",
                     photographer: "John Doe",
                     ...
                   }
                    │
                    ▼
               [5] 用 image_url 加载全屏图片
                    │
                    ▼
               [6] 渲染：全屏图 + 底部信息浮层
                    │
                    ▼
               [7] 后台静默预加载下 2 张（fetch 元数据 + 预加载图片）
```

### 2.3 与 Earth View 的逐项对比

| 维度 | Earth View | 我们的实现 |
|------|-----------|-----------|
| 扩展体积 | 165KB | < 50KB |
| photoIds 数量 | ~2500 | 150-200（初期） |
| 元数据托管 | gstatic.com | GitHub Pages |
| 元数据格式 | `{id}.json` | `{id}.json`（一致） |
| 图片托管 | gstatic.com | JetPhotos CDN |
| 更新方式 | Google 内部 | `git push` 到 GitHub |
| 版权模型 | 自有 | 标注归属 + 导流 |
| 数据生成 | 内部工具 | 一次性 build 脚本 |

---

## 3. 数据层设计

### 3.1 单张图片元数据 `photos/{id}.json`

完全对标 Earth View 的 `prettyearth/{id}.json`：

```json
{
  "id": "11354279",
  "jetphotos_url": "https://www.jetphotos.com/photo/11354279",
  "image_url": "https://cdn.jetphotos.com/full/5/12345_1234567890.jpg",
  "thumb_url": "https://cdn.jetphotos.com/400/5/12345_1234567890.jpg",
  "aircraft": {
    "type": "Boeing 747-8",
    "registration": "D-ABYA",
    "airline": "Lufthansa",
    "cn": "37832"
  },
  "photographer": {
    "name": "John Doe",
    "profile_url": "https://www.jetphotos.com/photographer/12345"
  },
  "location": {
    "airport": "Frankfurt Airport",
    "icao": "EDDF",
    "iata": "FRA",
    "country": "Germany"
  },
  "meta": {
    "category": "widebody",
    "tags": ["sunset", "classic", "takeoff"],
    "aspect": "landscape",
    "scraped_at": "2025-06-01T00:00:00Z"
  }
}
```

### 3.2 全量索引 `index.json`

扩展内置的 `photo-ids.js` 是主索引。GitHub Pages 上额外放一份 `index.json` 作为备用，也方便未来实现"热更新 photoIds 而不重发扩展"：

```json
{
  "version": "1.0.0",
  "updated_at": "2025-06-01T00:00:00Z",
  "total": 150,
  "photo_ids": ["11354279", "11354280", "11398765", "..."]
}
```

### 3.3 分类索引 `categories/{category}.json`

```json
{
  "category": "widebody",
  "count": 47,
  "photo_ids": ["11354279", "11354280", "..."]
}
```

支持的分类：

| 分类 key | 说明 | 目标数量 |
|----------|------|---------|
| widebody | 宽体客机 (747, A380, 787, A350, 777) | 40-50 |
| narrowbody | 窄体客机 (737, A320, E-Jet) | 25-30 |
| military | 军用飞机 (F-22, F-35, Blue Angels) | 15-20 |
| cargo | 货运涂装 (747F, AN-124, Beluga) | 10-15 |
| retro | 复古经典 (DC-3, Concorde, 707) | 10-15 |
| bizjet | 公务机 (Gulfstream, Global, Falcon) | 10 |
| special_livery | 特殊涂装 (星战, 彩绘, 联名) | 20-25 |
| helicopter | 直升机 | 5-10 |

### 3.4 GitHub Pages 部署结构

```
github.com/your-username/jetphotos-data/
├── index.json
├── photos/
│   ├── 11354279.json
│   ├── 11354280.json
│   └── ... (150-200 个文件)
├── categories/
│   ├── widebody.json
│   ├── narrowbody.json
│   ├── military.json
│   ├── cargo.json
│   ├── retro.json
│   ├── bizjet.json
│   ├── special_livery.json
│   └── helicopter.json
└── README.md
```

部署为 GitHub Pages 后，每个 JSON 都有稳定 URL：
`https://your-username.github.io/jetphotos-data/photos/11354279.json`

> **为什么用 GitHub Pages 而不是打包进扩展？**
>
> Earth View 用 gstatic.com 托管元数据而不是打包进扩展，原因是更新数据不需要重新发布扩展版本。我们用 GitHub Pages 达到同样效果——push 新 JSON 就行，扩展本体不动。

---

## 4. Build 脚本：一次性数据采集工具

### 4.1 工具定位

这不是"爬虫"，而是一次性的 build 脚本。类似于 Earth View 的数据团队在内部跑一次脚本生成所有 `{id}.json`，我们也跑一次脚本，从人工策展的 JetPhotos 页面提取元数据生成 JSON 文件。

### 4.2 工作流程

```
[人工策展] 收集 150-200 个 JetPhotos photo URL
     │
     ▼
[输入文件] curated-urls.txt
     │  https://www.jetphotos.com/photo/11354279
     │  https://www.jetphotos.com/photo/11354280
     │  ...
     │
     ▼
[Build 脚本] scraper.py（Python + requests + BeautifulSoup）
     │
     │  对每个 URL：
     │  1. 请求页面 HTML
     │  2. 解析提取：机型、航司、注册号、摄影师、CDN 图片 URL
     │  3. 生成 photos/{id}.json
     │  4. 请求间隔 3-5 秒（友好抓取）
     │
     ▼
[输出] photos/ 目录下 150-200 个 JSON 文件
     │
     ▼
[生成索引] index.json + categories/*.json
     │
     ▼
[git push] 推送到 GitHub Pages 仓库
```

### 4.3 脚本核心逻辑（伪代码）

```python
import requests, json, time, random
from bs4 import BeautifulSoup
from pathlib import Path

URLS_FILE = "curated-urls.txt"
OUTPUT_DIR = Path("photos")
DELAY_RANGE = (3, 5)

def scrape_photo(url: str) -> dict:
    """从 JetPhotos 照片页提取元数据"""
    resp = requests.get(url, headers={
        "User-Agent": "Mozilla/5.0 ...",
        "Referer": "https://www.jetphotos.com/"
    })
    soup = BeautifulSoup(resp.text, "html.parser")

    # 提取字段（实际 selector 需在开发时从真实页面确认）
    photo_id = url.split("/photo/")[1]

    return {
        "id": photo_id,
        "jetphotos_url": url,
        "image_url": extract_full_image_url(soup),
        "thumb_url": extract_thumb_url(soup),
        "aircraft": {
            "type": extract_aircraft_type(soup),
            "registration": extract_registration(soup),
            "airline": extract_airline(soup),
        },
        "photographer": {
            "name": extract_photographer(soup),
        },
        "location": {
            "airport": extract_airport(soup),
        },
        "meta": {
            "category": classify_aircraft(aircraft_type),
            "scraped_at": datetime.utcnow().isoformat() + "Z",
        }
    }

def main():
    urls = Path(URLS_FILE).read_text().strip().splitlines()
    OUTPUT_DIR.mkdir(exist_ok=True)

    for url in urls:
        data = scrape_photo(url)
        (OUTPUT_DIR / f"{data['id']}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False)
        )
        time.sleep(random.uniform(*DELAY_RANGE))

    # 生成索引
    generate_index()
    generate_category_indexes()
```

### 4.4 热更新机制

```
需要新增图片时：
1. 在 curated-urls.txt 追加新 URL
2. 运行 scraper.py --incremental（只处理新增的）
3. git push 到 GitHub Pages 仓库
4. 扩展下次 fetch 时自动拿到新数据

需要更新扩展内置的 photoIds 时：
1. 从 index.json 导出最新 ID 列表
2. 更新扩展的 photo-ids.js
3. 发布新版本扩展
```

---

## 5. Chrome 扩展实现

### 5.1 Manifest V3 配置

```json
{
  "manifest_version": 3,
  "name": "Aviation Gallery — New Tab",
  "version": "1.0.0",
  "description": "每次新标签页展示一张经典飞机摄影。Photos courtesy of JetPhotos.com.",
  "permissions": ["storage"],
  "chrome_url_overrides": {
    "newtab": "newtab.html"
  },
  "background": {
    "service_worker": "service-worker.js"
  },
  "icons": {
    "16": "icons/icon-16.png",
    "48": "icons/icon-48.png",
    "128": "icons/icon-128.png"
  },
  "content_security_policy": {
    "extension_pages": "script-src 'self'; object-src 'self'; img-src 'self' https://cdn.jetphotos.com https://*.github.io;"
  }
}
```

### 5.2 目录结构

```
jetphotos-newtab-extension/
├── manifest.json
├── newtab.html
├── newtab.css
├── newtab.js              # 主逻辑：随机选取 → fetch 元数据 → 渲染
├── service-worker.js      # 后台预缓存
├── config.js              # DATA_BASE_URL 配置
├── photo-ids.js           # 核心：photoIds 数组（对标 Earth View）
├── icons/
│   ├── icon-16.png
│   ├── icon-48.png
│   └── icon-128.png
└── assets/
    └── placeholder.jpg    # 本地兜底图（一张内置的飞机摄影，< 50KB）
```

### 5.3 核心文件：photo-ids.js

这是整个扩展最关键的文件，对标 Earth View 的 `onInstall.js` 中的 photoIds 数组：

```javascript
// photo-ids.js
// 策展的 JetPhotos 图片 ID 列表
// 更新方式：从 GitHub Pages 上的 index.json 同步
const PHOTO_IDS = [
  "11354279",
  "11354280",
  "11398765",
  "10987654",
  // ... 150-200 个 ID
];

export default PHOTO_IDS;
```

### 5.4 核心文件：config.js

```javascript
// config.js
const CONFIG = {
  // 元数据托管地址（GitHub Pages）
  DATA_BASE_URL: "https://your-username.github.io/jetphotos-data",

  // 预缓存数量
  PREFETCH_COUNT: 3,

  // 最近展示历史记录数（防重复）
  HISTORY_SIZE: 30,

  // 元数据 fetch 超时（毫秒）
  FETCH_TIMEOUT: 3000,

  // 图片加载超时（毫秒）
  IMAGE_TIMEOUT: 8000,
};

export default CONFIG;
```

### 5.5 核心逻辑：newtab.js

```javascript
import PHOTO_IDS from './photo-ids.js';
import CONFIG from './config.js';

// ── 启动流程（对标 Earth View） ──────────────────────

async function init() {
  // Step 1: 立即显示 placeholder
  showPlaceholder();

  // Step 2: 尝试从预缓存加载
  const cached = await loadFromCache();
  if (cached) {
    renderPhoto(cached.metadata, cached.imageBlob);
    prefetchNext();  // 后台补充预缓存
    return;
  }

  // Step 3: 无缓存，走在线流程（Earth View 标准路径）
  const id = pickRandomId();
  const metadata = await fetchMetadata(id);
  if (metadata) {
    await loadAndRenderImage(metadata);
  } else {
    showFallback();  // 网络不可用时的兜底
  }

  // Step 4: 后台预缓存下几张
  prefetchNext();
}

// ── 随机选取（含防重复） ────────────────────────────

async function pickRandomId() {
  const history = await getHistory();
  const available = PHOTO_IDS.filter(id => !history.includes(id));

  if (available.length === 0) {
    await clearHistory();
    return PHOTO_IDS[Math.floor(Math.random() * PHOTO_IDS.length)];
  }

  const id = available[Math.floor(Math.random() * available.length)];
  await addToHistory(id);
  return id;
}

// ── 元数据加载（对标 Earth View 的 gstatic fetch） ──

async function fetchMetadata(photoId) {
  try {
    const url = `${CONFIG.DATA_BASE_URL}/photos/${photoId}.json`;
    const resp = await fetch(url, {
      signal: AbortSignal.timeout(CONFIG.FETCH_TIMEOUT)
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch (err) {
    console.warn(`元数据加载失败 [${photoId}]:`, err);
    return null;
  }
}

// ── 预缓存机制 ──────────────────────────────────────

async function prefetchNext() {
  const ids = [];
  for (let i = 0; i < CONFIG.PREFETCH_COUNT; i++) {
    ids.push(pickRandomId());
  }

  for (const id of ids) {
    const metadata = await fetchMetadata(id);
    if (!metadata) continue;

    // 预加载图片为 blob
    try {
      const imgResp = await fetch(metadata.thumb_url);  // 先缓存缩略图
      const blob = await imgResp.blob();
      await chrome.storage.local.set({
        [`cache_${id}`]: {
          metadata,
          imageData: await blobToBase64(blob),
          cachedAt: Date.now()
        }
      });
    } catch (err) {
      // 静默失败
    }
  }
}
```

### 5.6 新标签页 UI 设计

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│                                                              │
│                                                              │
│               全屏飞机摄影图片                                  │
│               background-image: cover                        │
│               crossfade 过渡动画                               │
│                                                              │
│                                                              │
│                                                              │
│                                               ┌────────────┐ │
│                                               │  ↻ 换一张   │ │
│                                               └────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  ✈ Boeing 747-8 · Lufthansa · D-ABYA                  │  │
│  │  📷 John Doe · Frankfurt Airport (FRA)                 │  │
│  │  Powered by JetPhotos    [查看原图 ↗]                   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 5.7 交互设计

| 操作 | 行为 |
|------|------|
| 打开新 Tab | 随机展示，placeholder → crossfade 过渡 |
| 点击「换一张」 | 重新随机选取，crossfade 过渡 |
| 点击底部信息区 | 新窗口打开 JetPhotos 原图页面 |
| 点击摄影师名 | 新窗口打开摄影师 JetPhotos 主页 |
| 键盘 `Space` | 换一张 |
| 键盘 `F` | 收藏到本地 |
| 键盘 `I` | 展开/收起信息浮层 |
| 键盘 `←` `→` | 上一张 / 下一张（本地历史） |

### 5.8 性能目标

| 指标 | 目标 | 实现方式 |
|------|------|---------|
| 首屏 placeholder | < 50ms | 本地内置图片 |
| 有缓存时渲染 | < 100ms | chrome.storage.local 读取 |
| 无缓存时渲染 | < 2s | fetch 元数据 + CDN 加载图片 |
| 扩展体积 | < 50KB | 只含 ID 数组 + 一张 placeholder |
| 预缓存命中率 | > 80% | 后台预加载 3 张 |

---

## 6. CDN 防盗链应对

### 6.1 JetPhotos CDN 结构

```
缩略图  https://cdn.jetphotos.com/200/...
中图    https://cdn.jetphotos.com/400/...
大图    https://cdn.jetphotos.com/full/...
```

### 6.2 防盗链应对策略（按优先级）

**策略 1：直接加载 full 尺寸（首选）**

Chrome 扩展的 newtab 页面发起的图片请求，Referer 为 `chrome-extension://...`。许多 CDN 不会拦截扩展请求。先测试这条路径。

**策略 2：使用 400 中图 + CSS 放大**

如果 full 被拦截，400px 宽的中图通常限制更宽松。用 CSS `image-rendering: auto` + `background-size: cover` 在大屏上质量尚可。

**策略 3：thumbnail + "查看大图" 跳转**

最保守方案。展示 200px 缩略图作为预览，用户点击跳转 JetPhotos 原图页面查看完整大图。降级但完全合规。

**策略 4：元数据中同时存储多尺寸 URL**

```json
{
  "image_url": "https://cdn.jetphotos.com/full/...",
  "thumb_url": "https://cdn.jetphotos.com/400/...",
  "fallback_url": "https://cdn.jetphotos.com/200/..."
}
```

运行时依次尝试 full → 400 → 200，自动降级。

### 6.3 Build 脚本中的验证步骤

```python
def verify_cdn_access(image_url: str) -> bool:
    """验证 CDN URL 是否可直接访问"""
    try:
        resp = requests.head(image_url, headers={
            "Referer": ""  # 模拟无 referer
        }, timeout=5)
        return resp.status_code == 200
    except:
        return False
```

在 build 阶段就验证每个 URL 的可访问性，标记不可用的条目。

---

## 7. 版权合规

### 7.1 导流模型（非盗图模型）

这个扩展的定位是 JetPhotos 的"发现引擎"，每次展示都将用户导向 JetPhotos 原站：

1. 每张图片标注摄影师姓名（可点击跳转）
2. 每张图片标注 "Powered by JetPhotos"
3. 提供「在 JetPhotos 查看原图」跳转链接
4. 不提供下载/右键保存功能
5. 扩展描述声明："Aviation photography courtesy of JetPhotos.com and their respective photographers. This extension drives traffic to JetPhotos."

### 7.2 风险矩阵

| 风险 | 等级 | 缓解 |
|------|------|------|
| CDN 防盗链导致图片不可用 | 高 | 多尺寸降级策略 + build 阶段验证 |
| JetPhotos 要求下架 | 中 | 元数据中保留 contact 字段，响应式下架 |
| 摄影师个人投诉 | 低 | 提供 opt-out 机制，移除对应 JSON |
| Chrome Web Store 审核 | 低 | 声明版权归属，导流性质 |
| CDN URL 格式变更 | 中 | JSON 中存完整 URL（非拼接），变更只需更新 JSON |

---

## 8. 开发计划

### 8.1 Phase 0：可行性验证（2h）

在开始正式开发前，先验证两个关键假设：

```
验证 1：JetPhotos CDN 防盗链
  → 在 Chrome 扩展的 newtab 页面中 <img src="cdn.jetphotos.com/full/...">
  → 确认 full / 400 / 200 哪些尺寸可用

验证 2：JetPhotos 页面结构可解析
  → 手动打开一个 photo 页面
  → 确认 BeautifulSoup 能提取：机型、航司、注册号、摄影师、CDN URL
  → 记录实际的 CSS selector / HTML 结构
```

只有两个验证都通过，才进入正式开发。

### 8.2 里程碑

| 阶段 | 内容 | 预估工时 |
|------|------|---------|
| P0: 可行性验证 | CDN 防盗链测试 + 页面解析测试 | 2h |
| P1: Build 脚本 | Python 脚本：输入 URL 列表 → 输出 JSON 文件 | 3h |
| P2: 数据策展 | 人工收集 150 个 JetPhotos photo URL | 3-4h |
| P3: 数据生成 | 运行 build 脚本 + 验证 + 部署 GitHub Pages | 1h |
| P4: 扩展骨架 | Manifest V3 + newtab 覆盖 + photo-ids.js | 1h |
| P5: 核心渲染 | 随机选取 → fetch 元数据 → 加载图片 → 信息浮层 | 3h |
| P6: 预缓存 | Service Worker + chrome.storage + 预加载逻辑 | 2h |
| P7: 交互打磨 | 换一张、收藏、键盘快捷键、crossfade 动画 | 2h |
| P8: 图标 + 打包 | 扩展图标 + Chrome Web Store 打包 | 1h |
| **合计** | | **~18-19h** |

### 8.3 维护周期

| 频率 | 操作 | 方式 |
|------|------|------|
| 随时 | 新增图片 | 追加 URL → 跑 build 脚本 → git push |
| 每季度 | 检查 CDN 存活 | 跑验证脚本，替换失效条目 |
| 每半年 | 更新扩展 photoIds | 同步 index.json → 发布新版本 |
| 被动 | JetPhotos 改版 | 更新 build 脚本的 HTML parser |

---

## 9. 未来演进路径

```
方案 B v1（当前）
  │  手动策展 150 张，GitHub Pages 托管元数据
  │
  ▼
方案 B v2（自然演进）
  │  扩展支持「热更新 photoIds」：
  │  启动时 fetch index.json，与本地 photo-ids.js 合并
  │  新增图片无需重发扩展版本
  │
  ▼
方案 C（完整体）
  │  Cloudflare Worker 替代 GitHub Pages
  │  自动抓取 JetPhotos 热门图片
  │  图片库自动增长，内容常新
```

B → C 的迁移非常平滑：扩展代码几乎不需要改动，只需将 `config.js` 中的 `DATA_BASE_URL` 从 GitHub Pages 切换到 Cloudflare Worker 端点。

---

## 10. Claude Code 执行指令

### 10.1 Phase 0: 可行性验证

```
验证 JetPhotos CDN 图片在 Chrome 扩展 newtab 页面中是否可直接加载。

操作：
1. 创建一个最小 Manifest V3 扩展，只有 newtab.html
2. 在页面中嵌入 3-5 张 JetPhotos CDN 图片（full/400/200 各尺寸）
3. 加载扩展，观察哪些尺寸可用
4. 记录结果

同时：手动 fetch 一个 JetPhotos 照片页面的 HTML，分析实际 DOM 结构，
确认机型/航司/注册号/摄影师/CDN URL 的提取方式。
```

### 10.2 Phase 1-3: Build 脚本 + 数据

```
开发 JetPhotos 数据采集 build 脚本。

输入：curated-urls.txt（每行一个 JetPhotos 照片页 URL）
输出：photos/{id}.json + index.json + categories/*.json

技术栈：Python 3 + requests + BeautifulSoup4
约束：
- 请求间隔 3-5 秒随机
- 友好 User-Agent
- 输出 JSON 含完整元数据（参照文档 3.1 的数据结构）
- 自动分类到 widebody/narrowbody/military 等类别
- 验证每个 CDN URL 的可访问性
- 生成 index.json 和分类索引
```

### 10.3 Phase 4-8: Chrome 扩展

```
开发 Chrome 扩展，架构对标 Google Earth View。

核心逻辑：
1. 扩展内置 photo-ids.js（photoId 数组）
2. 每次新 Tab → 随机选 ID → fetch GitHub Pages 上的 {id}.json → 渲染
3. Service Worker 后台预缓存下 3 张
4. 完全对标 Earth View 的运行时数据流

技术约束：
- Manifest V3
- 纯 vanilla JS，ES modules
- CONFIG.DATA_BASE_URL 可配置
- 多尺寸图片降级（full → 400 → 200）
- 预缓存使用 chrome.storage.local
- crossfade 过渡动画
- 底部信息浮层含摄影师归属和 JetPhotos 链接
```