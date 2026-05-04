# API Key 与账单导出开通指南

这份指南说明 `.env` 里各个平台需要填写哪些字段，以及去哪里开通对应的 API Key、账单导出或只读权限。所有密钥只放在本机 `.env`，不要提交到 git。

## 推荐开通顺序

1. 先不启用任何自动平台，确认 dashboard 可以启动。
2. 填 ChatGPT Pro 的手动订阅成本，因为它不需要 API Key。
3. 开通 OpenAI API、MiniMax、Brave Search、DigitalOcean 这类只需要一个 API token 的平台。
4. 最后配置 Gemini 的 Google Cloud Billing Export 和百度千帆 AK/SK；这两项权限和控制台步骤更多。

改完 `.env` 后重启服务：

```bash
scripts/restart-server.sh
```

打开 http://127.0.0.1:18765 后点击 `Sync now`，看对应平台状态是否从 `missing_config` 变成 `configured` 或成功同步。

## 通用配置

```env
APP_HOST=127.0.0.1
APP_PORT=18765
DATABASE_URL=sqlite:///./data/api_spend.sqlite3
SYNC_INTERVAL_HOURS=6
DEFAULT_CURRENCY=USD
HTTP_TIMEOUT_SECONDS=30
```

- `SYNC_INTERVAL_HOURS`：后台定时同步间隔，默认每 6 小时拉一次。
- `DEFAULT_CURRENCY`：平台没有返回币种时使用的默认币种。
- `DATABASE_URL`：本地 SQLite 数据库路径，默认写入 `data/`，该目录已被 git 忽略。

`*_ENABLED=true` 表示该平台会参与定时同步和手动 `Sync now`；`false` 表示完全跳过这个平台。

## OpenAI API

需要填写：

```env
OPENAI_ENABLED=true
OPENAI_ADMIN_API_KEY=
OPENAI_ORG_ID=
```

开通步骤：

1. 用 Organization Owner 账号登录 OpenAI Platform。
2. 进入 Organization settings 里的 Admin keys 页面：`https://platform.openai.com/settings/organization/admin-keys`。
3. 点击 `Create new admin key` 创建 Admin API key。这里不是普通项目的 API keys 页面。
4. 这个 dashboard 调用的是组织级 Usage 和 Costs 接口，OpenAI 官方示例也使用 `OPENAI_ADMIN_KEY` 调用这些接口；如果创建页允许选择 scope，请给 usage/costs 相关读取权限，或使用只读/最小可用权限。
5. 把生成的 key 填到 `OPENAI_ADMIN_API_KEY`。
6. 如果你的账号有多个 organization，或接口要求指定组织，把组织 ID 填到 `OPENAI_ORG_ID`；单组织账号通常可以留空。

注意：

- ChatGPT 订阅和 OpenAI API 是两套账单系统，OpenAI 官方说明二者的费用和历史记录通常分开查看。
- 这里的 OpenAI API 同步会查询 `/v1/organization/costs` 和 `/v1/organization/usage/completions`，展示 API 费用、输入 token、输出 token 和请求数。
- 只有 Organization Owner 可以创建和使用 Admin API key；普通 Project API key 通常无法调用这些 organization 级接口。

官方文档：

- OpenAI Usage API: https://platform.openai.com/docs/api-reference/usage
- OpenAI Admin API keys: https://platform.openai.com/settings/organization/admin-keys
- OpenAI Admin API FAQ: https://help.openai.com/en/articles/9687866-admin-and-audit-logs-api-for-the-api-platform
- OpenAI ChatGPT vs Platform billing: https://help.openai.com/en/articles/9039756-billing-settings-in-chatgpt-vs-platform

## ChatGPT Pro

需要填写：

```env
CHATGPT_PRO_ENABLED=true
CHATGPT_PRO_PLAN_NAME=ChatGPT Pro
CHATGPT_PRO_PRICE=0
CHATGPT_PRO_CURRENCY=USD
CHATGPT_PRO_BILLING_PERIOD=monthly
CHATGPT_PRO_RENEWAL_DATE=
CHATGPT_PRO_NOTES=
```

开通步骤：

1. 不需要 API Key。
2. 在 ChatGPT 里查看你的订阅价格、续费日期和币种。
3. 把价格填入 `CHATGPT_PRO_PRICE`，续费日期建议用 `YYYY-MM-DD` 格式填入 `CHATGPT_PRO_RENEWAL_DATE`。

注意：

- ChatGPT Pro 当前没有官方 token 用量查询 API。
- dashboard 只把它作为手动订阅成本记录，不会展示 ChatGPT Pro 的 token 消耗。

官方文档：

- OpenAI ChatGPT vs Platform billing: https://help.openai.com/en/articles/9039756-billing-settings-in-chatgpt-vs-platform

## MiniMax Token Plan

需要填写：

```env
MINIMAX_ENABLED=true
MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://www.minimax.io
MINIMAX_PLAN_NAME=
MINIMAX_PLAN_PRICE=0
MINIMAX_PLAN_CURRENCY=USD
MINIMAX_PLAN_START_DATE=
MINIMAX_PLAN_END_DATE=
```

