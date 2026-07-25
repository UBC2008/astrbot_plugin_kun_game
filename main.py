import json
import os
import random
import time
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger, AstrBotConfig

# ==================== 常量 ====================

KUN_NAMES = [
    "菜虚鲲",
    "将鲲",
    "犷鲲",
    "尘鲲",
    "土鲲",
    "岩鲲",
    "石鲲",
    "沙鲲",
    "雷鲲",
    "雪鲲",
    "虹鲲",
    "碧鲲",
    "蓝鲲",
    "橙鲲",
    "黑鲲",
    "暗鲲",
    "铁头鲲",
    "钢背鲲",
    "彩鲲",
    "炎鲲",
    "冰鲲",
    "凶鲲",
    "恶鲲",
    "幻鲲",
    "诡鲲",
    "炬目鲲",
    "柯温鲲",
    "胖头鲲",
    "阳鲲",
    "靓鲲",
    "尸鲲",
    "血鲲",
    "骨鲲",
    "腐鲲",
    "毒鲲",
    "妖鲲",
    "魔鲲",
    "鬼鲲",
    "圣鲲",
    "灵鲲",
    "冥鲲",
    "玄鲲",
    "炫鲲",
    "帝鲲",
    "齿鲲",
    "剑鲲",
    "铠鲲",
    "阴鲲",
    "烈鲲",
]

BOSS_NAMES = ["鲲霸", "鲲皇", "鲲帝", "鲲神", "上古鲲鹏", "混沌鲲", "灭世鲲"]

KUN_ATTRIBUTES = {
    "无": "无属性",
    "魑": "♂魑：免疫强袭",
    "魅": "♂魅：免疫吞噬",
    "魍": "♂魍：免疫攻击",
    "魉": "♂魉：体重低于666千克时恢复至1000千克",
    "淫": "淫：被吞噬后对方75%几率狗带；攻击/被攻击25%几率恢复大量体重",
    "馋": "馋：吞噬失败不损体重；幻化不耗体重；不能攻击；体重>1000kg暴死(渡劫成功可暂时突破)",
    "贪": "贪：吞噬/攻击30%得蛋；磨炼70%不耗节操；放生得2-10蛋",
    "惰": "惰：极强防御不易被吞噬；免疫强袭",
    "怒": "怒：极强攻击易吞噬；开始25%致命一击",
    "妒": "妒：比其体重大的鲲无法对其吞噬或攻击",
    "傲": "傲：无视对方属性",
    "悲": "悲：初始体重=榜一体重+1000kg；不可幻化；(孵化率0.7%)",
}

# 体重范围
DEFAULT_WEIGHT_MIN = 50
DEFAULT_WEIGHT_MAX = 200

# 砸蛋概率: 道具率 = 运势/200*100%
EGG_SMASH_LIMIT = 100

# 致命一击倍率
CRITICAL_MULTIPLIER = 1.5

# 吞噬相关
DEVOUR_BASE_CHANCE = 50

# ==================== 数据管理 ====================


def get_data_dir() -> Path:
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path

    data_path = get_astrbot_data_path() or Path("data")
    plugin_dir = Path(data_path) / "plugin_data" / "astrbot_plugin_kun_game"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    return plugin_dir


