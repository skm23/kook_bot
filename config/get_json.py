import json

with open('config\setting.json', 'r', encoding='utf-8') as setting:
    data = json.load(setting)

log_create = data['loguru_create']
use_admin_user = data['use_admin_user_ids']