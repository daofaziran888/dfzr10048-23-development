"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。

复验路由放在通用资源路由之前注册，避免 `/api/signoff_reverify/packs`
被通用动态路径 `/{module}/{entry_id}` 抢先匹配。
"""
from __future__ import annotations

from app.routers import resource, signoff_reverify

ROUTERS = [signoff_reverify, resource]