开通步骤：

1. 登录 MiniMax 开放平台，进入 Token Plan 或账户管理页面。
2. 创建或复制 Token Plan API Key。
3. 国际站通常使用 `MINIMAX_BASE_URL=https://www.minimax.io`；国内站可使用 `https://www.minimaxi.com`。
4. 把套餐名称、购买价格、开始日期、到期日期手动填入对应 `MINIMAX_PLAN_*` 字段。

注意：

- MiniMax 官方文档提供 Token Plan 用量查询接口 `/v1/token_plan/remains`，dashboard 会使用 `MINIMAX_API_KEY` 查询剩余额度。
- Token Plan API Key 和普通开放平台 API Key 不可混用；普通 Key 是按量付费，Token Plan Key 是订阅套餐额度。
- dashboard 展示套餐价格和周期信息时依赖你手动填写的 `MINIMAX_PLAN_*` 字段。

官方文档：

- MiniMax Token Plan FAQ: https://platform.minimax.io/docs/token-plan/faq
- MiniMax 国内站 Token Plan FAQ: https://platform.minimaxi.com/docs/token-plan/faq

## Gemini API

Gemini 的费用推荐通过 Google Cloud Billing Export 导出到 BigQuery 后查询。需要填写：

```env
GEMINI_ENABLED=true
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
GCP_BILLING_PROJECT_ID=
GCP_BILLING_DATASET=
GCP_BILLING_TABLE=
GEMINI_SERVICE_FILTER=Gemini API
```

先理解 Google Cloud 里的几个对象：

- `Cloud Billing account` 是付款账户，绑定付款方式，最终账单从这里出。
- `Google Cloud Project` 是资源容器，Gemini API、BigQuery dataset、service account 都属于某个 project。
- Billing Export 的目标 project 不一定要和 Gemini API 所在 project 相同。推荐单独建一个类似 `api-spend-billing-export` 的项目，只用来存放 BigQuery 账单导出表。
- “确认这个项目已启用结算”指的是：这个用于存放 BigQuery 导出表的 project 要绑定到你的 Cloud Billing account，否则 BigQuery dataset/table 可能无法创建或使用。

可以按这个关系理解：

```text
Cloud Billing account
  ├─ Gemini API 项目
  ├─ 其他 GCP 项目
  └─ api-spend-billing-export 项目
       └─ BigQuery dataset / billing export table
```

开通步骤：

1. 在 Google Cloud Console 选择一个用于存放账单导出数据的项目，建议单独建一个 FinOps 或 billing 项目。
2. 确认这个项目已启用结算，并且关联到你要导出的 Cloud Billing account。
3. 创建 BigQuery dataset，例如 `api_spend_billing`。记下 project ID 和 dataset ID。
   - 中文控制台路径：进入 **BigQuery** 后，在左侧 **资源管理器** 里找到项目 `api-spend-billing-export`。
   - 点击项目名右侧的 `⋮` 三点菜单。
   - 选择 **创建数据集**。
   - **数据集 ID** 填 `api_spend_billing`。
   - **位置类型** 选 **多区域**，**多区域** 可选 `US`。
   - 其他保持默认，点击 **创建数据集**。
4. 进入 Cloud Billing 的 Billing export 页面，选择目标 billing account。
   - 中文控制台路径：左上角菜单 `☰` -> **结算** -> 选择你的 **结算账号** -> 左侧 **账单导出**。
   - 页面标题通常是 **结算数据导出**，页签是 **BigQuery Export**。
5. 启用标准使用费用导出，目标选择上一步的 BigQuery dataset。
   - 在 **标准使用费用** 这一块点击 **修改设置**。
   - 选择 **项目**：`api-spend-billing-export`。
   - 选择 **数据集**：`api_spend_billing`，或你实际创建的数据集 ID。
   - 保存设置。
   - 暂时不用启用 **详细的使用费**、**价格**、**承诺使用折扣导出**。当前 dashboard 查询标准账单导出就够；价格表和 CUD 导出不是实际用量账单。
6. 等待导出表生成。常见表名类似 `gcp_billing_export_v1_XXXXXX` 或 `gcp_billing_export_resource_v1_XXXXXX`，把真实表名填入 `GCP_BILLING_TABLE`。
7. 创建一个 service account，用于本地 dashboard 查询 BigQuery。
8. 给这个 service account 授权：
   - 在包含导出表的 dataset 上授予 `BigQuery Data Viewer`。
   - 在用于执行查询的项目上授予 `BigQuery Job User`。
9. 为 service account 创建 JSON key，下载到本机非仓库目录，例如 `~/.config/api-spend-dashboard/gcp-billing-reader.json`。
10. 把 JSON key 的绝对路径填到 `GOOGLE_APPLICATION_CREDENTIALS`。

注意：

- Billing Export 不是实时数据，刚启用后可能要等一段时间才有行。
- Billing Export 通常不会回填启用之前的历史账单数据。
- `GEMINI_SERVICE_FILTER` 会用来匹配 BigQuery billing export 里的 `service.description`，默认是 `Gemini API`。如果同步后没有数据，先在 BigQuery 里查看真实服务名称，再调整这个字段。
- BigQuery 查询本身可能产生很小费用，Google 官方文档也提示存储和查询 billing export 数据会有少量费用。