class GameData:
    def __init__(self, config: dict = None):
        self.dir = get_data_dir()
        self._groups: dict[str, dict] = {}
        self._cfg = config or {}
        self._load()

    def _load(self):
        gf = self.dir / "groups.json"
        if gf.exists():
            self._groups = json.loads(gf.read_text(encoding="utf-8"))

    def save(self):
        (self.dir / "groups.json").write_text(
            json.dumps(self._groups, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get_player(self, gid: str, qq: str) -> dict:
        group = self.get_group(gid)
        if "players" not in group:
            group["players"] = {}
        players = group["players"]
        if qq not in players:
            players[qq] = self._default_player(qq)
        return players[qq]

    def _default_player(self, qq: str) -> dict:
        cfg = self._cfg
        return {
            "qq": qq,
            "kun": None,
            "jie_cao": cfg.get("default_jie_cao", 50),
            "eggs": 0,
            "divine_weapon": 0,
            "phantom_pills": 0,
            "chicken_soup": 0,
            "resurrection_pills": 0,
            "luck": cfg.get("default_luck", 50),
            "today_train": 0,
            "signed_today": False,
            "last_sign_date": "",
        }

    def get_group(self, gid: str) -> dict:
        if gid not in self._groups:
            self._groups[gid] = self._default_group(gid)
        return self._groups[gid]

    def _default_group(self, gid: str) -> dict:
        return {
            "gid": gid,
            "kun_enabled": True,
            "game_enabled": True,
            "owner_qq": "",
            "players": {},
            "boss": None,
            "auction": None,
            "death_list": [],
            "last_boss_date": "",
            "anti_assault": [],
            "anti_devour": [],
            "anti_attack": [],
            "mini_game": None,
            "duel_champion": None,
        }

    def new_day_reset(self, gid: str):
        today = datetime.now().strftime("%Y-%m-%d")
        group = self.get_group(gid)
        if group.get("last_boss_date", "") != today:
            group["boss"] = None
            group["last_boss_date"] = today
        for pid in list(group.get("players", {}).keys()):
            p = group["players"][pid]
            if p.get("last_sign_date", "") != today:
                p["signed_today"] = False
                p["today_train"] = 0
                p["last_sign_date"] = today


# ==================== 辅助函数 ====================


def format_weight(w: float) -> str:
    if w >= 1000:
        return f"{w / 1000:.1f}吨"
    return f"{w:.0f}千克"


def parse_qq_id(msg: str) -> str | None:
    """尝试从消息中提取QQ号 (纯数字或@后跟数字)"""
    import re

    # 匹配纯数字串（5-12位）
    m = re.search(r"(\d{5,12})", msg)
    if m:
        return m.group(1)
    return None


# ==================== 主插件 ====================


class KunGamePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        self.data = GameData(config=self.config)

    async def initialize(self):
        self.prefix = self.config.get("command_prefix", "*")
        logger.info(f"养鲲游戏插件已加载 (命令前缀: {self.prefix})")

    async def terminate(self):
        self.data.save()
        logger.info("养鲲游戏插件已卸载")

    # ==================== 管理员指令 (AstrBot 管理员权限) ====================

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("鲲开")
    async def cmd_kun_on(self, event: AstrMessageEvent):
        gid = event.get_group_id()
        if not gid:
            yield event.plain_result("此命令仅支持群聊使用！")
            event.stop_event()
            return
        self.data.new_day_reset(str(gid))
        group = self.data.get_group(str(gid))
        yield event.plain_result(self._toggle_kun(group, True))
        event.stop_event()

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("鲲关")
    async def cmd_kun_off(self, event: AstrMessageEvent):
        gid = event.get_group_id()
        if not gid:
            yield event.plain_result("此命令仅支持群聊使用！")
            event.stop_event()
            return
        self.data.new_day_reset(str(gid))
        group = self.data.get_group(str(gid))
        yield event.plain_result(self._toggle_kun(group, False))
        event.stop_event()

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("小游戏开")
    async def cmd_game_on(self, event: AstrMessageEvent):
        gid = event.get_group_id()
        if not gid:
            yield event.plain_result("此命令仅支持群聊使用！")
            event.stop_event()
            return
        group = self.data.get_group(str(gid))
        yield event.plain_result(self._toggle_game(group, True))
        event.stop_event()

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("小游戏关")
    async def cmd_game_off(self, event: AstrMessageEvent):
        gid = event.get_group_id()
        if not gid:
            yield event.plain_result("此命令仅支持群聊使用！")
            event.stop_event()
            return
        group = self.data.get_group(str(gid))
        yield event.plain_result(self._toggle_game(group, False))
        event.stop_event()

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("刷新BOSS")
    async def cmd_refresh_boss(self, event: AstrMessageEvent):
        gid = event.get_group_id()
        if not gid:
            yield event.plain_result("此命令仅支持群聊使用！")
            event.stop_event()
            return
        self.data.new_day_reset(str(gid))
        group = self.data.get_group(str(gid))
        yield event.plain_result(self._refresh_boss(group))
        event.stop_event()

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("数据清除")
    async def cmd_clear_data(self, event: AstrMessageEvent):
        gid = event.get_group_id()
        if not gid:
            yield event.plain_result("此命令仅支持群聊使用！")
            event.stop_event()
            return
        uid = str(event.get_sender_id())
        name = event.get_sender_name()
        self.data.new_day_reset(str(gid))
        group = self.data.get_group(str(gid))
        yield event.plain_result(self._clear_data(group, uid, name))
        event.stop_event()

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("强制下架")
    async def cmd_force_delist(self, event: AstrMessageEvent):
        gid = event.get_group_id()
        if not gid:
            yield event.plain_result("此命令仅支持群聊使用！")
            event.stop_event()
            return
        uid = str(event.get_sender_id())
        name = event.get_sender_name()
        group = self.data.get_group(str(gid))
        yield event.plain_result(self._auction_force_delist_admin(group, uid, name))
        event.stop_event()

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("修改")
    async def cmd_admin_edit(
        self, event: AstrMessageEvent, target_qq: str, project: str, value: str = ""
    ):
        """修改玩家数据: /修改 QQ号 项目 数值  如 /修改 12345 体重 +100"""
        gid = event.get_group_id()
        if not gid:
            yield event.plain_result("此命令仅支持群聊使用！")
            event.stop_event()
            return
        name = event.get_sender_name()
        group = self.data.get_group(str(gid))
        self.data.new_day_reset(str(gid))
        cmd = f"{target_qq}/{project}/{value}" if value else f"{target_qq}/{project}"
        result = self._admin_edit(cmd, "", str(event.get_sender_id()), name, group)
        if result:
            yield event.plain_result(result)
        else:
            yield event.plain_result(
                "格式: /修改 QQ号 项目 数值\n项目: 鲲/体重/属性/节操/蛋/神器/幻化丹/鸡汤/复活药/运势"
            )
        event.stop_event()

    # ==================== 消息入口 ====================

    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息，处理 * 开头的指令"""
        msg = event.message_str.strip()
        prefix = self.config.get("command_prefix", "*")
        if not msg.startswith(prefix):
            return

        uid = str(event.get_sender_id())
        name = event.get_sender_name()
        gid = event.get_group_id()
        is_private = gid is None

        # 私聊支持的命令
        private_ok = {
            "签到",
            "砸蛋",
            "磨炼",
            "幻化",
            "查阅属性",
            "今日运势",
            "命令菜单",
            "喝鸡汤",
            "当前游戏",
        }
        cmd_part, args_part = self._parse_cmd(msg)

        if is_private:
            if cmd_part not in private_ok:
                yield event.plain_result("此命令仅支持群聊使用！")
                return
            gid = uid  # 私聊时用uid作为gid存数据
        else:
            gid = str(gid)

        self.data.new_day_reset(gid)
        group = self.data.get_group(gid)

        try:
            result = await self._handle_command(
                cmd_part, args_part, uid, gid, name, group, event
            )
            if result:
                yield event.plain_result(result)
                event.stop_event()
        except Exception as e:
            logger.error(f"处理命令 {msg} 出错: {e}", exc_info=True)
            yield event.plain_result(f"处理失败：{e}")

    def _parse_cmd(self, msg: str) -> tuple[str, str]:
        """解析 *命令 参数"""
        prefix = self.config.get("command_prefix", "*")
        msg = msg[len(prefix) :]  # 去掉前缀
        parts = msg.split(maxsplit=1)
        cmd = parts[0] if parts else ""
        args = parts[1] if len(parts) > 1 else ""
        return cmd.strip(), args.strip()

    async def _handle_command(
        self,
        cmd: str,
        args: str,
        uid: str,
        gid: str,
        name: str,
        group: dict,
        event: AstrMessageEvent,
    ) -> str | None:
        player = self.data.get_player(gid, uid)

        # 基本指令（无需游戏开启）
        basic_commands = {
            "签到": lambda: self._sign_in(player, name),
            "当前游戏": lambda: self._current_game(group),
            "命令菜单": lambda: self._command_menu(group),
            "绑定群": lambda: self._bind_group(group, args),
            "查阅属性": lambda: self._check_attr(player, group, name),
            "今日运势": lambda: self._check_luck(player, name),
            "阵亡名单": lambda: self._death_list(group),
            "拍卖行": lambda: self._auction_list(group),
        }
        if cmd in basic_commands:
            return basic_commands[cmd]()

        # 检查游戏是否开启
        if cmd not in () and not group.get("kun_enabled", True):
            return "未开启养鲲小游戏！"

        # 游戏指令
        game_commands = {
            "孵化": lambda: self._hatch(player, group, name),
            "买蛋": lambda: self._buy_eggs(player, name, args),
            "砸蛋": lambda: self._smash_eggs(player, name, args),
            "喂食": lambda: self._feed(player, name, args, group),
            "磨炼": lambda: self._train(player, name, args, group),
            "幻化": lambda: self._evolve(player, name, group),
            "吞噬": lambda: self._devour(player, uid, name, args, gid, group),
            "攻击": lambda: self._attack(player, uid, name, args, gid, group),
            "强袭": lambda: self._assault(player, uid, name, args, gid, group),
            "扔蛋": lambda: self._throw_egg(player, uid, name, args, group),
            "喝鸡汤": lambda: self._drink_soup(player, name, args, group),
            "渡劫": lambda: self._tribulation(player, name, group),
            "放生": lambda: self._release(player, name, group),
            "复活": lambda: self._resurrect(player, name, group),
            "查询BOSS": lambda: self._query_boss(group),
            "攻击BOSS": lambda: self._attack_boss(player, uid, name, group, gid),
            "吞噬BOSS": lambda: self._devour_boss(player, uid, name, group, gid),
            "强袭BOSS": lambda: self._assault_boss(player, uid, name, group, gid),
            "出售": lambda: self._auction_sell(player, uid, name, args, group),
            "出价": lambda: self._auction_bid(player, uid, name, args, group),
            "成交": lambda: self._auction_deal(player, uid, name, group),
            "免疫强袭": lambda: self._immunity(
                player, uid, name, args, "anti_assault", group
            ),
            "免疫吞噬": lambda: self._immunity(
                player, uid, name, args, "anti_devour", group
            ),
            "免疫攻击": lambda: self._immunity(
                player, uid, name, args, "anti_attack", group
            ),
            "查骰子": lambda: self._roll_dice(player, name, args),
            "奥数比赛": lambda: self._start_mini_game(group, "math"),
            "数星星": lambda: self._start_mini_game(group, "star"),
            "抄作业": lambda: self._start_mini_game(group, "homework"),
            "查看群主指令": lambda: self._owner_commands(group),
        }

        if cmd in game_commands:
            handler = game_commands[cmd]
            return handler()

        # Mini game commands
        if cmd == "抽群主一个大嘴巴":
            return self._mini_game_slap(player, uid, name, group)
        if cmd == "单挑群主":
            return self._mini_game_duel(player, uid, name, group)

        # Mini game answer: *=number or *=text
        if cmd.startswith("=") and len(cmd) > 1:
            return self._mini_game_answer(cmd[1:], uid, name, group)

        return None

    # ==================== 管理指令 ====================

    def _toggle_kun(self, group: dict, enabled: bool) -> str:
        group["kun_enabled"] = enabled
        self.data.save()
        return f"养鲲小游戏已{'开启' if enabled else '关闭'}！"

    def _toggle_game(self, group: dict, enabled: bool) -> str:
        group["game_enabled"] = enabled
        self.data.save()
        return f"小游戏已{'开启' if enabled else '关闭'}！"

    def _bind_group(self, group: dict, args: str) -> str:
        # 绑定群主
        gid = args.strip()
        if not gid.isdigit():
            return "请检查群号是否正确！\n格式: *绑定群 群号"
        group["owner_qq"] = gid
        self.data.save()
        return f"已绑定群 {gid}"

    def _clear_data(self, group: dict, uid: str, name: str) -> str:
        gid = group["gid"]
        # 清除该群所有玩家数据
        # 注意: 当前简化实现, 仅清空游戏相关的群数据
        group["boss"] = None
        group["auction"] = None
        group["death_list"] = []
        group["anti_assault"] = []
        group["anti_devour"] = []
        group["anti_attack"] = []
        self.data.save()
        return "游戏数据成功清除！"

    def _owner_commands(self, group: dict) -> str:
        p = self.config.get("command_prefix", "*")
        return (
            "====群主指令（AstrBot管理员，使用 / 前缀）====\n"
            "/鲲开 —— 开启养鲲游戏\n"
            "/鲲关 —— 关闭养鲲游戏\n"
            "/小游戏开 —— 开启小游戏\n"
            "/小游戏关 —— 关闭小游戏\n"
            "/数据清除 —— 清除本群数据\n"
            "/刷新BOSS —— 刷新BOSS\n"
            "/强制下架 —— 强制下架拍卖\n"
            "----修改指令----\n"
            "/修改 QQ号 项目 数值\n"
            "项目: 鲲/体重/属性/节操/蛋/神器/幻化丹/鸡汤/复活药/运势\n"
            "例: /修改 12345 体重 +100"
        )

    def _command_menu(self, group: dict) -> str:
        p = self.config.get("command_prefix", "*")
        return (
            "====养鲲游戏====\n"
            "开局一只鲲，进化全靠吞！\n"
            f"各位饲鲲主快来一试身手吧！\n\n"
            "====用户指令====\n"
            f"{p}签到 - 每日签到\n"
            f"{p}孵化 - 获取一只鲲\n"
            f"{p}买蛋【数量】- 购买蛋\n"
            f"{p}砸蛋【数量】- 砸蛋(可私聊)\n"
            f"{p}喂食【数量】- 用蛋喂鲲\n"
            f"{p}磨炼【数值】- 磨炼鲲(可私聊)\n"
            f"{p}幻化 - 幻化获得属性(可私聊)\n"
            f"{p}吞噬【@QQ】- 吞噬对方\n"
            f"{p}攻击【@QQ】- 攻击对方\n"
            f"{p}强袭【@QQ】- 强袭对方\n"
            f"{p}扔蛋【@QQ】- 扔对方蛋\n"
            f"{p}喝鸡汤【数量】- 补充节操\n"
            f"{p}今日运势 - 查看运势\n"
            f"{p}当前游戏 - 查看可玩游戏\n"
            f"{p}查阅属性 - 查看鲲属性\n"
            f"{p}渡劫 - 鲲渡劫\n"
            f"{p}放生 - 放生鲲\n"
            f"{p}复活 - 复活鲲\n"
            f"{p}拍卖行 - 查看拍卖\n"
            f"{p}查询BOSS - 看BOSS\n"
            f"{p}攻击BOSS/{p}吞噬BOSS/{p}强袭BOSS\n"
            f"{p}阵亡名单 - 查看阵亡者\n"
            f"{p}命令菜单 - 显示本菜单\n"
            f"\n管理员指令请发送 {p}查看群主指令"
        )

    def _admin_edit(self, cmd: str, args: str, uid: str, name: str, group: dict) -> str:
        """管理编辑命令: *QQ号/项目/数值 或 *QQ号/项目/+数值 或 *QQ号/项目/-数值"""
        parts = cmd.split("/", 2)
        if len(parts) != 3:
            return None

        target_qq, project, value_str = (
            parts[0].strip(),
            parts[1].strip(),
            parts[2].strip(),
        )

        if not target_qq.isdigit():
            return None

        target = self.data.get_player(group["gid"], target_qq)
        valid_projects = {
            "鲲": "kun",
            "体重": "weight",
            "属性": "attribute",
            "节操": "jie_cao",
            "蛋": "eggs",
            "神器": "divine_weapon",
            "幻化丹": "phantom_pills",
            "鸡汤": "chicken_soup",
            "复活药": "resurrection_pills",
            "运势": "luck",
        }

        if project not in valid_projects:
            return (
                "====管理员修改指令====\n"
                "格式: 【QQ号】/【项目】/【数值】\n"
                "可选项目: 鲲/体重/属性/节操/蛋/神器/幻化丹/鸡汤/复活药/运势\n"
                "数值正为加负为减\n"
                "例: 12345/属性/妒  = 改为妒属性\n"
                "例: 13579/蛋/-10 = 减10颗蛋\n"
                "例: 24680/节操/+1 = 节操+1"
            )

        key = valid_projects[project]

        if key == "attribute":
            # 直接设置属性
            if value_str not in KUN_ATTRIBUTES:
                return f"无效的属性: {value_str}\n可选: {list(KUN_ATTRIBUTES.keys())}"
            if not target.get("kun"):
                return f"玩家{target_qq}还没有鲲！"
            target["kun"]["attribute"] = value_str
            self.data.save()
            return f"已将玩家{target_qq}的鲲属性改为[{value_str}]"

        elif key == "kun":
            # 设置鲲的存在
            if value_str.lower() in ("无", "无", "删除", "remove", "null"):
                target["kun"] = None
                self.data.save()
                return f"已删除玩家{target_qq}的鲲"
            else:
                return "用法: *QQ号/鲲/无  (删除鲲)"

        elif key == "weight":
            if not target.get("kun"):
                return f"玩家{target_qq}还没有鲲！"
            op = value_str[0] if value_str else ""
            if op in "+-":
                val = float(value_str[1:])
                target["kun"]["weight"] += val if op == "+" else -val
                target["kun"]["weight"] = max(1, target["kun"]["weight"])
            else:
                target["kun"]["weight"] = float(value_str)
            self.data.save()
            return f"玩家{target_qq}鲲体重→{format_weight(target['kun']['weight'])}"

        else:
            # 数值型
            op = value_str[0] if value_str else ""
            if op in "+-":
                val = int(value_str[1:])
                target[key] = max(0, target[key] + (val if op == "+" else -val))
            else:
                target[key] = max(0, int(value_str))
            self.data.save()
            return f"玩家{target_qq} {project}→{target[key]}"

    # ==================== 核心游戏逻辑 ====================

    def _sign_in(self, player: dict, name: str) -> str:
        if player["signed_today"]:
            return f"@{name} 请勿重复签到！获得惩罚：节操-10\n剩余节操 {player['jie_cao'] - 10}"
        player["signed_today"] = True
        player["jie_cao"] += 10
        player["today_train"] = 0  # 磨炼次数恢复到30
        player["luck"] = min(100, player["luck"] + 5)
        # 随机奖励
        bonus_eggs = random.randint(1, 3)
        player["eggs"] += bonus_eggs
        self.data.save()
        return (
            f"@{name} 签到成功！\n"
            f"获得奖励：节操+10，蛋+{bonus_eggs}\n"
            f"磨炼次数回复至30\n"
            f"运势+5 (当前{player['luck']})\n"
            f"当前节操：{player['jie_cao']}，蛋：{player['eggs']}"
        )

    def _current_game(self, group: dict) -> str:
        if not group.get("game_enabled", True):
            return "小游戏未开启！"

        mg = group.get("mini_game")
        if mg:
            remaining = mg["max_slots"] - mg["slots_used"]
            return (
                f"====当前小游戏====\n"
                f"进行中：{mg['type']}\n"
                f"问题：{mg.get('question', '敲击群主')}\n"
                f"剩余名额：{remaining}\n"
                f"回复*=答案参与"
            )

        champion = group.get("duel_champion")
        if champion:
            return (
                f"====当前小游戏====\n"
                f"单挑群主进行中！当前群主：{champion['name']}（{champion.get('consecutive', 0)}连胜）\n"
                f"回复【{self.prefix}单挑群主】开始挑战\n"
                f"直到有人打败群主才可结束！"
            )

        return (
            "====当前小游戏====\n"
            "【奥数比赛】名额5 - 回复*=数值抢答\n"
            "【数星星】名额2 - 回复*=数值抢答\n"
            "【群殴群主】名额5 - 回复*抽群主一个大嘴巴\n"
            "【抄作业】名额5 - 回复*=答案\n"
            "【单挑群主】名额1 - 回复*单挑群主\n"
            "节操至少为1才能参与游戏"
        )

    def _check_attr(self, player: dict, group: dict, name: str) -> str:
        kun = player.get("kun")
        if not kun:
            return f"@{name} 你还没有鲲！\n发送【{self.prefix}孵化】获取鲲"
        attr = KUN_ATTRIBUTES.get(kun["attribute"], "未知")
        alive = "存活" if kun.get("alive", True) else "已阵亡"
        recovery_msg = self._check_kun_recovery(kun)
        lines = [
            f"@{name} 的鲲：{kun.get('name', '无名鲲')}",
            f"体重：{format_weight(kun['weight'])}",
            f"属性：{kun['attribute']} - {attr}",
            f"状态：{alive}",
        ]
        if recovery_msg:
            lines.append(recovery_msg.strip())
        lines += [
            f"@{name} 的鲲：",
            f"体重：{format_weight(kun['weight'])}",
            f"属性：{kun['attribute']} - {attr}",
            f"状态：{alive}",
            f"节操：{player['jie_cao']}",
            f"蛋：{player['eggs']}",
            f"神器：{player['divine_weapon']}",
            f"幻化丹：{player['phantom_pills']}",
            f"鸡汤：{player['chicken_soup']}",
            f"复活药：{player['resurrection_pills']}",
            f"运势：{player['luck']}",
        ]
        return "\n".join(lines)

    def _check_luck(self, player: dict, name: str) -> str:
        return f"@{name} 今日运势：{player['luck']}\n砸蛋出道具概率={player['luck'] / 200 * 100:.1f}%"

    def _death_list(self, group: dict) -> str:
        dlist = group.get("death_list", [])
        if not dlist:
            return "阵亡名单：暂无阵亡者"
        lines = ["阵亡名单："]
        for entry in dlist[-20:]:
            lines.append(f"  {entry.get('qq', '?')} - {entry.get('reason', '未知')}")
        lines.append("缅怀以上各位勇士！")
        return "\n".join(lines)

    # ---- 孵化 ----
    def _hatch(self, player: dict, group: dict, name: str) -> str:
        if player.get("kun") and player["kun"].get("alive", True):
            return f"@{name} 你已经拥有一只鲲了，开始吞吧！"
        if player["eggs"] <= 0:
            return f"@{name} 你并没有蛋！\n通过每日【{self.prefix}签到】或【{self.prefix}买蛋】可以获取蛋"

        player["eggs"] -= 1
        player["today_train"] = 0  # 孵化也重置磨炼次数

        # 确定属性: 0.7% 悲, 其余随机
        roll = random.random()
        if roll <= self.data._cfg.get("hatch_misfortune_rate", 0.007):
            attr = "悲"
            # 计算榜一体重
            bp = self._get_top_weight(group)
            weight = bp + 1000
        else:
            attrs = [
                "无",
                "魑",
                "魅",
                "魍",
                "魉",
                "淫",
                "馋",
                "贪",
                "惰",
                "怒",
                "妒",
                "傲",
            ]
            attr = random.choice(attrs)
            weight = random.randint(DEFAULT_WEIGHT_MIN, DEFAULT_WEIGHT_MAX)

        player["kun"] = {
            "name": random.choice(KUN_NAMES),
            "weight": weight,
            "attribute": attr,
            "alive": True,
            "killer": None,
        }
        self.data.save()

        attr_desc = KUN_ATTRIBUTES.get(attr, "未知")
        return f"@{name} 恭喜你获得一只{player['kun']['name']}\n体重：{format_weight(weight)}\n{attr_desc}"

    # ---- 买蛋 ----
    def _buy_eggs(self, player: dict, name: str, args: str) -> str:
        if player["jie_cao"] <= 0:
            return f"@{name} 你已经节操丧尽！不能买蛋！\n节操可以通过每日【{self.prefix}签到】或【{self.prefix}喝鸡汤】获取"

        try:
            count = int(args) if args else 1
        except ValueError:
            return "请输入正确数量！"

        cost = count * self.data._cfg.get("egg_price", 5)
        if player["jie_cao"] < cost:
            return f"@{name} 节操不足！需要{cost}节操，当前节操{player['jie_cao']}"

        player["jie_cao"] -= cost
        player["eggs"] += count
        self.data.save()

        quips = [
            "节操去渡劫，运气不好鲲永别！",
            "你不如来买蛋，节操换蛋真划算！",
            "买一个孵只鲲，要是太轻会被吞！",
            "你不如买一对，一个孵化一个喂！",
            "要是喂完还被吞，这个仇人记在心！",
            "回头再来买一斤，砸出神器袭他鲲!",
            "不行还要买一打，直接往他头上砸！",
            "瞧一瞧，看一看，5节操一颗蛋！",
            "走一走，转一转，节操不够靠边站！",
        ]
        quip = random.choice(quips)
        return f"@{name} 购买了{count}颗蛋！消耗{cost}节操。\n{quip}\n剩余节操：{player['jie_cao']}，现有蛋：{player['eggs']}"

    # ---- 砸蛋 ----
    def _smash_eggs(self, player: dict, name: str, args: str) -> str:
        try:
            count = int(args) if args else 1
        except ValueError:
            return "请输入正确数量！"

        if count > EGG_SMASH_LIMIT:
            return "最多同时砸100颗蛋！"

        if player["eggs"] < count:
            return f"@{name} 你没有足够的蛋！现有{player['eggs']}颗"

        player["eggs"] -= count

        drop_rate = player["luck"] / 200  # 每颗蛋出货概率

        weapons = 0
        pills = 0
        soups = 0
        revive = 0

        for _ in range(count):
            if random.random() < drop_rate:
                r = random.random()
                if r < 0.15:  # 神器
                    weapons += 1
                elif r < 0.35:  # 幻化丹
                    pills += 1
                elif r < 0.65:  # 鸡汤
                    soups += 1
                else:  # 复活药
                    revive += 1

        player["divine_weapon"] += weapons
        player["phantom_pills"] += pills
        player["chicken_soup"] += soups
        player["resurrection_pills"] += revive

        self.data.save()

        msg_parts = [f"@{name} 狠心砸开了{count}颗蛋！"]
        if weapons > 0:
            msg_parts.append(f"恭喜你砸出了上古神器+夨￥宀♂牮√ x{weapons}！")
        if pills > 0:
            msg_parts.append(f"恭喜你砸出了幻化丹 x{pills}！")
        if soups > 0:
            msg_parts.append(f"恭喜你砸出了一碗鸡汤 x{soups}！")
        if revive > 0:
            msg_parts.append(f"恭喜你砸出了复活药 x{revive}！")

        total = weapons + pills + soups + revive
        if total == 0:
            msg_parts.append(
                "里面并没有奖品，只有尚未成型的鲲宝宝...悔恨的泪水止不住的流。。。"
            )
            player["luck"] = max(0, player["luck"] - 2)
        else:
            player["luck"] = min(100, player["luck"] + total)

        msg_parts.append(
            f"\n现有神器：{player['divine_weapon']}，幻化丹：{player['phantom_pills']}，鸡汤：{player['chicken_soup']}，复活药：{player['resurrection_pills']}"
        )
        return "\n".join(msg_parts)

    # ---- 喂食 ----
    def _feed(self, player: dict, name: str, args: str, group: dict) -> str:
        kun = player.get("kun")
        if not kun or not kun.get("alive", True):
            return f"@{name} 你并没有鲲！\n发送【{self.prefix}孵化】获取鲲"

        if group.get("auction") and group["auction"]["seller"] == player["qq"]:
            return f"@{name} 正在拍卖，无法喂食！\n当前竞价：{group['auction'].get('current_bid', '无')}"

        try:
            count = int(args) if args else 1
        except ValueError:
            return "请输入正确数量！"

        if count > 100:
            return "最多同时喂食100颗蛋！"

        if player["eggs"] < count:
            return f"@{name} 你没有足够的蛋！现有{player['eggs']}颗"

        player["eggs"] -= count
        weight_gain = count * random.randint(5, 15)
        kun["weight"] += weight_gain

        # 馋属性体重超1000暴死
        if kun["attribute"] == "馋" and kun["weight"] > 1000:
            kun["alive"] = False
            group.setdefault("death_list", []).append(
                {"qq": player["qq"], "reason": "馋属性暴食而死"}
            )
            self.data.save()
            return f"@{name} 因暴食而死！\n人为鸟死，鲲为食亡！"

        self.data.save()
        return f"@{name} 喂食了{count}颗蛋！体重增加了{format_weight(weight_gain)}\n现体重为{format_weight(kun['weight'])}"

    # ---- 磨炼 ----
    def _train(self, player: dict, name: str, args: str, group: dict) -> str:
        kun = player.get("kun")
        if not kun or not kun.get("alive", True):
            return f"@{name} 你还没有鲲！\n发送【{self.prefix}孵化】获取鲲"

        if group.get("auction") and group["auction"]["seller"] == player["qq"]:
            return f"@{name} 正在拍卖，无法磨炼！"

        try:
            value = float(args)
        except ValueError:
            return "请输入正确数值！"

        if value <= 0:
            return "磨炼数值必须大于0！"

        if value > kun["weight"]:
            return "不行不行，这么练会死的！\n磨炼数值不能大于体重！"

        max_train = self.data._cfg.get("train_daily_max", 30)
        if player["today_train"] >= max_train:
            return f"今日磨炼次数已用完！\n每日【{self.prefix}签到】或【{self.prefix}孵化】可将磨炼次数回复至30"

        # 检查节操
        need_jc = 2
        if player["jie_cao"] <= 0:
            return f"@{name} 你已节操丧尽！无法磨炼！"

        if player["jie_cao"] < need_jc:
            return f"@{name} 节操不足{need_jc}！当前节操{player['jie_cao']}"

        # 贪属性70%不耗节操
        if kun["attribute"] == "贪" and random.random() < 0.7:
            need_jc = 0

        player["jie_cao"] -= need_jc
        player["today_train"] += 1

        # 成功率 = 磨炼数值/总体重*100%
        success_rate = value / kun["weight"]
        success = random.random() < success_rate

        if success:
            kun["weight"] -= value
            self.data.save()
            return f"@{name} 磨炼成功！【{kun['attribute']}】体重减少{format_weight(value)}，剩余体重{format_weight(kun['weight'])}"
        else:
            kun["weight"] += kun["weight"] - value  # 总体重 - 磨炼数值 = 增加
            self.data.save()
            # 检查馋属性暴死
            if kun["attribute"] == "馋" and kun["weight"] > 1000:
                kun["alive"] = False
                group.setdefault("death_list", []).append(
                    {"qq": player["qq"], "reason": "馋属性磨炼暴食而死"}
                )
                return f"@{name} 因暴食而死！人为鸟死，鲲为食亡！"
            return f"@{name} 磨炼失败！【{kun['attribute']}】体重增加{format_weight(value)}，现体重{format_weight(kun['weight'])}"

    # ---- 幻化 ----
    def _evolve(self, player: dict, name: str, group: dict) -> str:
        kun = player.get("kun")
        if not kun or not kun.get("alive", True):
            return f"@{name} 你还没有鲲！\n发送【{self.prefix}孵化】获取鲲"

        if group.get("auction") and group["auction"]["seller"] == player["qq"]:
            return f"@{name} 正在拍卖，无法幻化！\n当前竞价：{group['auction'].get('current_bid', '无')}"

        if kun["attribute"] == "悲":
            return "悲属性的鲲无法幻化！"

        if player["phantom_pills"] <= 0:
            return f"@{name} 你没有幻化丹！\n【{self.prefix}砸蛋】可以获取幻化丹"

        # 幻化成本：10kg体重 (馋不消耗)
        cost_weight = 0 if kun["attribute"] == "馋" else 10

        player["phantom_pills"] -= 1

        # 随机新属性（无属性不可获得悲，幻化无法获得悲）
        all_attrs = [
            "无",
            "魑",
            "魅",
            "魍",
            "魉",
            "淫",
            "馋",
            "贪",
            "惰",
            "怒",
            "妒",
            "傲",
        ]
        # 去掉当前属性
        available = [a for a in all_attrs if a != kun["attribute"]]
        new_attr = random.choice(available)

        # 成功率: 权重相关, 简化: 60% 成功率
        if random.random() < 0.6:
            old_attr = kun["attribute"]
            kun["attribute"] = new_attr
            if cost_weight > 0:
                kun["weight"] = max(1, kun["weight"] - cost_weight)
            self.data.save()
            return (
                f"@{name} 幻化成功！\n"
                f"【{old_attr}】→【{new_attr}】\n"
                f"{KUN_ATTRIBUTES.get(new_attr, '')}\n"
                f"{'消耗' + format_weight(cost_weight) + '体重' if cost_weight > 0 else '未消耗体重'}\n"
                f"剩余幻化丹：{player['phantom_pills']}"
            )
        else:
            if new_attr == kun["attribute"]:
                # 属性不变，返还
                player["phantom_pills"] += 1
                self.data.save()
                return f"@{name} 属性未发生变化，返还幻化丹\n剩余幻化丹：{player['phantom_pills']}"
            else:
                self.data.save()
                return (
                    f"@{name} 幻化失败！就这么没了！\n"
                    f"再接再厉吧\n"
                    f"剩余幻化丹：{player['phantom_pills']}"
                )

    # ---- 吞噬 ----
    def _devour(
        self, player: dict, uid: str, name: str, args: str, gid: str, group: dict
    ) -> str:
        return self._pvp_action(player, uid, name, args, gid, group, "devour")

    def _attack(
        self, player: dict, uid: str, name: str, args: str, gid: str, group: dict
    ) -> str:
        return self._pvp_action(player, uid, name, args, gid, group, "attack")

    def _assault(
        self, player: dict, uid: str, name: str, args: str, gid: str, group: dict
    ) -> str:
        return self._pvp_action(player, uid, name, args, gid, group, "assault")

    def _throw_egg(
        self, player: dict, uid: str, name: str, args: str, group: dict
    ) -> str:
        return self._pvp_action(player, uid, name, args, "", group, "throw_egg")

    def _pvp_action(
        self,
        player: dict,
        uid: str,
        name: str,
        args: str,
        gid: str,
        group: dict,
        action: str,
    ) -> str:
        kun = player.get("kun")
        if not kun or not kun.get("alive", True):
            return f"@{name} 你还没有鲲！\n发送【{self.prefix}孵化】获取鲲"

        # 拍卖检查
        if group.get("auction"):
            auc = group["auction"]
            if auc["seller"] == uid:
                return f"@{name} 正在拍卖，无法{action}！\n当前竞价：{auc.get('current_bid', '无')}"

        # 获取目标
        target_id = parse_qq_id(args)
        if not target_id:
            return f"@{name} 请指定目标！格式：*{action} @QQ 或 *{action} QQ号"

        if target_id == uid:
            if action == "throw_egg":
                player["luck"] = max(0, player["luck"] - 1)
                self.data.save()
                return f"@{name} 向自己头上扔了一颗蛋！运势-1\n（大家快看，这有个大傻[消音]！）"
            return f"@{name} 不能对自己进行操作！"

        target = self.data.get_player(gid, target_id)
        t_kun = target.get("kun")

        if action == "throw_egg":
            return self._do_throw_egg(player, target, name, target_id, group)

        if not t_kun or not t_kun.get("alive", True):
            return f"@{name} 对方还没有鲲，快邀请他一起♂玩吧"

        # 拍卖检查对方
        if group.get("auction") and group["auction"]["seller"] == target_id:
            return f"@{name} 对方的鲲正在拍卖，无法{action}！"

        if action == "devour":
            return self._do_devour(player, target, name, target_id, gid, group)
        elif action == "attack":
            return self._do_attack(player, target, name, target_id, gid, group)
        elif action == "assault":
            return self._do_assault(player, target, name, target_id, gid, group)
        return "未知操作"

    def _get_effective_devour_rate(self, attacker: dict, defender: dict) -> float:
        """计算吞噬成功率"""
        a_w = attacker["kun"]["weight"]
        d_w = defender["kun"]["weight"]
        d_attr = defender["kun"]["attribute"]

        base = 0.5  # 50%基础概率
        # 体重因素
        if d_w > a_w * 2:
            base -= 0.3
        elif d_w > a_w:
            base -= 0.1
        elif a_w > d_w * 2:
            base += 0.3
        elif a_w > d_w:
            base += 0.1

        # 惰属性极难吞噬
        if d_attr == "惰":
            base = 0.05
        # 怒属性容易吞噬
        if attacker["kun"]["attribute"] == "怒":
            base += 0.2
        # 妒属性: 比其体重大的无法吞噬
        if d_attr == "妒" and d_w > a_w:
            return 0

        return max(0, min(1, base))

    def _do_devour(
        self,
        player: dict,
        target: dict,
        name: str,
        target_id: str,
        gid: str,
        group: dict,
    ) -> str:
        a_kun = player["kun"]
        d_kun = target["kun"]

        # 魅免疫吞噬
        if d_kun["attribute"] == "魅":
            return f"@{name} 魅免疫吞噬！吞噬失败！"

        # 馋不能吞噬(虽然没明确，但馋不能攻击)
        if a_kun["attribute"] == "馋":
            return f"@{name} 馋属性无法发起吞噬！"

        # 太小了
        if a_kun["weight"] < d_kun["weight"] * 0.3:
            return f"@{name} 你的鲲太小了！养肥了再吞吧"

        # 致命一击 (怒属性25%)
        critical = False
        if a_kun["attribute"] == "怒" and random.random() < 0.25:
            critical = True

        # 成功率
        rate = self._get_effective_devour_rate(player, target)
        success = random.random() < rate

        if success:
            dmg = a_kun["weight"] * (
                random.uniform(0.3, 0.6) if not critical else CRITICAL_MULTIPLIER
            )
            d_kun["weight"] -= dmg

            if d_kun["weight"] <= 0 or critical:
                d_kun["alive"] = False
                d_kun["killer"] = player["qq"]
                group.setdefault("death_list", []).append(
                    {"qq": target_id, "reason": f"被{name}吞噬"}
                )
                a_kun["weight"] += d_kun["weight"] if d_kun["weight"] > 0 else 0

                # 淫属性: 75%对方狗带 -> 已触发, 对方已死, 这里处理吞噬者也被反噬
                if d_kun["attribute"] == "淫" and random.random() < 0.75:
                    a_kun["alive"] = False
                    group.setdefault("death_list", []).append(
                        {"qq": player["qq"], "reason": "被淫属性反噬"}
                    )
                    self.data.save()
                    return (
                        f"@{name} 吞噬了{target_id}的鲲，但被淫属性反噬！双方同归于尽！"
                    )

                self.data.save()
                return (
                    f"@{name} 吞噬了{target_id}的鲲！\n"
                    + ("发动了致命一击！\n" if critical else "")
                    + f"现体重：{format_weight(a_kun['weight'])}"
                )

            a_kun["weight"] += dmg

            # 馋属性暴死检查
            if a_kun["attribute"] == "馋" and a_kun["weight"] > 1000:
                a_kun["alive"] = False
                group.setdefault("death_list", []).append(
                    {"qq": player["qq"], "reason": "馋属性暴食而死"}
                )
                self.data.save()
                return f"@{name} 吞噬成功但因暴食而死！\n友情提示：多行不义必自毙！"

            # 淫属性反噬
            if d_kun["attribute"] == "淫" and random.random() < 0.75:
                a_kun["alive"] = False
                group.setdefault("death_list", []).append(
                    {"qq": player["qq"], "reason": "被淫属性反噬"}
                )
                self.data.save()
                return f"@{name} 吞噬成功但{target_id}的淫属性反噬了你！你狗带了！"

            # 贪属性30%得蛋
            egg_msg = ""
            if a_kun["attribute"] == "贪" and random.random() < 0.3:
                player["eggs"] += 1
                egg_msg = "\n下了一颗蛋！人生处处是惊喜！"

            self.data.save()
            return (
                f"@{name} 发起吞噬！\n"
                + (f"吞噬成功！体重增加{format_weight(dmg)}\n")
                + f"现体重：{format_weight(a_kun['weight'])}\n"
                + f"对方{target_id}体重减少{format_weight(dmg)}，剩余{format_weight(d_kun['weight'])}"
                + egg_msg
            )
        else:
            # 失败惩罚: 损失体重
            loss = a_kun["weight"] * 0.2
            if a_kun["attribute"] != "馋":
                a_kun["weight"] -= loss

            if a_kun["weight"] <= 0:
                a_kun["alive"] = False
                group.setdefault("death_list", []).append(
                    {"qq": player["qq"], "reason": "吞噬失败反噬而死"}
                )
                self.data.save()
                return f"@{name} 吞噬失败！为食而死！\n吞噬要量力而为啊！"

            self.data.save()
            return f"@{name} 吞噬失败！体重减少{format_weight(loss)}\n剩余体重{format_weight(a_kun['weight'])}"

    def _do_attack(
        self,
        player: dict,
        target: dict,
        name: str,
        target_id: str,
        gid: str,
        group: dict,
    ) -> str:
        a_kun = player["kun"]
        d_kun = target["kun"]

        # 魍免疫攻击
        if d_kun["attribute"] == "魍":
            return f"@{name} 魍免疫攻击！攻击无效！"

        # 馋不能攻击
        if a_kun["attribute"] == "馋":
            return "馋属性鲲无法发起攻击！"

        # 太小了
        if a_kun["weight"] < d_kun["weight"] * 0.3:
            return f"@{name} 太小了！以大欺小，胜之不武！放他一马吧！"

        # 妒
        if d_kun["attribute"] == "妒" and d_kun["weight"] > a_kun["weight"]:
            return f"@{name} 妒属性的鲲比你重，无法攻击！"

        # 致命一击
        critical = a_kun["attribute"] == "怒" and random.random() < 0.25

        # 攻击伤害计算
        dmg = (
            a_kun["weight"]
            * random.uniform(0.1, 0.3)
            * (CRITICAL_MULTIPLIER if critical else 1)
        )
        d_kun["weight"] -= dmg

        if d_kun["weight"] <= 0:
            d_kun["alive"] = False
            d_kun["killer"] = player["qq"]
            group.setdefault("death_list", []).append(
                {"qq": target_id, "reason": f"被{name}攻击致死"}
            )
            self.data.save()
            return (
                f"@{name} 发起攻击！\n"
                + (f"发动了致命一击！\n" if critical else "")
                + f"干死了{target_id}的鲲！"
            )

        # 淫属性25%恢复大量体重
        if a_kun["attribute"] == "淫" and random.random() < 0.25:
            heal = a_kun["weight"] * 0.5
            a_kun["weight"] += heal
            self.data.save()
            return (
                f"@{name} 发起攻击！\n{target_id}体重减少{format_weight(dmg)}\n"
                f"淫属性触发大恢复术！体重+{format_weight(heal)}"
            )

        # 贪得蛋
        egg_msg = ""
        if a_kun["attribute"] == "贪" and random.random() < 0.3:
            player["eggs"] += 1
            egg_msg = "\n下了一颗蛋！"

        self.data.save()
        return (
            f"@{name} 发起攻击！\n{target_id}体重减少{format_weight(dmg)}\n"
            f"剩余体重{format_weight(d_kun['weight'])}" + egg_msg
        )

    def _do_assault(
        self,
        player: dict,
        target: dict,
        name: str,
        target_id: str,
        gid: str,
        group: dict,
    ) -> str:
        if player["divine_weapon"] <= 0:
            return f"@{name} 你没有神器+夨￥宀♂牮√，无法发动强袭\n【{self.prefix}砸蛋】可获得+夨￥宀♂牮√"

        # 魑免疫强袭
        if target["kun"]["attribute"] == "魑":
            return f"@{name} 魑免疫强袭！强袭无效！"

        player["divine_weapon"] -= 1
        player["jie_cao"] = max(0, player["jie_cao"] - 2)

        # 随机结果
        if random.random() < 0.7:  # 70%成功率
            dmg = random.randint(50, 300)
            target["kun"]["weight"] -= dmg

            if target["kun"]["weight"] <= 0:
                target["kun"]["alive"] = False
                target["kun"]["killer"] = player["qq"]
                group.setdefault("death_list", []).append(
                    {"qq": target_id, "reason": f"被{name}强袭致死"}
                )
                self.data.save()
                return (
                    f"@{name} 悄悄向{target_id}投掷了+夨￥宀♂牮√！\n"
                    f"打死了{target_id}的鲲！\n"
                    f"神器余量：{player['divine_weapon']}"
                )

            self.data.save()
            return (
                f"@{name} 悄悄向{target_id}投掷了+夨￥宀♂牮√！\n"
                f"对方受伤：{format_weight(dmg)}\n"
                f"强袭成功！节操-2\n神器余量：{player['divine_weapon']}"
            )
        else:
            self.data.save()
            return (
                f"@{name} 悄悄向{target_id}投掷了+夨￥宀♂牮√！\n"
                f"蛇皮走位，躲开了！\n"
                f"强袭失败！节操-2\n神器余量：{player['divine_weapon']}"
            )

    def _do_throw_egg(
        self, player: dict, target: dict, name: str, target_id: str, group: dict
    ) -> str:
        if player["eggs"] <= 0:
            return f"@{name} 你没有蛋！"

        player["eggs"] -= 1

        # 50%命中
        if random.random() < 0.5:
            target["luck"] = max(0, target["luck"] - 2)
            self.data.save()
            return f"@{name} 向{target_id}扔了一颗蛋！命中！\n对方运势-2"
        else:
            self.data.save()
            return f"@{name} 向{target_id}扔了一颗蛋！\n对方闪转腾挪，躲开了！"

    # ---- BOSS ----
    def _query_boss(self, group: dict) -> str:
        boss = group.get("boss")
        if not boss:
            return f"今日BOSS尚未刷新！\n发送【{self.prefix}刷新BOSS】刷新\n（或等待每日0点自动刷新）"

        if not boss.get("alive", True):
            return (
                f"今日BOSS已经被击杀！\n"
                f"击杀者：{boss.get('killer', '?')}\n"
                f"请等待每日0点刷新或联系群主！"
            )

        lines = [
            f"====今日BOSS====",
            f"名称：{boss.get('name', '未知')}",
            f"体重：{format_weight(boss['weight'])}",
            f"属性：{', '.join(boss.get('attributes', []))}",
        ]

        dmg_rank = boss.get("damage_rank", {})
        if dmg_rank:
            lines.append("----输出排行----")
            sorted_dmg = sorted(dmg_rank.items(), key=lambda x: x[1], reverse=True)
            for i, (qq, dmg_val) in enumerate(sorted_dmg[:5], 1):
                lines.append(f"  {i}. {qq}: {format_weight(dmg_val)}")

        return "\n".join(lines)

    def _refresh_boss(self, group: dict) -> str:
        group["boss"] = self._generate_boss()
        self.data.save()
        return f"今日BOSS已刷新！\n发送【{self.prefix}查询BOSS】查看详情"

    def _generate_boss(self) -> dict:
        attrs_combo = [
            ["魅", "魍"],
            ["魑", "惰"],
            ["怒", "傲"],
            ["魅", "魉"],
            ["淫"],
            ["妒"],
        ]
        return {
            "name": random.choice(BOSS_NAMES),
            "weight": random.randint(2000, 5000),
            "attributes": random.choice(attrs_combo),
            "alive": True,
            "killer": None,
            "damage_rank": {},
            "anti_assault": [],
            "anti_devour": [],
            "anti_attack": [],
        }

    def _attack_boss(
        self, player: dict, uid: str, name: str, group: dict, gid: str
    ) -> str:
        return self._boss_action(player, uid, name, group, "attack", gid)

    def _devour_boss(
        self, player: dict, uid: str, name: str, group: dict, gid: str
    ) -> str:
        return self._boss_action(player, uid, name, group, "devour", gid)

    def _assault_boss(
        self, player: dict, uid: str, name: str, group: dict, gid: str
    ) -> str:
        return self._boss_action(player, uid, name, group, "assault", gid)

    def _boss_action(
        self,
        player: dict,
        uid: str,
        name: str,
        group: dict,
        action: str,
        gid: str,
    ) -> str:
        boss = group.get("boss")
        if not boss:
            return f"今日BOSS尚未刷新！\n发送【{self.prefix}刷新BOSS】刷新"

        if not boss.get("alive", True):
            return (
                f"今日BOSS已经被击杀！\n"
                f"击杀者：{boss.get('killer', '?')}\n"
                f"请等待每日0点刷新或联系群主！"
            )

        kun = player.get("kun")
        if not kun or not kun.get("alive", True):
            return f"@{name} 你还没有鲲！\n发送【{self.prefix}孵化】获取鲲"

        # 检查免疫
        boss_attrs = boss.get("attributes", [])
        if action == "assault" and "魑" in boss_attrs:
            return f"BOSS免疫强袭！"
        if action == "devour" and "魅" in boss_attrs:
            return f"BOSS免疫吞噬！"
        if action == "attack" and "魍" in boss_attrs:
            return f"BOSS免疫攻击！"

        # 计算伤害
        base_dmg = kun["weight"] * random.uniform(0.05, 0.2)
        dmg = base_dmg

        # 傲无视属性
        if kun["attribute"] == "傲":
            dmg *= 1.5
        if kun["attribute"] == "怒" and random.random() < 0.25:
            dmg *= CRITICAL_MULTIPLIER

        boss["weight"] -= dmg
        boss.setdefault("damage_rank", {})
        boss["damage_rank"][uid] = boss["damage_rank"].get(uid, 0) + dmg

        # 反伤
        reflect = boss["weight"] * 0.1
        kun["weight"] -= min(reflect, kun["weight"] * 0.3)

        # 检查BOSS是否被击杀
        if boss["weight"] <= 0:
            boss["alive"] = False
            boss["killer"] = uid
            player["eggs"] += 20
            player["jie_cao"] += 100

            # 输出排行前5每人300节操
            dmg_rank = boss.get("damage_rank", {})
            sorted_dmg = sorted(dmg_rank.items(), key=lambda x: x[1], reverse=True)[:5]
            reward_lines = []
            for r_uid, r_dmg in sorted_dmg:
                if r_uid != uid:
                    rp = self.data.get_player(gid, r_uid)
                    rp["jie_cao"] += 300

            self.data.save()
            return (
                f"@{name} 成功击杀了BOSS {boss['name']}！\n"
                f"获得击杀奖励：蛋*20，节操*100\n"
                f"输出排行前五名每人获得300节操奖励！"
            )

        # 检查鲲是否阵亡
        if kun["weight"] <= 0:
            kun["alive"] = False
            kun["killer"] = "BOSS"
            group.setdefault("death_list", []).append(
                {"qq": uid, "reason": "讨伐BOSS阵亡"}
            )
            self.data.save()
            return (
                f"@{name} 对BOSS造成了{format_weight(dmg)}伤害！\n"
                f"但被BOSS反击致死！阵亡名单已记录。"
            )

        self.data.save()
        return (
            f"@{name} 对BOSS造成了{format_weight(dmg)}伤害！\n"
            f"BOSS剩余体重：{format_weight(boss['weight'])}\n"
            f"你的鲲受到{format_weight(min(reflect, kun['weight'] * 0.3))}反伤"
        )

    def _get_top_weight(self, group: dict) -> int:
        """获取群里现有鲲的最大体重"""
        max_w = 0
        for pid, p in group.get("players", {}).items():
            kun = p.get("kun")
            if kun and kun.get("alive", True):
                if kun["weight"] > max_w:
                    max_w = kun["weight"]
        return max_w if max_w > 0 else 1000

    # ---- 魉恢复 ----
    def _check_kun_recovery(self, kun: dict | None) -> str:
        """魉: 体重低于666千克时恢复至1000千克"""
        if not kun or not kun.get("alive", True):
            return ""
        if kun["attribute"] == "魉" and kun["weight"] < 666:
            kun["weight"] = 1000
            return "\n魉属性触发大恢复术！体重恢复至1000千克！"
        return ""

    # ---- 渡劫 ----
    def _tribulation(self, player: dict, name: str, group: dict) -> str:
        kun = player.get("kun")
        if not kun or not kun.get("alive", True):
            return f"@{name} 你并没有鲲！\n发送【{self.prefix}孵化】获取鲲"

        if group.get("auction") and group["auction"]["seller"] == player["qq"]:
            return f"@{name} 正在拍卖，无法渡劫！\n当前竞价：{group['auction'].get('current_bid', '无')}"

        if kun["attribute"] == "无":
            return f"无属性的鲲无法渡劫！\n通过【{self.prefix}幻化】可以获得属性"

        if player["jie_cao"] <= 0:
            return "你已经节操丧尽！无法渡劫！"

        trib_cost = self.data._cfg.get("tribulation_cost", 10)
        if player["jie_cao"] < trib_cost:
            return f"节操不足{trib_cost}！无法渡劫！\n当前节操：{player['jie_cao']}"

        player["jie_cao"] -= trib_cost

        if random.random() < 0.5:  # 50%成功率
            kun["weight"] *= random.uniform(1.5, 3.0)
            self.data.save()
            return (
                f"@{name} 渡劫成功！\n"
                f"体重暴涨至{format_weight(kun['weight'])}\n"
                f"剩余节操：{player['jie_cao']}"
            )
        else:
            kun["alive"] = False
            group.setdefault("death_list", []).append(
                {"qq": player["qq"], "reason": "渡劫失败"}
            )
            self.data.save()
            return (
                f"@{name} 粉身碎骨灰飞烟灭！\n渡劫失败！\n剩余节操：{player['jie_cao']}"
            )

    # ---- 放生 ----
    def _release(self, player: dict, name: str, group: dict) -> str:
        kun = player.get("kun")
        if not kun or not kun.get("alive", True):
            return f"@{name} 你并没有鲲！\n发送【{self.prefix}孵化】获取鲲"

        if group.get("auction") and group["auction"]["seller"] == player["qq"]:
            return f"@{name} 正在拍卖，无法放生！\n当前竞价：{group['auction'].get('current_bid', '无')}"

        attr = kun["attribute"]
        bonus_eggs = 0
        if attr == "贪":
            bonus_eggs = random.randint(2, 10)

        player["jie_cao"] += 2
        player["eggs"] += bonus_eggs
        player["kun"] = None

        msg = f"@{name} 功德无量！随喜赞叹！节操+2！"
        if bonus_eggs:
            msg += f"\n意外获得了{bonus_eggs}颗蛋！"
        msg += f"\n现有节操：{player['jie_cao']}"

        self.data.save()
        return msg

    # ---- 复活 ----
    def _resurrect(self, player: dict, name: str, group: dict) -> str:
        kun = player.get("kun")
        if not kun:
            return f"@{name} 你并没有鲲！\n发送【{self.prefix}孵化】获取鲲"

        if kun.get("alive", True):
            return f"@{name} 你的鲲还活着！"

        if player["resurrection_pills"] <= 0:
            return f"@{name} 你没有复活药！\n通过【{self.prefix}砸蛋】可以获取复活药"

        if kun["attribute"] != "无":
            return f"@{name} 复活失败！\n（注：属性鲲是无法复活的）"

        player["resurrection_pills"] -= 1
        kun["alive"] = True
        kun["weight"] = random.randint(DEFAULT_WEIGHT_MIN, DEFAULT_WEIGHT_MAX)
        self.data.save()
        return (
            f"@{name} 已经复活！\n"
            f"起！死！回！生！\n"
            f"新体重：{format_weight(kun['weight'])}\n"
            f"剩余复活药：{player['resurrection_pills']}"
        )

    # ---- 喝鸡汤 ----
    def _drink_soup(self, player: dict, name: str, args: str, group: dict) -> str:
        try:
            count = int(args) if args else 1
        except ValueError:
            return "请输入正确数量！"

        if count <= 0:
            return "请输入正确数量！"

        if player["chicken_soup"] < count:
            return f"@{name} 你没有足够的鸡汤！现有鸡汤：{player['chicken_soup']}"

        player["chicken_soup"] -= count
        player["jie_cao"] += count
        self.data.save()
        return f"@{name} 喝了{count}碗鸡汤，节操+{count}\n哎呀妈呀！真香！\n当前节操：{player['jie_cao']}，剩余鸡汤：{player['chicken_soup']}"

    # ---- 拍卖 ----
    def _auction_sell(
        self, player: dict, uid: str, name: str, args: str, group: dict
    ) -> str:
        if group.get("auction"):
            return "拍卖行消息：\n无法出售！拍卖行已经有鲲在售了！"

        kun = player.get("kun")
        if not kun or not kun.get("alive", True):
            return f"@{name} 你并没有鲲！\n发送【{self.prefix}孵化】可获得鲲"

        if kun["attribute"] == "无":
            return "拍卖行消息：\n无属性的鲲无法出售！"

        try:
            price = float(args)
        except ValueError:
            return "请输入正确的起拍价！\n格式：*出售 价格"

        if price <= 0:
            return "起拍价必须大于0！"

        group["auction"] = {
            "seller": uid,
            "seller_name": name,
            "kun": dict(kun),
            "start_price": price,
            "current_bid": price,
            "bidder": None,
            "start_time": time.time(),
        }

        self.data.save()
        return (
            f"拍卖行消息：\n"
            f"上架成功！\n"
            f"属性：{kun['attribute']}，体重：{format_weight(kun['weight'])}\n"
            f"起拍价：{price}节操\n"
            f"发送【{self.prefix}出价【数值】】参与竞拍\n"
            f"卖家发送【{self.prefix}成交】完成交易"
        )

    def _auction_bid(
        self, player: dict, uid: str, name: str, args: str, group: dict
    ) -> str:
        auc = group.get("auction")
        if not auc:
            return "拍卖行消息：\n目前没有在售的鲲！"

        if auc["seller"] == uid:
            return "拍卖行消息：\n无法为自己的鲲出价！"

        try:
            bid = float(args)
        except ValueError:
            return "请输入正确数值！"

        if bid <= auc["current_bid"]:
            return (
                f"拍卖行消息：\n出价失败！\n出价必须大于当前竞价：{auc['current_bid']}"
            )

        if player["jie_cao"] < bid:
            return f"拍卖行消息：\n出价失败！\n节操不足！当前节操：{player['jie_cao']}"

        auc["current_bid"] = bid
        auc["bidder"] = uid
        self.data.save()
        return (
            f"拍卖行消息：\n"
            f"出价成功！\n"
            f"当前竞价：{bid}\n"
            f"卖家发送【{self.prefix}成交】完成交易"
        )

    def _auction_deal(self, player: dict, uid: str, name: str, group: dict) -> str:
        auc = group.get("auction")
        if not auc:
            return "拍卖行消息：\n你没有在售的鲲！"

        if auc["seller"] != uid:
            return "拍卖行消息：\n你不是卖家！"

        bidder = auc.get("bidder")
        if not bidder:
            return "拍卖行消息：\n没有买主！"

        buyer = self.data.get_player(group["gid"], bidder)
        seller = self.data.get_player(group["gid"], uid)

        price = auc["current_bid"]
        if buyer["jie_cao"] < price:
            return "买主节操不足！"

        buyer["jie_cao"] -= price
        seller["jie_cao"] += price

        # 转移鲲
        seller_kun = auc["kun"]
        buyer["kun"] = seller_kun
        player["kun"] = None

        group["auction"] = None
        self.data.save()
        return f"拍卖行消息：\n交♂易成功！\n{name}的鲲以{price}节操卖给了{bidder}！"

    def _auction_force_delist(self, group: dict, args: str) -> str:
        auc = group.get("auction")
        if not auc:
            return "拍卖行消息：\n目前没有在售的鲲！"

        group["auction"] = None
        self.data.save()
        return "已经下架！"

    def _auction_force_delist_admin(self, group: dict, uid: str, name: str) -> str:
        auc = group.get("auction")
        if not auc:
            return "拍卖行消息：\n没有在售的鲲！"

        if time.time() - auc["start_time"] < 300:  # 5分钟保护
            return "拍卖行消息：\n上架时间不足5分钟，不可强制下架！"

        group["auction"] = None
        self.data.save()
        return "已经强制下架！"

    def _auction_list(self, group: dict) -> str:
        auc = group.get("auction")
        if not auc:
            return f"拍卖行消息：\n目前没有鲲上架！\n发送【{self.prefix}出售【起拍价】】将自己的鲲上架"

        kun = auc["kun"]
        return (
            f"拍卖行消息：\n"
            f"卖家：{auc.get('seller_name', '?')}\n"
            f"鲲名：{kun.get('name', '未知')}\n"
            f"属性：{kun['attribute']}，体重：{format_weight(kun['weight'])}\n"
            f"当前竞价：{auc['current_bid']}\n"
            f"出价者：{auc.get('bidder', '无')}\n"
            f"发送【{self.prefix}出价【竞拍价】】进行竞拍"
        )

    # ---- 免疫 ----
    def _immunity(
        self,
        player: dict,
        uid: str,
        name: str,
        args: str,
        immunity_type: str,
        group: dict,
    ) -> str:
        kun = player.get("kun")
        if not kun:
            return f"@{name} 你还没有鲲！"

        # 魑免疫强袭, 魅免疫吞噬, 魍免疫攻击, 惰免疫强袭
        attr_immunity_map = {
            "魑": "anti_assault",
            "魅": "anti_devour",
            "魍": "anti_attack",
            "惰": "anti_assault",
        }
        expected = attr_immunity_map.get(kun["attribute"])
        if expected == immunity_type:
            return f"@{name} 你的鲲({kun['attribute']})已免疫！"
        return f"@{name} 你的鲲属性不提供此免疫"

    # ---- 骰子 ----
    def _roll_dice(self, player: dict, name: str, args: str) -> str:
        try:
            sides = int(args) if args else 6
        except ValueError:
            sides = 6
        if sides < 2:
            sides = 2
        if sides > 100:
            sides = 100
        result = random.randint(1, sides)
        return f"@{name} 掷出了 {result} 点 (D{sides})"

    # ==================== 小游戏 ====================

    def _start_mini_game(self, group: dict, game_type: str) -> str:
        """开始一个小游戏"""
        if not group.get("game_enabled", True):
            return "小游戏未开启！"

        mg = group.get("mini_game")
        if mg:
            return f"当前已有游戏在进行中：{mg['type']}"

        if game_type == "math":
            return self._start_math_game(group)
        elif game_type == "star":
            return self._start_star_game(group)
        elif game_type == "homework":
            return self._start_homework_game(group)
        elif game_type == "slap":
            return self._start_slap_game(group)
        return "未知游戏类型"

    def _start_math_game(self, group: dict) -> str:
        mg = {
            "type": "奥数比赛",
            "slots_used": 0,
            "max_slots": 5,
            "participants": [],
            "rewards": {},
        }
        a, b = random.randint(1, 99), random.randint(1, 99)
        op = random.choice(["+", "-", "*"])
        if op == "+":
            answer = a + b
        elif op == "-":
            answer = a - b
        else:
            answer = a * b
        mg["question"] = f"{a} {op} {b} = ?"
        mg["answer"] = str(answer)
        group["mini_game"] = mg
        self.data.save()
        return f"奥数比赛【总名额5】\n问：{mg['question']}\n回复【{self.prefix}=数值】来抢答\n剩余名额：5"

    def _start_star_game(self, group: dict) -> str:
        mg = {
            "type": "数星星",
            "slots_used": 0,
            "max_slots": 2,
            "participants": [],
            "rewards": {},
        }
        stars = random.randint(5, 20)
        black = random.randint(1, min(5, stars))
        mg["question"] = f"☆☆★☆★★☆★☆☆★☆★★★☆★☆★★☆★☆★☆"[: stars * 2]
        mg["answer"] = str(black)
        group["mini_game"] = mg
        self.data.save()
        return f"数星星【总名额2】\n问：有多少黑色星星\n回复【{self.prefix}=数值】来抢答\n剩余名额：2"

    def _start_homework_game(self, group: dict) -> str:
        mg = {
            "type": "抄作业",
            "slots_used": 0,
            "max_slots": 5,
            "participants": [],
            "rewards": {},
        }
        chars = "ABCDEFGHJKLMN0123456789"
        question = "".join(random.choice(chars) for _ in range(random.randint(4, 8)))
        mg["question"] = question
        mg["answer"] = question[::-1]  # 倒序
        group["mini_game"] = mg
        self.data.save()
        return f"抄作业【总名额5】\n答案：倒序抄写问题\n原文：{question}\n回复【{self.prefix}=答案】获取节操\n剩余名额：5"

    def _start_slap_game(self, group: dict) -> str:
        mg = {
            "type": "群殴群主",
            "slots_used": 0,
            "max_slots": 5,
            "participants": [],
            "rewards": {},
        }
        group["mini_game"] = mg
        self.data.save()
        return f"群殴群主【总名额5】\n回复【{self.prefix}抽群主一个大嘴巴】获取节操\n剩余名额：5"

    def _mini_game_answer(
        self, answer: str, uid: str, name: str, group: dict
    ) -> str | None:
        mg = group.get("mini_game")
        if not mg:
            return None

        if uid in mg.get("participants", []):
            return f"@{name} 你已经参与过此轮游戏了！"

        if mg["slots_used"] >= mg["max_slots"]:
            return "本轮游戏名额已满！"

        mg["slots_used"] += 1
        mg["participants"].append(uid)

        if answer.strip().upper() == mg["answer"].strip().upper():
            reward = random.randint(2, 8)
            player = self.data.get_player(group["gid"], uid)
            player["jie_cao"] += reward
            self.data.save()
            group["mini_game"] = None
            return f"@{name} 回答正确！节操+{reward}\n当前节操：{player['jie_cao']}"

        player = self.data.get_player(group["gid"], uid)
        player["jie_cao"] = max(0, player["jie_cao"] - 1)
        self.data.save()

        if mg["slots_used"] >= mg["max_slots"]:
            group["mini_game"] = None
            return f"@{name} 回答错误！节操-1\n游戏结束，正确答案是：{mg['answer']}"

        remaining = mg["max_slots"] - mg["slots_used"]
        return f"@{name} 回答错误！节操-1\n剩余名额：{remaining}"

    def _mini_game_slap(self, player: dict, uid: str, name: str, group: dict) -> str:
        mg = group.get("mini_game")
        if not mg or mg.get("type") != "群殴群主":
            return self._start_slap_game(group)

        if uid in mg.get("participants", []):
            return f"@{name} 你已经抽过了！目无法纪！胆大包天！节操-10"

        mg["slots_used"] += 1
        mg["participants"].append(uid)

        reward = random.randint(1, 5)
        player["jie_cao"] += reward
        self.data.save()

        remaining = mg["max_slots"] - mg["slots_used"]
        msg = f"@{name} 抽了群主一个大嘴巴！节操+{reward}\n抚摸了群主的脸颊，响亮但不文雅！"
        if remaining > 0:
            msg += f"\n剩余名额：{remaining}"
        else:
            group["mini_game"] = None
            msg += "\n群主已被抽肿！游戏结束！"
        return msg

    def _mini_game_duel(self, player: dict, uid: str, name: str, group: dict) -> str:
        if player["jie_cao"] <= 0:
            return "节操至少为1才能参与游戏"

        champion = group.get("duel_champion")
        if champion and champion["uid"] == uid:
            return f"@{name} 你就是群主！还有谁！！！"

        if not champion:
            # 发起挑战，挑战者打群主
            group["duel_champion"] = {"uid": uid, "name": name, "consecutive": 0}
            self.data.save()
            return (
                f"@{name} 开始单挑群主！\n"
                f"回复【{self.prefix}单挑群主】继续挑战\n"
                f"直到有人打败群主才可结束当前游戏！\n"
                f"获胜节操奖励：{5}"
            )

        # 挑战
        consec = champion.get("consecutive", 0)
        win_chance = 0.3 + consec * 0.05  # 连胜越高越难打败

        if random.random() < win_chance:
            # 挑战者获胜
            reward = 5 + consec * 2
            player["jie_cao"] += reward
            player["luck"] = min(100, player["luck"] + 5)
            group["duel_champion"] = None
            self.data.save()
            return (
                f"@{name} 打趴了群主！功德无量，百世流芳！\n"
                f"节操+{reward}，奖励提高至{5 + (consec + 1) * 2}\n"
                f"单挑群主游戏结束\n"
                f"还有谁！！！\n"
                f"发送【{self.prefix}单挑群主】进行游戏"
            )
        else:
            # 挑战失败
            player["jie_cao"] = max(0, player["jie_cao"] - 5)
            champion["consecutive"] = consec + 1
            self.data.save()
            return (
                f"@{name} 不自量力！螳臂当车！\n"
                f"被群主打趴了！舍生取益，可歌可泣！\n"
                f"节操-5，当前节操：{player['jie_cao']}\n"
                f"回复【{self.prefix}单挑群主】继续挑战"
            )
