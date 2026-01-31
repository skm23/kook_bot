import random
from typing import  Dict, List, Set

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
