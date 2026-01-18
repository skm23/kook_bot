#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kook机器人
基于khl.py开发
"""

import io
import re
import os
import sys
import time
import random
import aiohttp
import asyncio
import datetime
import traceback
import statistics
from loguru import logger
from threading import Thread
from dotenv import load_dotenv
from typing import  Dict, List, Set, Optional
from khl import Bot, Message, EventTypes, Event
from khl.card import Card, CardMessage, Module, Element, Types

from config1 import get_json
load_dotenv('config1\.env')

"""
bot_token
创建机器人实例
"""
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(token=BOT_TOKEN)
ADMIN_USER_IDS = os.getenv('ADMIN_USER_IDS')


"""
日志配置
"""
if get_json.log_create == 1:
    logger.add("log\kook_bot.log")

"""
猜数字
"""
#游戏状态管理
class GuessManger:
    def __init__(self):
        self.active_games: Dict[str, 'GameSession'] = {}       # 频道ID -> 游戏会话
        self.player_stats: Dict[str, dict] = {}               # 玩家ID -> 统计数据

    def start_game(self, channel_id: str, player_id: str, player_name: str):
        #开始游戏
        # 结束该频道的现有游戏（如果有）
        if channel_id in self.active_games:
            self.end_game(channel_id)

        #创建新游戏
        target_number = random.randint(1,100)
        self.active_games[channel_id] = GameSession(
            target_number = target_number,
            player_id = player_id,
            player_name = player_name,
            start_time = time.time()
        )

        return self.active_games[channel_id]

    def end_game(self, channel_id: str):
        #结束游戏
        if channel_id in self.active_games:
            del self.active_games[channel_id]

    def get_game(self, channel_id: str) -> Optional['GameSession']:
        #获取游戏会话
        return self.active_games.get(channel_id)

    def record_win(self, player_id: str, player_name: str, attempts: int, time_taken: float):
        #记录玩家胜利
        if player_id not in self.player_stats:
            self.player_stats[player_id] = {
                'name': player_name,
                'wins': 0,
                'total_attempts': 0,
                'total_games': 0,
                'best_score': float('inf'),
                'best_time': float('inf')
            }

        stats = self.player_stats[player_id]
        stats['wins'] += 1
        stats['total_attempts'] += attempts
        stats['total_games'] += 1

        if attempts < stats['best_score']:
            stats['best_score'] = attempts
        if time_taken < stats['best_time']:
            stats['best_time'] = time_taken

    def get_leaderboard(self) -> List[dict]:
        #获取排行榜
        return sorted(
            self.player_stats.values(),
            key=lambda x: (-x['wins'], x['best_score'], x['best_time'])
        )[:10]

class GameSession:
    def __init__(self, target_number: int, player_id: str, player_name: str, start_time: float):
        self.target_number = target_number
        self.player_id = player_id
        self.player_name = player_name
        self.start_time = start_time
        self.attempts = 0
        self.guess_history: List[int] = []

    def make_guess(self, guess: int) -> dict:
        #进行猜测并返回结果
        self.attempts += 1
        self.guess_history.append(guess)

        if guess == self.target_number:
            return {'status': 'correct', 'message': '🎉 恭喜你猜对了！'}
        elif guess < self.target_number:
            return {'status': 'low', 'message': '📈 猜小了，再试试！'}
        else:
            return {'status': 'high', 'message': '📉 猜大了，再试试！'}

    def get_hint(self) -> str:
        #获取提示
        if len(self.guess_history) < 2:
            return "还没有足够的猜测来提供提示"

        last_guess = self.guess_history[-1]
        prev_guess = self.guess_history[-2]

        if abs(last_guess - self.target_number)< abs(prev_guess - self.target_number):
            return "🔥 更接近了！"
        else:
            return "❄️ 更远了！"

    def get_time_taken(self) -> float:
        #获取游戏耗时
        return time.time() - self.start_time

#创建全集游戏管理器
guess_manager = GuessManger()

@bot.command(name='猜', prefixes=['/'])
async def guess_command(msg: Message, number: str):
    #猜数字
    try:
        chnnel_id = msg.ctx.channel.id
        user_id = msg.author.id
        username = msg.author.username

        #解析数字参数
        try:
            guess_num = int(number)
            if guess_num < 1 or guess_num > 100:
                raise ValueError("数字必须在1-100之间")

        except ValueError:
            card = Card(
                Module.Section(
                    Element.Text(
                        "❌ **参数错误**\n"
                        "请输入1-100之间的整数，例如: `/猜 50`",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )

            await msg.reply(CardMessage(card))
            return

        #获取当前游戏
        game = guess_manager.get_game(chnnel_id)

        if not game:
            #没有进行中的游戏，自动开始新游戏
            game = guess_manager.start_game(chnnel_id, user_id, username)
            card = Card(
                Module.Header("🎯 新游戏开始"),
                Module.Section(
                    Element.Text(
                        f"👤 玩家: {username}\n"
                        f"🎲 数字范围: 1-100\n"
                        f"💡 已猜测: {guess_num}\n\n"
                        f"游戏已自动开始！请继续猜测。",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.INFO
            )
            await msg.reply(CardMessage(card))

            #处理第一次猜测
            result = game.make_guess(guess_num)
            await send_guess_result(msg, result, game, is_first_guess = True)
            return

        #检查是否是游戏创建者
        if game.player_id != user_id:
            card = Card(
                Module.Section(
                    Element.Text(
                        f"⏸️ **游戏进行中**\n"
                        f"当前 {game.player_name} 正在游戏中。\n"
                        f"请等待当前游戏结束或使用 `/新游戏` 开始新游戏。",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.WARNING
            )
            await msg.reply(CardMessage(card))
            return

        #处理猜测
        result = game.make_guess(guess_num)

        if result['status'] == 'correct':
            #猜对游戏结束
            time_taken = game.get_time_taken()
            guess_manager.record_win(user_id, username, game.attempts, time_taken)

            await send_victory_message(msg, game, time_taken)

        else:
            #继续猜
            await send_guess_result(msg, result, game, is_first_guess = False)

    except Exception as e:
        logger.warning(f"处理 /猜 命令时出错: {e}")
        await send_error_message(msg, "处理猜测命令时出现错误")

@bot.command(name='新游戏', prefixes=['/'])
async def newgame_command(msg: Message):
    #开始新游戏新命令
    try:
        channel_id = msg.ctx.channel.id
        user_id = msg.author.id
        username = msg.author.username

        #结束现有游戏(如果有)
        if channel_id in guess_manager.active_games:
            guess_manager.end_game(channel_id)

        #开始新游戏
        game = guess_manager.start_game(channel_id, user_id, username)

        card = Card(
            Module.Header("🎯 新游戏开始"),
            Module.Section(
                Element.Text(
                    f"👤 玩家: {username}\n"
                    f"🎲 数字范围: 1-100\n"
                    f"⏱️ 计时开始！\n\n"
                    f"请使用 `/猜 数字` 开始猜测。",
                    type=Types.Text.KMD
                )
            ),
            Module.Context(
                Element.Text("💡 提示: 数字在1到100之间", type=Types.Text.KMD)
            ),
            theme=Types.Theme.SUCCESS
        )

        await msg.reply(CardMessage(card))

    except Exception as e:
        logger.warning(f"处理 /新游戏 命令时出错: {e}")
        await send_error_message(msg, "开始新游戏时出现错误")

@bot.command(name='提示', prefixes=['/'])
async def hint_command(msg: Message):
    #提示
    try:
        channel_id = msg.ctx.channel.id
        user_id = msg.author.id

        game = guess_manager.get_game(channel_id)

        if not game:
            card = Card(
                Module.Section(
                    Element.Text(
                        "❌ **没有进行中的游戏**\n"
                        "请先使用 `/新游戏` 开始游戏。",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )
            await msg.reply(CardMessage(card))
            return

        if game.player_id != user_id:
            card = Card(
                Module.Section(
                    Element.Text(
                        f"🚫 **权限不足**\n"
                        f"只有游戏创建者 {game.player_name} 可以获取提示。",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.WARNING
            )
            await msg.reply(CardMessage(card))
            return

        hint = game.get_hint()

        card = Card(
            Module.Section(
                Element.Text(
                    f"💡 **提示**\n"
                    f"{hint}\n"
                    f"📊 已尝试: {game.attempts} 次\n"
                    f"📝 最近猜测: {game.guess_history[-1] if game.guess_history else '无'}",
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.INFO
        )

        await msg.reply(CardMessage(card))

    except Exception as e:
        logger.warning(f"处理 /提示 命令时出错: {e}")
        await send_error_message(msg, "获取提示时出现错误")

@bot.command(name='结束', prefixes=['/'])
async def endgame_command(msg: Message):
    #结束游戏
    try:
        channel_id = msg.ctx.channel.id
        user_id = msg.author.id

        game = guess_manager.get_game(channel_id)

        if not game:
            card = Card(
                Module.Section(
                    Element.Text(
                        "❌ **没有进行中的游戏**\n"
                        "当前没有需要结束的游戏。",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )
            await msg.reply(CardMessage(card))
            return

        if game.player_id != user_id:
            card = Card(
                Module.Section(
                    Element.Text(
                        f"🚫 **权限不足**\n"
                        f"只有游戏创建者 {game.player_name} 可以结束游戏。",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.WARNING
            )
            await msg.reply(CardMessage(card))
            return

        #结束游戏并显示答案
        guess_manager.end_game(channel_id)

        card = Card(
            Module.Section(
                Element.Text(
                    f"🏁 **游戏结束**\n"
                    f"正确答案是: **{game.target_number}**\n"
                    f"📊 尝试次数: {game.attempts}\n"
                    f"⏱️ 游戏时长: {game.get_time_taken():.1f}秒\n\n"
                    f"使用 `/新游戏` 开始新游戏！",
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.SECONDARY
        )

        await msg.reply(CardMessage(card))

    except Exception as e:
        logger.warning(f"处理 /结束 命令时出错: {e}")
        await send_error_message(msg, "结束游戏时出现错误")

@bot.command(name='排行榜', prefixes=['/'])
async def leaderboard_command(msg: Message):
    #排行榜显示
    try:
        leaderboard = guess_manager.get_leaderboard()

        if not leaderboard:
            card = Card(
                Module.Section(
                    Element.Text(
                        "📊 **排行榜**\n"
                        "暂无游戏记录。\n"
                        "快来成为第一个获胜者吧！",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.INFO
            )
            await msg.reply(CardMessage(card))
            return

        leaderboard_text = ""
        for i, player in enumerate(leaderboard, 1):
            leaderboard_text += (
                f"**{i}. {player['name']}**\n"
                f"   🏆 胜利: {player['wins']}次 | "
                f"🎯 最佳: {player['best_score']}次 | "
                f"⏱️ 最快: {player['best_time']:.1f}秒\n"
            )

        card = Card(
            Module.Header("🏆 猜数字排行榜"),
            Module.Section(
                Element.Text(
                    f"📊 **顶尖玩家**\n\n"
                    f"{leaderboard_text}",
                    type=Types.Text.KMD
                )
            ),
            Module.Context(
                Element.Text("💡 排名依据: 胜利次数 → 最少尝试 → 最快时间", type=Types.Text.KMD)
            ),
            theme=Types.Theme.SUCCESS
        )

        await msg.reply(CardMessage(card))

    except Exception as e:
        logger.warning(f"处理 /排行榜 命令时出错: {e}")
        await send_error_message(msg, "显示排行榜时出现错误")

async def send_guess_result(msg: Message, result: dict, game: GameSession, is_first_guess: bool):
    #发送猜测结果
    status_emoji = "🎯" if is_first_guess else "🔄"

    card = Card(
        Module.Section(
            Element.Text(
                f"{status_emoji} **猜测结果**\n"
                f"{result['message']}\n"
                f"📊 尝试次数: {game.attempts}\n"
                f"📝 历史猜测: {', '.join(map(str, game.guess_history[-5:]))}",
                type=Types.Text.KMD
            )
        ),
        Module.Context(
            Element.Text("💡 使用 `/提示` 获取提示", type=Types.Text.KMD)
        ),
        theme=Types.Theme.INFO
    )

    await msg.reply(CardMessage(card))

async def send_victory_message(msg: Message, game: GameSession, time_taken: float):
    #发送胜利消息
    #表现
    if game.attempts <= 5:
        rating = "🎖️ 天才！"
    elif game.attempts <= 10:
        rating = "🏅 很棒！"
    elif game.attempts <= 15:
        rating = "🥉 不错！"
    else:
        rating = "📝 继续努力！"

    card = Card(
        Module.Header("🎉 恭喜获胜！"),
        Module.Section(
            Element.Text(
                f"👑 **胜利者:** {game.player_name}\n"
                f"✅ **正确答案:** {game.target_number}\n"
                f"📊 **尝试次数:** {game.attempts}次\n"
                f"⏱️ **用时:** {time_taken:.1f}秒\n"
                f"🏆 **评价:** {rating}\n\n"
                f"使用 `/新游戏` 再玩一次！",
                type=Types.Text.KMD
            )
        ),
        theme=Types.Theme.SUCCESS
    )

    await msg.reply(CardMessage(card))

#处理错误消息
async def send_error_message(msg: Message, error_text: str):
    card = Card(
        Module.Section(
            Element.Text(
                f"⚠️ **系统错误**\n"
                f"{error_text}，请稍后重试。",
                type=Types.Text.KMD
            )
        ),
        theme=Types.Theme.WARNING
    )

    await  msg.reply(CardMessage(card))


"""
分组功能
"""
class GroupManager:
    def __init__(self):
        self.is_collecting = False
        self.participants: Set[str] = set()    #存储用户id
        self.user_names: Dict[str, str] = {}   #存储ID到用户名的映射

    def start_collection(self):                #开始统计
        self.is_collecting = True
        self.participants.clear()
        self.user_names.clear()

    def add_participant(self, user_id: str, username: str):    #添加参与者
        if self.is_collecting:
            self.participants.add(user_id)
            self.user_names[user_id] = username

    def stop_collection(self):                 #结束统计
        self.is_collecting = False

    def get_participant_count(self) -> int:    #获取参与者数量
        return len(self.participants)

    def get_participant_names(self) -> List[str]:              #获取所有参与者用户名
        return [self.user_names[uid] for uid in self.participants]

    def generate_groups(self, group_count: int) -> List[List[str]]:     #随机分成指定数量的组
        if not self.participants:
            return []

        #随机打乱参与者列表
        shuffled_users = list(self.participants)
        random.shuffle(shuffled_users)

        #计算每组大致人数
        total_users = len(shuffled_users)
        base_group_size = total_users // group_count
        remainder = total_users % group_count

        groups: List[List[str]] = []
        start_index = 0

        #分配用户到各组
        for i in range(group_count):
            #前remainder组多一个人
            group_size = base_group_size + (1 if i < remainder else 0)
            end_index = start_index + group_size

            #获取该组的用户id并转换为用户名
            group_user_ids = shuffled_users[start_index: end_index]
            group_users = [self.user_names[uid] for uid in group_user_ids]

            groups.append(group_users)
            start_index = end_index

        return groups

group_manager = GroupManager()

@bot.command(name="start", prefixes=['/'])
async def start_command(msg:Message):
    try:
        if group_manager.is_collecting:
            card = Card(
                Module.Section(
                    Element.Text(
                        "⚠️ **统计正在进行中**\n"
                        "当前已有统计正在进行，请先使用 `/end n` 结束当前统计。",
                        type=Types.Text.KMD
                    )
                )
            )
            await msg.reply(CardMessage(card))
            return

        #开始新的统计
        group_manager.start_collection()

        card = Card(
            Module.Header("🎯 分组统计开始"),
            Module.Section(
                Element.Text(
                    "📋 **统计已开始**\n"
                    "现在可以输入 `/j` 报名参加分组。\n"
                    "当所有参与者报名完成后，使用 `/end n` 进行分组。\n\n"
                    "**使用方法:**\n"
                    "• 报名: `/j`\n"
                    "• 结束统计: `/end 组数` (例如: `/end 3`)",
                    type=Types.Text.KMD
                )
            ),
            Module.Context(
                Element.Text("💡 提示: 分组结果将随机分配", type=Types.Text.KMD)
            ),
            theme=Types.Theme.SUCCESS
        )

        await msg.reply(CardMessage(card))

    except Exception as e:
        logger.warning(f"处理 /start 命令时出错：{e}")
        await send_error_message(msg, "处理开始命令时出现错误")

@bot.command(name='j', prefixes=['/'])
async def join_command(msg: Message):
    #报名参加分组命令
    try:
        if not group_manager.is_collecting:
            #统计未开始
            card = Card(
                Module.Section(
                    Element.Text(
                        "❌ **统计未开始**\n"
                        "请先使用 `/start` 开始统计后再报名。",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )
            await  msg.reply(CardMessage(card))
            return

        user_id = msg.author.id
        username = msg.author.username

        #检查是否已经报名
        if user_id in group_manager.participants:
            card = Card(
                Module.Section(
                    Element.Text(
                        f"ℹ️ **已经报名**\n"
                        f"{username}，你已经报名过了！",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.INFO
            )
            await msg.reply(CardMessage(card))
            return

        #添加参与者
        group_manager.add_participant(user_id, username)

        current_count = group_manager.get_participant_count()

        card = Card(
            Module.Section(
                Element.Text(
                    f"✅ **报名成功**\n"
                    f"👤 用户: {username}\n"
                    f"📊 当前人数: {current_count} 人\n\n"
                    f"感谢你的参与！",
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.SUCCESS
        )

        await msg.reply(CardMessage(card))

    except Exception as e:
        logger.warning(f"处理 /j 命令时出错: {e}")
        await send_error_message(msg, "处理报名命令时出现错误")

@bot.command(name='end', prefixes=['/'])
async def end_command(msg: Message, group_count: str):
    #结束统计并分组命令
    try:
        if not group_manager.is_collecting:
            #统计未开始
            card = Card(
                Module.Section(
                    Element.Text(
                        "❌ **统计未开始**\n"
                        "请先使用 `/start` 开始统计。",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )
            await msg.reply(CardMessage(card))
            return

        #解析组数参数
        try:
            n = int(group_count)
            if n <= 0:
                raise ValueError("组数必须大于0")
        except ValueError:
            card = Card(
                Module.Section(
                    Element.Text(
                        "❌ **参数错误**\n"
                        "请输入有效的组数，例如: `/end 3`",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )
            await msg.reply(CardMessage(card))
            return

        total_participants = group_manager.get_participant_count()

        if total_participants == 0:
            card = Card(
                Module.Section(
                    Element.Text(
                        "❌ **没有参与者**\n"
                        "当前没有用户报名，无法进行分组。",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )
            await msg.reply(CardMessage(card))
            return

        if n > total_participants:
            card = Card(
                Module.Section(
                    Element.Text(
                        f"❌ **组数过多**\n"
                        f"当前有 {total_participants} 人，但要求分成 {n} 组。\n"
                        f"组数不能超过参与者数量。",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )
            await msg.reply(CardMessage(card))
            return

        #生成分组
        groups = group_manager.generate_groups(n)
        group_manager.stop_collection()

        #构建分组结果消息
        group_text = ""
        for i,group in enumerate(groups, 1):
            group_text += f"**第 {i} 组** ({len(group)}人):\n"
            group_text += ", ".join(group) + "\n\n"

        card = Card(
            Module.Header("🎉 分组完成"),
            Module.Section(
                Element.Text(
                    f"📊 **分组结果**\n"
                    f"总人数: {total_participants} 人\n"
                    f"组数: {n} 组\n\n"
                    f"{group_text}",
                    type=Types.Text.KMD
                )
            ),
            Module.Context(
                Element.Text("🎲 分组结果随机生成，祝大家游戏愉快！", type=Types.Text.KMD)
            ),
            theme=Types.Theme.SUCCESS
        )
        await  msg.reply(CardMessage(card))

    except Exception as e:
        logger.warning(f"处理 /end 命令时出错：{e}")
        await send_error_message(msg,"处理结束命令时出现错误")

@bot.command(name="status", prefixes=['/'])
async def status_command(msg: Message):
    #查看当前统计状态
    try:
        if not group_manager.is_collecting:
            card = Card(
                Module.Section(
                    Element.Text(
                        "📊 **统计状态**\n"
                        "当前没有进行中的统计。\n"
                        "使用 `/start` 开始新的统计。",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.INFO
            )

        else:
            count = group_manager.get_participant_count()
            participants = group_manager.get_participant_names()

            participant_list = ", ".join(participants) if participants else "暂无"

            card = Card(
                Module.Section(
                    Element.Text(
                        f"📊 **统计进行中**\n"
                        f"当前人数: {count} 人\n"
                        f"参与者: {participant_list}\n\n"
                        f"使用 `/end n` 结束统计并分组。",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.INFO
            )

        await msg.reply(CardMessage(card))

    except Exception as e:
        logger.warning(f"处理 /status 命令时出错: {e}")
        await send_error_message(msg, "处理状态命令时出现错误")

"""
骗子酒馆模式
"""
#储存游戏状态
games = {}

#定义扑克牌
CARDS = ['A', 'K', 'Q'] * 6 + ['JOKER'] * 2

# 用于跟踪俄罗斯轮盘的概率状态
roulette_state = {}

def create_chamber():
    #创建新的左轮，只有一个子弹位置
    chamber = [False] * 6
    # 固定子弹位置为0
    chamber[0] = True
    return chamber

def spin_chamber():
    #旋转弹仓，随机选一个位
    return random.randint(0,5)

def get_roulette_probability(channel_id, player_id):
    key = f"{channel_id}:{player_id}"
    if key not in roulette_state:
        #初始化概率
        roulette_state[key] = 6    #初始概率分母为6
    return roulette_state[key]

def update_roulette_probability(channel_id, player_id):
    #更新的概率
    key = f"{channel_id}:{player_id}"
    if key in roulette_state:
        roulette_state[key] = max(1,roulette_state[key] - 1)   #概率增加
    else:
        roulette_state[key] = 6

@bot.command(name='创建游戏', prefixes=['/'])
async def start_game_command(msg: Message):
    channel_id = msg.ctx.channel.id
    if channel_id in games:
        card = Card(
            Module.Section(
                Element.Text(
                    f'当前频道已经有一个游戏正在进行中！',
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.DANGER
        )

        await msg.reply(CardMessage(card))
        return

    # 初始化新游戏
    games[channel_id] = {
        'players': [],
        'status': 'waiting',
        'current_player': None,
        'target_card': None,
        'deck': [],
        'discard_pile': [],
        'last_declared_card': None,
        'last_player': None
    }

    card = Card(
        Module.Section(
            Element.Text(
                f'游戏已创建！请玩家们输入 `/加入游戏` 加入游戏。',
                type=Types.Text.KMD
            )
        ),
        theme=Types.Theme.SUCCESS
    )

    await msg.reply(CardMessage(card))

@bot.command(name='加入游戏', prefixes=['/'])
async def join_game_command(msg: Message):
    channel_id = msg.ctx.channel.id
    user_id = msg.author.id
    user_name = msg.author.nickname or msg.author.username

    if channel_id not in games:
        card = Card(
            Module.Section(
                Element.Text(
                    f'当前频道没有正在进行的游戏，请先创建游戏！\n'
                    f"输入 `/创建游戏` 以创建游戏",
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.DANGER
        )

        await msg.ctx.channel.send(CardMessage(card), temp_target_id = msg.author.id)
        return

    game = games[channel_id]
    if game['status'] != 'waiting':
        card = Card(
            Module.Section(
                Element.Text(
                    f'游戏已经开始，无法加入！',
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.DANGER
        )

        await msg.ctx.channel.send(CardMessage(card), temp_target_id = msg.author.id)
        return

    #检查玩家是否已加入
    for player in game['players']:
        if player['id'] == user_id:
            card = Card(
                Module.Section(
                    Element.Text(
                        f'{user_name} 已经在游戏房间中了！\n'
                        f"请等待游戏开始\n",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.SECONDARY
            )

            await msg.ctx.channel.send(CardMessage(card), temp_target_id = msg.author.id)
            return

    #添加玩家
    game['players'].append({
        'id': user_id,
        'name': user_name,
        'cards': [],
        'alive': True,
        'bullet_chamber': create_chamber(),          # 左轮手枪弹仓，6个位置
        'chamber_position': spin_chamber()           # 弹仓当前位置
    })

    card = Card(
        Module.Section(
            Element.Text(
                f'{user_name} 已加入游戏！当前玩家数量：{len(game["players"])}\n'
                f"请等待房主开始游戏",
                type=Types.Text.KMD
            )
        ),
        theme=Types.Theme.SUCCESS
    )

    await msg.reply(CardMessage(card))

@bot.command(name='开始游戏', prefixes=['/'])
async def begin_game_command(msg: Message):
    channel_id = msg.ctx.channel.id
    if channel_id not in games:
        card = Card(
            Module.Section(
                Element.Text(
                    f'当前频道没有正在进行的游戏，请先创建游戏！'
                    f"请输入 `/创建游戏` 以创建游戏",
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.DANGER
        )

        await msg.reply(CardMessage(card))
        return

    game = games[channel_id]
    if game['status'] != 'waiting':
        card = Card(
            Module.Section(
                Element.Text(
                    f'游戏已经开始！\n'
                    f"请等待下一场游戏的开始",
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.DANGER
        )

        await msg.ctx.channel.send(CardMessage(card), temp_target_id = msg.author.id)
        return

    # 检查玩家数量
    player_count = len(game['players'])
    if player_count < 2:
        card = Card(
            Module.Section(
                Element.Text(
                    f'至少需要2名玩家才能开始游戏！当前只有{player_count}名玩家。',
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.WARNING
        )

        await msg.reply(CardMessage(card))
        return

    # 开始游戏
    game['status'] = 'playing'

    # 确定目标牌
    game['target_card'] = random.choice(['A', 'K', 'Q'])

    # 初始化牌堆
    game['deck'] = CARDS.copy()
    random.shuffle(game['deck'])

    # 发牌给每个玩家
    for player in game['players']:
        player['cards'] = []
        for _ in range(5):
            if game['deck']:
                player['cards'].append(game['deck'].pop())

        # 装填子弹（每个玩家使用相同的弹仓）
        player['bullet_chamber'] = create_chamber()
        player['chamber_position'] = spin_chamber()

    # 通过私信发送手牌给每个玩家
    for player in game['players']:
        cards_str = ', '.join(player['cards'])
        try:
            user = await bot.client.fetch_user(player['id'])

            card = Card(
                Module.Section(
                    Element.Text(
                        f'你的手牌是: {cards_str}\n'
                        f'目标牌是: {game["target_card"]}\n'
                        f'发送 "状态" 可以随时查看游戏状态。\n'
                        f'出牌格式：出牌 牌名 声明数量（例如：出牌 A 3）',
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.INFO
            )

            await user.send(CardMessage(card))

        except Exception as e:
            # 如果无法发送私信，就在频道中提示
            card = Card(
                Module.Section(
                    Element.Text(
                        f'无法向 {player["name"]} 发送私信，请检查隐私设置。',
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.WARNING
            )

            await msg.reply(CardMessage(card))

    # 确定第一个玩家
    game['current_player'] = 0
    first_player = game['players'][game['current_player']]

    # 显示游戏开始信息（不包含具体手牌）
    player_names = ', '.join([p['name'] for p in game['players']])
    card = Card(
        Module.Section(
            Element.Text(
                f'游戏开始！\n'
                f'玩家: {player_names}\n'
                f'目标牌: {game["target_card"]}\n'
                f'请{first_player["name"]}前往bot私信出牌!\n',
                type=Types.Text.KMD
            )
        ),
        theme=Types.Theme.SECONDARY
    )

    await msg.reply(CardMessage(card))

# 处理私信出牌
@bot.on_message()
async def handle_private_play(msg: Message):
    # 检查是否是出牌指令格式
    content = msg.content.strip()
    if not (content.startswith('出牌') or content == '状态' or content == 'status'):
        # 如果不是我们关心的指令，直接返回
        return

    if content.startswith('出牌'):
        # 处理出牌指令
        parts = content.split()
        if len(parts) != 3:
            card = Card(
                Module.Section(
                    Element.Text(
                        f'出牌指令格式错误！请使用"出牌 牌名 声明数量"的格式。\n'
                        f'例如：出牌 A 3\n'
                        f'发送"状态"可以查看当前游戏状态。',
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )

            await msg.reply(CardMessage(card))
            return

        card = parts[1]
        try:
            declared_count = int(parts[2])
        except ValueError:
            card_vl = Card(
                Module.Section(
                    Element.Text(
                        '声明数量必须是数字！',
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )

            await msg.reply(CardMessage(card_vl))
            return

        user_id = msg.author.id

        # 查找该用户参与的游戏
        game = None
        channel_id = None
        player_index = None

        for gid, g in games.items():
            for i, p in enumerate(g['players']):
                if p['id'] == user_id:
                    game = g
                    channel_id = gid
                    player_index = i
                    break
            if game:
                break

        if not game or not channel_id:
            card = Card(
                Module.Section(
                    Element.Text(
                        f'你没有参与任何正在进行的游戏！',
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )

            await msg.reply(CardMessage(card))
            return

        if game['status'] != 'playing':
            await msg.reply()
            return

        # 检查是否是当前玩家
        current_player = game['players'][game['current_player']]
        if current_player['id'] != user_id:
            # 非当前玩家尝试出牌，发送警告
            try:
                channel = await bot.client.fetch_public_channel(channel_id)
                card_op = Card(
                    Module.Section(
                        Element.Text(
                            f'警告：{msg.author.nickname or msg.author.username}尝试在非其回合时出牌！',
                            type=Types.Text.KMD
                        )
                    ),
                    theme=Types.Theme.DANGER
                )

                await channel.send(CardMessage(card_op))

            except:
                pass

            card_or = Card(
                Module.Section(
                    Element.Text(
                        f'还没轮到你出牌！请等待你的回合。',
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )

            await msg.reply(CardMessage(card_or))
            return

        # 检查玩家是否还有牌
        if not current_player['cards']:
            card_hc = Card(
                Module.Section(
                    Element.Text(
                        f'你已经没有牌了！',
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )

            await msg.reply(CardMessage(card_hc))
            return

        # 检查是否有这张牌
        if card not in current_player['cards'] and card != 'JOKER':
            card_nc = Card(
                Module.Section(
                    Element.Text(
                        f'你没有这张牌！',
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.DANGER
            )

            await msg.reply(CardMessage(card_nc))
            return

        # 从玩家手中移除这张牌
        if card in current_player['cards']:
            current_player['cards'].remove(card)
        elif card == 'JOKER' and 'JOKER' in current_player['cards']:
            current_player['cards'].remove('JOKER')

        # 将牌加入弃牌堆
        game['discard_pile'].append(card)
        game['last_declared_card'] = card
        game['last_player'] = current_player

        # 轮到下一个玩家
        game['current_player'] = (game['current_player'] + 1) % len(game['players'])
        next_player = game['players'][game['current_player']]

        # 在游戏频道中公布出牌信息（不显示具体牌面）
        try:
            channel = await bot.client.fetch_public_channel(channel_id)
            card_np = Card(
                Module.Section(
                    Element.Text(
                        f'{current_player["name"]}已出牌！\n'
                        f'轮到{next_player["name"]}出牌或质疑！',
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.SUCCESS
            )

            await channel.send(CardMessage(card_np))
        except:
            pass

        # 私信回复确认（不显示具体出牌内容）
        card_pl = Card(
            Module.Section(
                Element.Text(
                    f'你已出牌！\n'
                    f'发送"状态"可以查看当前游戏状态。',
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.SUCCESS
        )

        await msg.reply(CardMessage(card_pl))

    elif content == '状态' or content == 'status':
        await send_game_status(msg)

# 发送游戏状态信息到私信
async def send_game_status(msg: Message):
    user_id = msg.author.id

    # 查找该用户参与的游戏
    game = None
    channel_id = None
    player = None

    for gid, g in games.items():
        for p in g['players']:
            if p['id'] == user_id:
                game = g
                channel_id = gid
                player = p
                break
        if game:
            break

    if not game or not channel_id:
        card_npn = Card(
            Module.Section(
                Element.Text(
                    f'你没有参与任何正在进行的游戏！',
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.DANGER
        )

        await msg.reply(CardMessage(card_npn))
        return

    if game['status'] != 'playing':
        card_ns = Card(
            Module.Section(
                Element.Text(
                    f'游戏尚未开始！'
                    f'请等待房主开始游戏',
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.DANGER
        )

        await msg.reply(CardMessage(card_ns))
        return

    # 构造状态信息
    current_player = game['players'][game['current_player']]
    alive_players = [p for p in game['players'] if p['alive']]

    status_info = f"游戏状态：\n"
    status_info += f"目标牌：{game['target_card']}\n"
    status_info += f"当前回合：{current_player['name']}\n"
    status_info += f"你的手牌：{', '.join(player['cards'])}\n"
    status_info += f"存活玩家：{', '.join([p['name'] for p in alive_players])}\n"

    await msg.reply(status_info)


# 处理游戏结束
async def handle_game_end(channel_id, msg, alive_players):
    if alive_players:
        winner = alive_players[0]
        card_win = Card(
            Module.Section(
                Element.Text(
                    f'游戏结束！{winner["name"]}获胜！\n',
                    type=Types.Text.KMD
                )
            ),
            Module.Context(
                f"输入 `/创建游戏` 开始新游戏\n"
            ),
            theme=Types.Theme.SUCCESS
        )

        await msg.reply(CardMessage(card_win))
        # 发送游戏结果通知
        await send_game_result_notifications(channel_id, winner)
    else:
        card_ash = Card(
            Module.Section(
                Element.Text(
                    f'游戏结束！所有玩家都被淘汰！',
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.INFO
        )

        await msg.reply(CardMessage(card_ash))
        # 发送游戏结果通知
        await send_game_result_notifications(channel_id)
    del games[channel_id]

    # 清除该频道的俄罗斯轮盘状态
    keys_to_remove = [key for key in roulette_state.keys() if key.startswith(f"{channel_id}:")]
    for key in keys_to_remove:
        del roulette_state[key]


# 发送游戏结果通知到私信
async def send_game_result_notifications(channel_id, winner=None):
    if channel_id not in games:
        return

    game = games[channel_id]

    # 构造结果信息
    if winner:
        result_info = Card(
                Module.Section(
                    Element.Text(
                        f"游戏结束！{winner['name']}获胜！\n感谢参与游戏。",
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.SUCCESS
            )
    else:
        result_info = f"游戏结束！所有玩家都被淘汰！\n感谢参与游戏。"

    # 向所有参与游戏的玩家发送结果通知
    for player in game['players']:
        try:
            user = await bot.client.fetch_user(player['id'])
            await user.send(result_info)
        except Exception as e:
            # 如果无法发送私信，忽略错误
            pass


@bot.command(name='质疑', prefixes=['/'])
async def challenge(msg: Message):
    channel_id = msg.ctx.channel.id
    user_id = msg.author.id

    if channel_id not in games:
        card = Card(
            Module.Section(
                Element.Text(
                    f'当前频道没有正在进行的游戏！',
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.DANGER
        )

        await msg.reply(CardMessage(card))
        return

    game = games[channel_id]
    if game['status'] != 'playing':
        card = Card(
            Module.Section(
                Element.Text(
                    f'游戏尚未开始！'
                    f'请等待房主开始游戏',
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.DANGER
        )

        await msg.reply(CardMessage(card))
        return

    # 检查是否是当前玩家
    current_player = game['players'][game['current_player']]
    if current_player['id'] != user_id:
        card = Card(
            Module.Section(
                Element.Text(
                    f'你不能质疑，还没轮到你！'
                    f'请轮到你再质疑',
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.DANGER
        )

        await msg.reply(CardMessage(card))
        return

    if not game['last_declared_card'] or not game['last_player']:
        card = Card(
            Module.Section(
                Element.Text(
                    f'还没有人出牌，无法质疑！'
                    f'请耐心等待',
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.DANGER
        )

        await msg.reply(CardMessage(card))
        return

    # 检查上一个玩家出的牌是否属实
    last_player = game['last_player']
    last_declared_card = game['last_declared_card']
    target_card = game['target_card']

    # 计算实际打出的目标牌数量（包括JOKER）
    actual_target_cards = game['discard_pile'].count(target_card) + \
                          game['discard_pile'].count('JOKER')

    # 重置弃牌堆
    game['discard_pile'] = []
    game['last_declared_card'] = None
    game['last_player'] = None

    # 判断是否说谎：如果声明的牌不是目标牌且实际没有打出目标牌，则说谎
    is_lying = (last_declared_card != target_card) and (actual_target_cards == 0)

    # 确定进行俄罗斯轮盘的玩家
    if is_lying:  # 上家说谎
        roulette_player = last_player
        result_msg = f'{last_player["name"]}被揭穿说谎，进行俄罗斯轮盘...\n'
    else:  # 上家没有说谎（打出的是目标牌或声明的是目标牌）
        roulette_player = current_player
        result_msg = f'{current_player["name"]}质疑错误，进行俄罗斯轮盘...\n'

    # 进行俄罗斯轮盘
    chamber = roulette_player['bullet_chamber']
    position = roulette_player['chamber_position']

    # 获取当前概率分母
    probability_denominator = get_roulette_probability(channel_id, roulette_player['id'])

    # 计算被淘汰的概率
    eliminated_probability = 1.0 / probability_denominator

    # 生成随机数判断是否被淘汰
    color = None
    if random.random() < eliminated_probability:
        # 被淘汰
        roulette_player['alive'] = False
        result_msg += f'Bang! {roulette_player["name"]}被淘汰了！'
        color = Types.Theme.DANGER

        # 检查游戏是否结束
        alive_players = [p for p in game['players'] if p['alive']]
        if len(alive_players) <= 1:
            await handle_game_end(channel_id, msg, alive_players)
            return
    else:
        # 幸存，更新概率状态
        update_roulette_probability(channel_id, roulette_player['id'])
        result_msg += f'Click! {roulette_player["name"]}幸存下来！'
        color = Types.Theme.SUCCESS

    card = Card(
                Module.Section(
                    Element.Text(
                        result_msg,
                        type=Types.Text.KMD
                    )
                ),
                theme=color
            )

    await msg.reply(CardMessage(card))

    # 重新发牌
    await deal_cards(msg, game)


#重新发牌
async def deal_cards(msg: Message, game):
    """重新发牌"""
    # 重置牌堆
    game['deck'] = CARDS.copy()
    random.shuffle(game['deck'])

    # 发牌给每个存活的玩家
    alive_players = [p for p in game['players'] if p['alive']]
    cards_per_player = 5

    for player in alive_players:
        player['cards'] = []
        for _ in range(cards_per_player):
            if game['deck']:
                player['cards'].append(game['deck'].pop())

        # 重新装填子弹（每个玩家使用相同的弹仓）
        player['bullet_chamber'] = create_chamber()
        player['chamber_position'] = spin_chamber()

    # 通过私信发送新牌给每个玩家
    for player in alive_players:
        cards_str = ', '.join(player['cards'])
        try:
            user = await bot.client.fetch_user(player['id'])
            card = Card(
                Module.Section(
                    Element.Text(
                        f'重新发牌完成！你的新牌是: {cards_str}\n'
                        f'目标牌是: {game["target_card"]}\n'
                        f'发送"状态"可以随时查看游戏状态。\n'
                        f'出牌格式：出牌 牌名 声明数量（例如：出牌 A 3）',
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.SUCCESS
            )

            await user.send(CardMessage(card))

        except Exception as e:
            card = Card(
                Module.Section(
                    Element.Text(
                        f'无法向 {player["name"]} 发送私信，请检查隐私设置。',
                        type=Types.Text.KMD
                    )
                ),
                theme=Types.Theme.WARNING
            )

            await msg.reply(CardMessage(card))

    # 确定下一个玩家
    alive_player_ids = [p['id'] for p in alive_players]
    current_player_id = game['players'][game['current_player']]['id']

    if current_player_id not in alive_player_ids:
        # 当前玩家被淘汰，找下一个存活的玩家
        for i, player in enumerate(game['players']):
            if player['id'] == alive_player_ids[0]:
                game['current_player'] = i
                break

    next_player = game['players'][game['current_player']]
    card = Card(
        Module.Section(
            Element.Text(
                f'重新发牌完成！请{next_player["name"]}出牌！',
                type=Types.Text.KMD
            )
        ),
        theme=Types.Theme.SUCCESS
    )

    await msg.reply(CardMessage(card))


"""
测试网络延迟和bot响应时间
"""
command_timestamps: Dict[str, float] = {}

async def measure_ping():
    #测试网络延迟
    latencies = []
    url = "https://www.baidu.com"

    async with aiohttp.ClientSession() as session:
        for i in range(10):
            try:
                start_time = time.time()

                async with session.get(url, timeout = 10) as response:
                    #发送请求
                    await response.read()

                end_time = time.time()
                lactency = round((end_time - start_time) * 1000, 2)
                latencies.append(lactency)

                await asyncio.sleep(0.5)

            except asyncio.TimeoutError:
                latencies.append(9999)
            except Exception as e:
                latencies.append(9999)

    #计算平均值
    valid_latencies = [lat for lat in latencies if lat < 9999]

    if valid_latencies:
        avg_latency = round(statistics.mean(valid_latencies), 2)
        return avg_latency, len(valid_latencies), len(latencies)
    else:
        return 9999, 0, len(latencies)

@bot.command(name='ping', prefixes=['/'])
async def ping_command(msg: Message):
    #ping命令
    user_id = msg.author.id
    current_time = time.time()

    #记录命令接收时间
    command_timestamps[user_id] = current_time

    # 回复
    response_start_time = time.time()
    await msg.reply("""收到\n等我回国处理""")
    response_end_time = time.time()

    #计算相应时间
    response_time = (response_end_time - response_start_time) * 1000
    total_time = (response_end_time - current_time) * 1000

    logger.info(f"[TIME] 纯响应时间: {response_time:.2f}ms")
    logger.info(f"[TIME] 总处理时间: {total_time:.2f}ms")

    card = Card(
        Module.Section(
            Element.Text(
                f"🏓 **Pong!**\n"
                f"👤 用户: {msg.author.username}\n"
                f"⏰ 响应时间: {response_time:.2f} ms\n"
                f"⏰ 总响应时间: {total_time:.2f} ms\n"
                f"🤖 机器人状态: 正常运行",
                type=Types.Text.KMD
            )
        ),
        theme=Types.Theme.SECONDARY
    )

    if user_id in command_timestamps:
        del command_timestamps[user_id]

    await msg.reply(CardMessage(card))

    try:
        card = Card(
            Module.Section(
                Element.Text(
                    "🔄 正在测量网络延迟...\n"
                    "📡 目标: www.baidu.com\n"
                    "📦 数据包: 64字节\n"
                    "🔢 测试次数: 10次\n"
                    "⏳ 请稍候...",
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.SUCCESS
        )

        await msg.reply(CardMessage(card))

        avg_latency, success_count, total_count = await measure_ping()

        if avg_latency < 50:
            status = "🟢 极佳"
        elif avg_latency < 100:
            status = "🟡 良好"
        elif avg_latency < 200:
            status = "🟠 一般"
        elif avg_latency < 9999:
            status = "🔴 较差"
        else:
            status = "⚫ 连接失败"

        if avg_latency < 9999:
            card = Card(
                Module.Section(
                    Element.Text(
                        f"🏓 **Pong 测试结果**\n"
                        f"📡 **目标**: www.baidu.com\n"
                        f"📦 **数据包**: 64字节\n"
                        f"🔢 **测试次数**: {success_count}/{total_count} 次成功\n"
                        f"📊 **平均延迟**: {avg_latency}ms\n"
                        f"📈 **网络状态**: {status}",
                        type=Types.Text.KMD
                    )
                ),
                Module.Context(
                    Element.Text("💡 *延迟越低，网络连接质量越好*", type=Types.Text.KMD)
                ),
                theme=Types.Theme.SUCCESS
            )

            await msg.reply(CardMessage(card))

            logger.info(f"用户 {msg.author.username} 平均延迟 {avg_latency}ms")

        else:
            card = Card(
                Module.Section(
                    Element.Text(
                        f"❌ **Ping 测试失败**\n"
                        f"📡 **目标**: www.baidu.com\n"
                        f"🔢 **测试次数**: {success_count}/{total_count} 次成功",
                        type=Types.Text.KMD
                    )
                ),
                Module.Context(
                    Element.Text("💡 *无法连接到目标服务器，请检查网络连接*", type=Types.Text.KMD)
                ),
                theme=Types.Theme.WARNING
            )

            await msg.reply(CardMessage(card))

    except Exception as e:
        logger.warning(f"处理 /ping 命令时出错: {e}")
        await send_error_message(msg, "测量延迟时出现错误")

"""
查看当前时间
"""
@bot.command(name='time', prefixes=['/'])
async def time_command(msg: Message):
    #time命令
    try:
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        card = Card(
            Module.Section(
                Element.Text(
                    f"🕒 **当前时间**\n"
                    f"📅 日期时间: {current_time}\n"
                    f"👤 用户: {msg.author.username}\n",
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.INFO
        )

        await msg.reply(CardMessage(card))

    except Exception as e:
        logger.warning(f"处理 /time 命令时出错: {e}")
        await send_error_message(msg, "处理状态命令时出现错误")

"""
彩蛋
"""
@bot.on_message()
async def on_mention(msg: Message):
    """
    处理 @ 提及事件
    当用户 @ 机器人时自动回复'收到'
    """
    content = msg.content.strip()
    try:
        # 检查消息是否提及了当前机器人

        if content == "(met)1026571641(met)":
            # 创建简单的文本回复
            await msg.reply("✅ 收到！")
            logger.info(f"📩 收到来自 {msg.author.username} 的 @ 提及并已回复")

    except Exception as e:
        logger.warning(f"处理 @ 提及事件时出错: {e}")
        await send_error_message(msg, "处理状态命令时出现错误")
    except DeprecationWarning:
        None

"""
bot通过命令关闭或重启
"""
#解析管理员ID列表
if get_json.use_admin_user == 1:
    ADMIN_USER_ID_LIST = [uid.strip() for uid in ADMIN_USER_IDS.split(',') if uid.strip()]
else:
    ADMIN_USER_ID_LIST = [None]

@bot.command(name='stop', prefixes=['/'])
async def stop_bot(msg: Message):
    user_id = msg.author.id

    if user_id not in ADMIN_USER_ID_LIST:
        card = Card(
            Module.Section(
                Element.Text(
                    f"⚠ 权限不足，请联系管理员",
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.WARNING
        )

        await msg.reply(CardMessage(card))
        return

    card = Card(
        Module.Section(
            Element.Text(
                f"✅ 正在关闭机器人...",
                type=Types.Text.KMD
            )
        ),
        theme=Types.Theme.SUCCESS
    )

    await msg.reply(CardMessage(card))
    await bot.client.offline()
    logger.info("机器人已被kook端关闭")
    os._exit(1)


current_file_path = os.path.abspath(sys.argv[0])

@bot.command(name='restart', prefixes=['/'])
async def restart_bot(msg: Message):
    user_id = msg.author.id

    if user_id not in ADMIN_USER_ID_LIST:
        card = Card(
            Module.Section(
                Element.Text(
                    f"⚠ 权限不足，请联系管理员",
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.WARNING
        )

        await msg.reply(CardMessage(card))
        return

    card = Card(
        Module.Section(
            Element.Text(
                f"✅ 正在重启机器人...",
                type=Types.Text.KMD
            )
        ),
        theme=Types.Theme.SUCCESS
    )

    await msg.reply(CardMessage(card))
    await bot.client.offline()
    time.sleep(0.1)
    os.system(f"python {current_file_path}")

"""
bot欢迎功能
"""
@bot.on_event(EventTypes.JOINED_GUILD)
async def welcome_new_member(bot, event: Event):
    #获取新成员信息
    user_id = event.body['user_id']

    #发送欢迎消息
    channel = await bot.fetch_public_channel('7125355179539829')
    await channel.send(f'欢迎新成员 (met){user_id}(met) 加入服务器！')

"""
帮助命令
"""
@bot.command(name="分组", prefixes=['/'])
async def help_command(msg: Message):
    #分组帮助命令
    card = Card(
        Module.Header("🤖 分组统计机器人帮助"),
        Module.Section(
            Element.Text(
                "**📋 功能说明:**\n"
                "这是一个分组统计机器人，用于随机分配参与者到指定数量的组。\n\n"
                "**🎯 使用方法:**\n"
                "• `/start` - 开始统计\n"
                "• `/j` - 报名参加分组\n"
                "• `/end n` - 结束统计并分成n组 (例如: `/end 3`)\n"
                "• `/status` - 查看当前统计状态\n"
                "• `/help` - 显示帮助信息\n\n"
                "**💡 示例:**\n"
                "1. 管理员: `/start`\n"
                "2. 用户A: `/j`\n"
                "3. 用户B: `/j`\n"
                "4. 管理员: `/end 2`",
                type=Types.Text.KMD
            )
        ),
        Module.Context(
            Element.Text("🎲 分组结果完全随机，确保公平性", type=Types.Text.KMD)
        ),
        theme=Types.Theme.INFO
    )

    await msg.reply(CardMessage(card))

@bot.command(name='猜数字', prefixes=['/'])
async def guesshelp_command(msg: Message):
    #猜数字帮助命令
    card = Card(
        Module.Header("🤖 猜数字游戏帮助"),
        Module.Section(
            Element.Text(
                "**🎯 游戏规则:**\n"
                "猜出1-100之间的随机数字，尽量用最少的次数！\n\n"
                "**🕹️ 可用命令:**\n"
                "• `/新游戏` - 开始新游戏\n"
                "• `/猜 数字` - 猜测数字 (例如: `/猜 50`)\n"
                "• `/提示` - 获取提示\n"
                "• `/结束` - 结束当前游戏\n"
                "• `/排行榜` - 查看排行榜\n"
                "• `/猜数字` - 显示帮助\n\n"
                "**💡 游戏技巧:**\n"
                "• 使用二分法策略\n"
                "• 注意每次猜测的反馈\n"
                "• 合理使用提示功能",
                type=Types.Text.KMD
            )
        ),
        theme=Types.Theme.INFO
    )

    await msg.reply(CardMessage(card))

@bot.command(name='骗子酒馆', prefixes=['/'])
async def pzhelp_command(msg: Message):
    card = Card(
        Module.Header(f"骗子酒馆游戏帮助："),
        Module.Section(
            Element.Text(
                f"游戏指令：\n"
                f'`/创建游戏` - 创建新的游戏房间\n'
                f'`/加入游戏` - 加入当前频道的游戏\n'
                f'`/开始游戏` - 开始游戏（至少需要2名玩家）\n'
                f'`/质疑` - 质疑上家是否说谎\n\n'
            
                f'私信指令（在私信中使用）：\n'
                f'出牌 <牌名> <声明数量> - 出牌（例如：出牌 A 3）\n'
                f'状态 - 查看当前游戏状态\n\n'
            
                f'游戏规则：\n'
                f'1. 游戏使用20张牌：A、K、Q各6张，大小王2张\n'
                f'2. 每位玩家初始获得5张牌\n'
                f'3. 每轮指定一种牌为目标牌（如A）\n'
                f'4. 玩家轮流出牌并声明牌的数量\n'
                f'5. 其他玩家可以质疑前一位玩家是否说谎\n'
                f'6. 被质疑的玩家进行俄罗斯轮盘，失败者被淘汰\n'
                f'7. 最后存活的玩家获胜\n\n'
                
                f'特殊规则：\n'
                f'- 大小王可以当作任意牌使用\n'
                f'- 质疑错误也需要进行俄罗斯轮盘\n'
                f'- 游戏过程中会通过私信发送状态更新和结果通知',
                type=Types.Text.KMD
            )
        ),
        theme=Types.Theme.INFO
    )

    await msg.reply(CardMessage(card))

@bot.command(name='help', prefixes=['!', '！'])
async def allhelp_command(msg: Message):
    user_id = msg.author.id

    #全局帮助命令
    card = Card(
        Module.Header("🌈 帮助菜单"),
        Module.Section(
            Element.Text(
                "\n"
                "** 可用命令:**\n"
                "• `/分组` - 查看分组相关命令\n"
                "• `/猜数字` - 查看猜数字相关命令\n"
                "• `/骗子酒馆` - 查看骗子酒馆相关命令\n"
                "• `/ping` - 网络连接测试与bot响应时间\n"
                "• `/time` - 查看当前时间\n",
                type=Types.Text.KMD
            )
        ),
        theme=Types.Theme.INFO
    )

    await msg.reply(CardMessage(card))

    if user_id in ADMIN_USER_ID_LIST:

        card = Card(
            Module.Section(
                Element.Text(
                    "• `/stop` - 关闭bot(仅限管理员)\n"
                    "• `/restart` - 重启bot(仅限管理员)",
                    type=Types.Text.KMD
                )
            ),
            theme=Types.Theme.INFO
        )

        await msg.ctx.channel.send(CardMessage(card), temp_target_id = user_id)


"""
消息监听与错误消息处理
"""
#消息监听
@bot.on_message()
async def handle_all_messages(msg: Message):

    #只处理文本消息
    if not msg.content or not isinstance(msg.content, str):
        return

    content = msg.content.strip()

    if content == "/help":
        logger.info(f"📝 用户 {msg.author.username} 执行了其他 bot 的 help 命令")
    elif content == "！help":
        logger.info(f"📝 用户 {msg.author.username} 执行了 help 命令")

    #检查是否以/或.或!开头
    if content.startswith(('/', '!', '.', '@')):
        #正则表达除去前缀
        command_match = re.match(r'^[/!](\w+)', content)
        if command_match:
            command = command_match.group(1).lower()
        if content != "/help":
            logger.info(f"📝 用户 {msg.author.username} 执行了 {command} 命令")

#处理错误消息
async def send_error_message(msg: Message, error_text: str):
    card = Card(
        Module.Section(
            Element.Text(
                f"⚠️ **系统错误**\n"
                f"{error_text}，请稍后重试。",
                type=Types.Text.KMD
            )
        ),
        theme=Types.Theme.WARNING
    )

    await  msg.reply(CardMessage(card))

#避免跨线程访问冲突
def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

new_loop = asyncio.new_event_loop()
t = Thread(target=start_loop, args=(new_loop,))
t.start()

#在新线程中运行异步任务
async def task():
    await asyncio.sleep(1)
    logger.success("在新线程中运行异步任务完成")

asyncio.run_coroutine_threadsafe(task(), new_loop)

"""
主函数
"""
async def main():
    if not BOT_TOKEN:
        logger.warning("❌ 错误: 请设置 KHL_BOT_TOKEN 环境变量")
        logger.warning("💡 使用方法:")
        logger.warning("  Windows: set KHL_BOT_TOKEN=你的机器人令牌")
        logger.warning("  Linux/Mac: export KHL_BOT_TOKEN='你的机器人令牌'")
        sys.exit(1)

    if not ADMIN_USER_ID_LIST:
        logger.warning("请设置ADMIN_USER_ID环境变量")
        sys.exit(1)

    try:
        logger.success("🎉 启动机器人...")
        logger.success("按 Ctrl+C 停止机器人")
        logger.success("=" * 50)

        await bot.start()

    except KeyboardInterrupt:
        logger.success("🛑 机器人已手动停止")
    except Exception as e:
        logger.warning(f"❌ 启动机器人时出错: {e}")
        traceback.print_exc()

"""
协程进行
"""
"""loop = asyncio.get_event_loop()
tasks = [loop.create_task(main()), loop.create_task(creat_ui())]
loop.run_until_complete(asyncio.gather(*tasks))
loop.close()
"""

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 机器人已手动停止")
        os._exit(1)
    except Exception as e:
        logger.warning(f"❌ 启动机器人时出错: {e}")
        traceback.print_exc()
        os._exit(1)

