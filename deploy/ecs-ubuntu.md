# Ubuntu ECS 部署清单

本文用于在用户手动重装后的 Ubuntu 22.04 LTS ECS 上部署 Code-Agent。首轮部署只使用公网上的 IP/HTTP 访问和 Mock Provider；不包含自动登录、自动重装、域名、HTTPS、备份或真实云端 Provider。

## 1. 前置条件与安全组

1. 在阿里云控制台确认 ECS 已安装 Ubuntu 22.04 LTS，并记录公网 IP。
2. 在安全组中只开放 TCP 80；SSH TCP 22 只允许用户可信的公网 IP。不要把 SSH 或其他管理端口开放给 `0.0.0.0/0`，也不要继续保留重装前的公网 RDP 规则。
3. 通过用户自己的密钥登录服务器。本文不记录服务器地址、密码、私钥、API Key 或 Provider 凭据。

## 2. 安装 Docker Engine 与 Docker Compose

在 ECS 上执行官方 Docker Engine 安装流程，确保 `docker` 服务已经启动，并确认 Compose 插件可用：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc >/dev/null
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

## 3. 获取、构建与启动

使用用户自己的公开仓库地址克隆项目；不要把 token、私钥或密钥写进命令和文件：

```bash
git clone <公开仓库地址> code-agent
cd code-agent
sudo docker compose -f docker-compose.yml up -d --build
sudo docker compose ps
sudo docker compose logs --tail=100 code-agent
```

服务通过主机 TCP 80 映射到容器 TCP 8000。浏览器访问 `http://<ECS公网IP>/`，即可进行首轮 IP/HTTP 验收。默认 Provider 是 Mock Provider，不会读取 keyring，也不会访问真实 Provider。

## 4. 更新、回滚与持久化

更新前先查看当前状态和日志；更新失败时保留卷并回滚代码版本：

```bash
git fetch --all --prune
git pull --ff-only
sudo docker compose pull
sudo docker compose up -d --build
sudo docker compose ps
sudo docker compose logs --tail=100 code-agent
```

如果新版本异常：

```bash
git log --oneline -5
git checkout <已验证的版本>
sudo docker compose up -d --build
sudo docker compose ps
sudo docker compose logs --tail=100 code-agent
```

SQLite 文件位于容器内 `/var/lib/code-agent/state.db`，由 Compose 命名卷 `code-agent-state` 持久化。普通重建、停止和容器重启不应删除任务记录；只有明确执行 `docker compose down -v` 才会删除该卷，因此销毁卷前必须由用户另行完成备份决定。

彻底清理临时部署时才执行：

```bash
sudo docker compose down -v
```

## 5. 边界与后续工作

本清单不自动修改 ECS 安全组，不自动登录或重装系统，不配置域名、HTTPS、备份，也不启用真实云端 Provider。IP/HTTP 仅用于临时演示；正式公网服务必须另行设计域名、TLS、访问控制、备份和监控。
