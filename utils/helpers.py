# -*- coding: utf-8 -*-
"""
通用工具函数
"""
import random
import string
from datetime import datetime

import config


def gen_order_no():
    """生成唯一订单号：日期 + 随机串"""
    return 'MO' + datetime.now().strftime('%Y%m%d%H%M%S') + ''.join(
        random.choices(string.digits, k=6))


def gen_ticket_code():
    """生成电子票核销码（16位大写字母数字）"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))


def order_is_timeout(created_at):
    """判断待支付订单是否超时（超过 ORDER_TIMEOUT 未支付）"""
    if created_at is None:
        return False
    return (datetime.now() - created_at).total_seconds() > config.ORDER_TIMEOUT
