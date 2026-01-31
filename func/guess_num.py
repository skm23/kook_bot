import time
import random
from typing import  Dict, List, Set, Optional

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