官方文档：

- Set up Cloud Billing data export to BigQuery: https://cloud.google.com/billing/docs/how-to/export-data-bigquery-setup
- BigQuery IAM access control: https://cloud.google.com/bigquery/docs/control-access-to-resources-iam
- Create and delete service account keys: https://cloud.google.com/iam/docs/keys-create-delete

## 百度千帆

需要填写：

```env
QIANFAN_ENABLED=true
BAIDU_ACCESS_KEY_ID=
BAIDU_SECRET_ACCESS_KEY=
QIANFAN_ENDPOINT=https://qianfan.baidubce.com
QIANFAN_SERVICE_IDS=
QIANFAN_APP_IDS=
```

开通步骤：

1. 登录百度智能云控制台。
2. 进入访问控制或安全认证，创建 Access Key，拿到 `Access Key ID` 和 `Secret Access Key`。
3. 建议使用子用户，不要使用主账号 AK/SK。
4. 给子用户授予千帆只读权限。千帆服务调用概览接口要求具备以下权限之一：`QianfanFullControlAccessPolicy`、`QianfanReadAccessPolicy` 或 `QianfanServiceReadAccessPolicy`。优先选只读权限。
5. 把 AK/SK 填到 `BAIDU_ACCESS_KEY_ID` 和 `BAIDU_SECRET_ACCESS_KEY`。
6. 如需限制统计范围，把服务 ID 填到 `QIANFAN_SERVICE_IDS`，应用 ID 填到 `QIANFAN_APP_IDS`，多个值用英文逗号分隔。

注意：

- dashboard 当前查询千帆 `DescribeServiceMetric`，展示请求数和 token 用量。
- 千帆这个接口返回的是调用概览指标，不直接返回费用，所以 dashboard 的千帆费用会显示为空。

官方文档：

- 百度智能云如何获取 AK/SK: https://cloud.baidu.com/doc/Reference/s/9jwvz2egb/
- 千帆查询服务调用概览 DescribeServiceMetric: https://cloud.baidu.com/doc/qianfan-api/s/4mm33t0kj
- 千帆认证鉴权: https://cloud.baidu.com/doc/qianfan-api/s/ym9chdsy5

## Brave Search API

需要填写：

```env
BRAVE_ENABLED=true
BRAVE_API_KEY=
BRAVE_PROBE_QUERY=api spend dashboard
BRAVE_PRICE_PER_1000_REQUESTS=5
BRAVE_CURRENCY=USD
```

开通步骤：

1. 打开 Brave Search API 页面并进入 API dashboard。
2. 创建或复制 API key。
3. 把 key 填到 `BRAVE_API_KEY`。
4. 按你的 Brave Search 订阅价格，把每 1000 次请求价格填到 `BRAVE_PRICE_PER_1000_REQUESTS`。

注意：

- Brave Search API 没有单独的费用查询接口。
- dashboard 会发起一次轻量查询，读取响应里的 quota/rate-limit header 来估算用量，再按 `BRAVE_PRICE_PER_1000_REQUESTS` 估算费用。
- `BRAVE_PROBE_QUERY` 是探测 quota 时使用的查询词，可以保持默认。

官方文档：

- Brave Search API: https://brave.com/search/api/
- Brave Search API rate limiting: https://api-dashboard.search.brave.com/documentation/guides/rate-limiting

## DigitalOcean

需要填写：

```env
DIGITALOCEAN_ENABLED=true
DIGITALOCEAN_TOKEN=
```

开通步骤：

1. 登录 DigitalOcean Control Panel。
2. 进入左侧 `API`，在 `Personal access tokens` 里创建 token。
3. 如果页面支持 Custom Scopes，授予 billing 相关读取权限；如果不支持细粒度 scope，选择 Read Only。
4. 复制 token，填入 `DIGITALOCEAN_TOKEN`。

注意：

- DigitalOcean token 只显示一次，创建后立即保存到 `.env` 或密码管理器。
- dashboard 会读取 DigitalOcean billing balance / usage 相关接口，展示月内费用或余额信息。

官方文档：

- Create a Personal Access Token: https://docs.digitalocean.com/reference/api/create-personal-access-token/
- Billing API Reference: https://docs.digitalocean.com/platform/billing/reference/api/
- Billing API scope: https://docs.digitalocean.com/reference/api/scopes/billing/

## 安全建议

- `.env` 已在 `.gitignore` 中，不要把真实 key 写进 `.env.example`、README、issue 或截图。
- 优先使用只读权限、子用户或自定义 scope。
- Google service account JSON 不要放进仓库目录；如果必须放本项目目录，先确认对应路径已加入 `.gitignore`。
- 如果 key 曾经进入 git、聊天记录、日志或截图，直接作废并重新生成。
- 开源前运行 `git status --short` 和 `git diff --cached`，确认没有 `.env`、service account JSON、API token 或本地数据库被提交。
