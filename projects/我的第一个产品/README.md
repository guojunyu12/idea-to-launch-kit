# AIGC 内容生成平台

当前完成到 V7 阶段 2-2：后端已具备邮箱验证码会话、角色隔离、模板发布边界，以及“已发布模板 + 文字提示词 + 尺寸 + 千问模型 → 生成结果”的用户主链路。旧版上传与任务接口继续保留。

## 本地启动

```bash
cd projects/我的第一个产品/backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

打开：

- 健康检查：<http://127.0.0.1:8000/healthz>
- API 文档：<http://127.0.0.1:8000/docs>
- 旧版兼容测试台：<http://127.0.0.1:8000/test>
- V7 点击式验收台：<http://127.0.0.1:8000/test>

当前真实模式使用阿里云百炼 DashScope 的 `qwen-image-2.1-turbo`，由本地 `.env` 的 `GEN_PROVIDER_MODE=qwen` 启动。真实 Key 只放在本地 `.env`，不要提交到 Git。

## V7 登录与角色

开发期默认 `AUTH_MODE=dev_fixed`，固定验证码从 `AUTH_DEV_CODE` 读取；接口不会回显验证码。普通邮箱自动创建为 `user`，`ADMIN_EMAILS` 和 `OPERATOR_EMAILS` 中的邮箱分别映射为管理员和运营人员。会话通过 HttpOnly Cookie 保存。

接口顺序：

1. `POST /api/v1/auth/request-code`，请求体 `{"email":"user@example.com"}`。
2. `POST /api/v1/auth/verify-code`，提交返回的 `challenge_id`、邮箱和本地固定码。
3. `GET /api/v1/auth/me` 查看当前角色；`POST /api/v1/auth/logout` 注销。

生产环境禁止固定验证码模式，需在上线阶段接入正式邮件服务并启用安全 Cookie。

## 模板审核

公开接口 `GET /api/v1/templates` 只返回已发布模板。运营或管理员登录后可调用：

- `POST /api/v1/admin/templates/import` 导入候选模板；
- `POST /api/v1/admin/templates/{id}/review` 审核通过或驳回；
- `POST /api/v1/admin/templates/{id}/publish` 发布审核通过的模板。

模板模块使用 `sticker`、`mobile_wallpaper`、`desktop_wallpaper`；旧 `kind=wallpaper` 查询继续兼容手机壁纸。

## V7 用户生成

登录后从已发布模板中选择模板、输入提示词、选择比例或自定义 256–4096 px 尺寸，再点击生成。可用模型从 `GET /api/v1/models` 返回，当前本地默认是 `qwen-image-2.1-turbo`。

- `POST /api/v1/generations` 创建生成任务；需要登录 Cookie。
- `GET /api/v1/generations` 查看自己的生成记录。
- `GET /api/v1/generations/{id}/asset` 下载自己的 PNG 结果。
- 每个用户每天 3 次免费生成；成功记录额度使用，失败记录返还状态。

## 验证

```bash
cd projects/我的第一个产品/backend
PYTHONPATH=. .venv/bin/python -m pytest -q
```

从工具包根目录运行阶段自检：

```bash
cd /Users/guo/Documents/通用项目/aigc-zhong-tai
bash kit.sh 自检 我的第一个产品
```

阶段2-1和阶段2-2的技术说明、验收步骤见 `docs/阶段文档/` 与 `docs/evidence/阶段2-2/照着做清单.md`。

## 真实冒烟

```bash
cd /Users/guo/Documents/通用项目/aigc-zhong-tai/projects/我的第一个产品
set -a && source backend/.env && set +a
SMOKE_STAGE=阶段2-2 backend/.venv/bin/python scripts/smoke_real.py
```

脚本会把真实调用结果写入 `docs/evidence/阶段2-1/冒烟记录.md`，并保存结果图片；不要把 Key 或完整输入内容写入文档。Qwen-Image 使用 DashScope 原生多模态生图接口，应用侧仍会把输出统一保存为 PNG。
