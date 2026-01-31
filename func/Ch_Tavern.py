import random

# 用于跟踪俄罗斯轮盘的概率状态
roulette_state = {}

class Cheater_Tavern:
    def __init__(self):
        pass
    
    def create_chamber(self):
        #创建新的左轮，只有一个子弹位置
        chamber = [False] * 6
        # 固定子弹位置为0
        chamber[0] = True
        return chamber

    def spin_chamber(self):
        #旋转弹仓，随机选一个位
        return random.randint(0,5)

    def get_roulette_probability(self, channel_id, player_id):
        key = f"{channel_id}:{player_id}"
        if key not in roulette_state:
            #初始化概率
            roulette_state[key] = 6    #初始概率分母为6
        return roulette_state[key]

    def update_roulette_probability(self, channel_id, player_id):
        #更新的概率
        key = f"{channel_id}:{player_id}"
        if key in roulette_state:
            roulette_state[key] = max(1,roulette_state[key] - 1)   #概率增加
        else:
            roulette_state[key] = 6

Ch_Tavern = Cheater_Tavern()
