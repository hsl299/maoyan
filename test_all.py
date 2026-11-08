# -*- coding: utf-8 -*-
"""仿猫眼系统全功能端到端测试：覆盖商家端 + 用户端全部用例，逐项断言"""
import json
import os
import urllib.parse
import urllib.request
import http.cookiejar
import pymysql
from PIL import Image
import io

import config

BASE = 'http://127.0.0.1:5000'
RESULTS = []


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def post(self, path, data=None, as_json=False, multipart=None):
        if multipart:
            body, ct = multipart
            req = urllib.request.Request(BASE + path, data=body, method='POST',
                                         headers={'Content-Type': ct})
        else:
            headers = {'User-Agent': 'test'}
            if as_json:
                body = json.dumps(data or {}).encode()
                headers['Content-Type'] = 'application/json'
            else:
                body = urllib.parse.urlencode(data or {}).encode()
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
            req = urllib.request.Request(BASE + path, data=body, headers=headers)
        with self.opener.open(req) as r:
            return r.status, r.read().decode()

    def get(self, path):
        path = urllib.parse.quote(path, safe='/?&=:%')
        req = urllib.request.Request(BASE + path, headers={'User-Agent': 'test'})
        with self.opener.open(req) as r:
            return r.status, r.read().decode()


def _conn():
    return pymysql.connect(host=config.DB_HOST, port=config.DB_PORT,
                           user=config.DB_USER, password=config.DB_PASSWORD,
                           database=config.DB_NAME, charset='utf8mb4')


def db_one(sql, params=()):
    c = _conn(); cur = c.cursor(pymysql.cursors.DictCursor)
    cur.execute(sql, params); row = cur.fetchone(); c.close(); return row


def db_all(sql, params=()):
    c = _conn(); cur = c.cursor(pymysql.cursors.DictCursor)
    cur.execute(sql, params); rows = cur.fetchall(); c.close(); return rows


def db_exec(sql, params=()):
    c = _conn(); cur = c.cursor()
    cur.execute(sql, params); c.commit(); c.close()


def make_png():
    buf = io.BytesIO(); Image.new('RGB', (200, 300), (40, 120, 200)).save(buf, 'PNG')
    return buf.getvalue()


def multipart(fields, file_field, filename, file_bytes, ct='image/png'):
    import uuid
    boundary = '----b' + uuid.uuid4().hex
    body = io.BytesIO()
    for k, v in fields.items():
        body.write(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                    % (boundary, k, v)).encode())
    body.write(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
                'Content-Type: %s\r\n\r\n' % (boundary, file_field, filename, ct)).encode())
    body.write(file_bytes)
    body.write(('\r\n--%s--\r\n' % boundary).encode())
    return body.getvalue(), 'multipart/form-data; boundary=%s' % boundary


def check(name, cond, extra=''):
    RESULTS.append((name, bool(cond), extra))
    tag = 'PASS' if cond else 'FAIL'
    print(f'[{"PASS" if cond else "FAIL"}] {name}' + (f'  | {extra}' if extra else ''))


# ============================================================
print('===== 一、商家端 =====')
m = Client()
s, _ = m.post('/login', {'username': 'shop01', 'password': '123456'})

# 1 新增票品（电影，无封面）
m.post('/merchant/tickets/new', data={'title': 'TEST流浪地球2', 'type': '0', 'duration': '173',
                                      'actors': '吴京', 'address': '呼和浩特·万达影城', 'intro': '测试'})
t1 = db_one("SELECT * FROM tickets WHERE title='TEST流浪地球2'")
check('商家新增电影票品', t1 is not None, f"id={t1 and t1['id']}")
if t1:
    check('新票品默认上架(status=1)', t1['status'] == 1, f"status={t1['status']}")

# 2 新增演出票品（带封面上传）
body, ct = multipart({'title': 'TEST音乐会', 'type': '1', 'duration': '120'}, 'cover_file', 'a.png', make_png())
m.post('/merchant/tickets/new', multipart=(body, ct))
t2 = db_one("SELECT * FROM tickets WHERE title='TEST音乐会'")
check('商家新增演出票品(封面上传)', t2 is not None and t2['cover'].startswith('uploads/'),
      f"cover={t2 and t2['cover']}")
if t2:
    check('上传封面文件已落盘', os.path.exists(os.path.join('static', t2['cover'])))

# 3 编辑票品
if t1:
    m.post(f"/merchant/tickets/{t1['id']}/edit", data={'title': 'TEST流浪地球3', 'type': '0',
                                                       'duration': '150', 'actors': '吴京', 'address': '测试'})
    t1e = db_one('SELECT * FROM tickets WHERE id=%s', (t1['id'],))
    check('编辑票品信息生效', t1e['title'] == 'TEST流浪地球3', t1e['title'])
    tid = t1e['id']
else:
    tid = None

# 4 下架 / 上架
if t1:
    m.post(f"/merchant/tickets/{t1['id']}/toggle", {})
    check('票品下架', db_one('SELECT status s FROM tickets WHERE id=%s', (t1['id'],))['s'] == 0)
    m.post(f"/merchant/tickets/{t1['id']}/toggle", {})
    check('票品恢复上架', db_one('SELECT status s FROM tickets WHERE id=%s', (t1['id'],))['s'] == 1)

# 5 添加场次 + 座位生成
if tid:
    m.post(f'/merchant/tickets/{tid}/sessions/add',
           data={'show_time': '2026-11-05T14:30', 'base_price': '50', 'seat_rows': '8', 'seat_cols': '10'})
    s1 = db_one('SELECT * FROM sessions WHERE ticket_id=%s ORDER BY id DESC LIMIT 1', (tid,))
    check('添加场次成功', s1 is not None, f"sid={s1 and s1['id']}")
    if s1:
        cnt = db_one('SELECT COUNT(*) c FROM seats WHERE session_id=%s', (s1['id'],))['c']
        check('场次自动生成8x10=80个座位', cnt == 80, f"实际{cnt}")
        a1 = db_one("SELECT price p FROM seats WHERE session_id=%s AND seat_row='A' AND seat_col=1", (s1['id'],))
        d1 = db_one("SELECT price p FROM seats WHERE session_id=%s AND seat_row='D' AND seat_col=1", (s1['id'],))
        e1 = db_one("SELECT price p FROM seats WHERE session_id=%s AND seat_row='E' AND seat_col=1", (s1['id'],))
        check('票价分层(前3行+30%,中+15%,后平价)',
              a1 and abs(float(a1['p']) - 65) < 0.01 and d1 and abs(float(d1['p']) - 57.5) < 0.01 and e1 and abs(float(e1['p']) - 50) < 0.01,
              f"A1={a1 and a1['p']} D1={d1 and d1['p']} E1={e1 and e1['p']}")
    m.post(f'/merchant/tickets/{tid}/sessions/add',
           data={'show_time': '2026-11-06T19:00', 'base_price': '80', 'seat_rows': '6', 'seat_cols': '8'})
    check('添加第2个场次', db_one('SELECT COUNT(*) c FROM sessions WHERE ticket_id=%s', (tid,))['c'] >= 2)

# 6 场次停售 / 恢复
if s1:
    m.post(f"/merchant/sessions/{s1['id']}/toggle", {})
    check('场次停售', db_one('SELECT status s FROM sessions WHERE id=%s', (s1['id'],))['s'] == 0)
    m.post(f"/merchant/sessions/{s1['id']}/toggle", {})
    check('场次恢复在售', db_one('SELECT status s FROM sessions WHERE id=%s', (s1['id'],))['s'] == 1)

# 7 座位/票价管理
if s1:
    m.post(f"/merchant/sessions/{s1['id']}/seats/update", {'action': 'price_row', 'seat_row': 'A', 'price': '88'})
    a1 = db_one("SELECT price p FROM seats WHERE session_id=%s AND seat_row='A' AND seat_col=1", (s1['id'],))
    check('按行调价A行→88', a1['p'] == 88, str(a1['p']))
    m.post(f"/merchant/sessions/{s1['id']}/seats/update", {'action': 'price_all', 'price': '66'})
    allp = db_all('SELECT DISTINCT price p FROM seats WHERE session_id=%s', (s1['id'],))
    check('全场统一定价→66', len(allp) == 1 and allp[0]['p'] == 66, str([x['p'] for x in allp]))
    m.post(f"/merchant/sessions/{s1['id']}/seats/update", {'action': 'reset'})
    rst = db_one('SELECT COUNT(*) c FROM seats WHERE session_id=%s AND status!=0', (s1['id'],))['c']
    check('重置场次座位全可售', rst == 0, f"非0座位={rst}")
    sid = s1['id']

# ============================================================
print('\n===== 二、用户端 =====')
u = Client()
u.post('/register', {'username': 'user02', 'password': '123456', 'confirm': '123456',
                     'nickname': '测试用户', 'phone': '13800000002'})
check('新用户注册', db_one("SELECT id FROM users WHERE username='user02'") is not None)
s, _ = u.post('/login', {'username': 'user02', 'password': '123456'})

# 首页
s, html = u.get('/')
check('首页展示票品', 'TEST流浪地球3' in html)
check('首页展示上传封面', 'uploads/' in html)

# 搜索 + 分类
s, html = u.get('/?kw=音乐会')
check('关键词搜索', 'TEST音乐会' in html)
s, html = u.get('/?type=0')
check('分类筛选电影', 'TEST流浪地球3' in html and 'TEST音乐会' not in html)

# 详情
if tid:
    s, html = u.get(f'/ticket/{tid}')
    check('票品详情页', 'TEST流浪地球3' in html and '选择场次' in html)

# 选座页（含座位图）
if sid:
    s, html = u.get(f'/select_seat/{sid}')
    seat_cnt = db_one('SELECT COUNT(*) c FROM seats WHERE session_id=%s', (sid,))['c']
    check('选座页展示座位图(80座)', s == 200 and 'seat' in html and seat_cnt == 80, f"HTTP{s} 座{seat_cnt}")

    # 锁座 2 个座位
    seats = db_all('SELECT id FROM seats WHERE session_id=%s AND status=0 ORDER BY id LIMIT 2', (sid,))
    ids = [x['id'] for x in seats]
    s, resp = u.post('/api/lock_seats', as_json=True, data={'session_id': sid, 'seat_ids': ids})
    lr = json.loads(resp)
    oid = lr.get('order_id')
    check('锁座成功生成待支付订单', lr.get('success') and oid is not None, str(lr))
    if oid:
        od = db_one('SELECT status s FROM orders WHERE id=%s', (oid,))
        check('订单状态=待支付(0)', od['s'] == 0, str(od['s']))
        lk = db_one('SELECT COUNT(*) c FROM seats WHERE id IN (%s,%s) AND status=1' % (ids[0], ids[1]))
        check('锁定的座位状态=1(锁定)', lk['c'] == 2, f"锁定{lk['c']}")

        # 重复锁同一座位（已被锁）应失败
        s, resp = u.post('/api/lock_seats', as_json=True, data={'session_id': sid, 'seat_ids': ids})
        check('已锁座位再选被拒绝', not json.loads(resp).get('success'))

        # 支付
        s, resp = u.post(f'/order/{oid}/pay')
        check('模拟支付成功', json.loads(resp).get('success'))
        od = db_one('SELECT status s, verify_code v FROM orders WHERE id=%s', (oid,))
        check('支付后订单已支付+生成统一核销码', od['s'] == 1 and od['v'] and len(od['v']) == 16, f"码={od['v']}")
        et = db_one('SELECT COUNT(*) c FROM e_tickets WHERE order_id=%s', (oid,))['c']
        check('生成2张电子票记录', et == 2, str(et))
        sol = db_one('SELECT COUNT(*) c FROM seats WHERE id IN (%s,%s) AND status=2' % (ids[0], ids[1]))
        check('支付后座位已售(status=2)', sol['c'] == 2, f"已售{sol['c']}")

        # 电子票页：核销码只出现1次
        s, html = u.get(f'/order/{oid}/ticket')
        check('电子票页展示唯一核销码(1次)', html.count(od['v']) == 1, f"出现{html.count(od['v'])}次")

        # 我的订单
        s, html = u.get('/my_orders')
        check('我的订单显示该单', od['v'] in html or f'/order/{oid}' in html)

        # 订单详情
        s, html = u.get(f'/order/{oid}')
        check('订单详情展示2个座位', html.count('座位') >= 1 and len(db_all('SELECT * FROM order_seats WHERE order_id=%s', (oid,))) == 2)

        # 退票申请（订单已支付）
        s, html = u.get(f'/order/{oid}/refund')
        s, _ = u.post(f'/order/{oid}/refund', {'reason': '行程有变'})
        od = db_one('SELECT status s FROM orders WHERE id=%s', (oid,))
        rf = db_one('SELECT * FROM refunds WHERE order_id=%s', (oid,))
        check('退票申请后订单=退票审核中(5)', od['s'] == 5, str(od['s']))
        check('生成退票申请记录', rf is not None and rf['status'] == 0)
        seat_still = db_one('SELECT COUNT(*) c FROM seats WHERE id IN (%s,%s) AND status=2' % (ids[0], ids[1]))
        check('退票审核中座位未释放', seat_still['c'] == 2, f"仍售{seat_still['c']}")

        # 商家销售订单能看到
        ono = db_one('SELECT order_no n FROM orders WHERE id=%s', (oid,))['n']
        s, html = m.get('/merchant/orders')
        check('商家销售订单列表显示该单', ono in html, ono)

        # 商家退票审核：驳回
        if rf:
            m.post(f"/merchant/refunds/{rf['id']}/handle", {'action': 'reject', 'reply': '不符合退票条件'})
            od = db_one('SELECT status s FROM orders WHERE id=%s', (oid,))
            rf2 = db_one('SELECT status s FROM refunds WHERE id=%s', (rf['id'],))
            check('退票驳回后订单恢复已支付(1)', od['s'] == 1, str(od['s']))
            check('退票申请状态=驳回(2)', rf2['s'] == 2, str(rf2['s']))

            # 再次申请退票 → 通过
            u.post(f'/order/{oid}/refund', {'reason': '再次申请'})
            rf3 = db_one('SELECT id FROM refunds WHERE order_id=%s AND status=0', (oid,))
            if rf3:
                m.post(f"/merchant/refunds/{rf3['id']}/handle", {'action': 'approve', 'reply': '同意'})
                od = db_one('SELECT status s FROM orders WHERE id=%s', (oid,))
                rec = db_one('SELECT COUNT(*) c FROM seats WHERE id IN (%s,%s) AND status=0' % (ids[0], ids[1]))
                check('退票通过后订单=已退票(3)', od['s'] == 3, str(od['s']))
                check('退票通过后座位回收可售', rec['c'] == 2, f"回收{rec['c']}")

        # 座位冲突：已售(未退)场景再测一次 → 用第2个场次下一单，再锁同座
        s2 = db_one('SELECT * FROM sessions WHERE ticket_id=%s AND id!=%s ORDER BY id LIMIT 1', (tid, sid))
        if s2:
            s2seats = db_all('SELECT id FROM seats WHERE session_id=%s AND status=0 ORDER BY id LIMIT 1', (s2['id'],))
            s, resp = u.post('/api/lock_seats', as_json=True,
                             data={'session_id': s2['id'], 'seat_ids': [s2seats[0]['id']]})
            oid2 = json.loads(resp)['order_id']
            u.post(f'/order/{oid2}/pay')

            # 核销测试（订单2）
            od2 = db_one('SELECT verify_code v FROM orders WHERE id=%s', (oid2,))
            m.post('/merchant/verify/api', {'code': od2['v']})
            od2b = db_one('SELECT status s FROM orders WHERE id=%s', (oid2,))
            et2 = db_one('SELECT COUNT(*) c FROM e_tickets WHERE order_id=%s AND status=1', (oid2,))['c']
            check('核销后订单=已核销(6)', od2b['s'] == 6, str(od2b['s']))
            check('核销后电子票券全部已核销', et2 == 1, f"{et2}张")
            s, resp = m.post('/merchant/verify/api', {'code': od2['v']})
            check('重复核销被拦截', not json.loads(resp).get('success'), json.loads(resp).get('msg'))

            # 归属校验：另一商家核销 shop01 的订单应拒绝
            m2 = Client()
            m2.post('/register', {'username': 'shop02', 'password': '123456', 'confirm': '123456',
                                  'nickname': '商家2', 'phone': '13900000002', 'role': '1'})
            m2.post('/login', {'username': 'shop02', 'password': '123456'})
            s, resp = m2.post('/merchant/verify/api', {'code': od2['v']})
            check('其他商家核销被拒绝(归属校验)', not json.loads(resp).get('success'), json.loads(resp).get('msg'))

        # 超时取消：构造一个超时待支付订单
        s3seats = db_all('SELECT id FROM seats WHERE session_id=%s AND status=0 ORDER BY id LIMIT 1', (sid,))
        if s3seats:
            s, resp = u.post('/api/lock_seats', as_json=True,
                             data={'session_id': sid, 'seat_ids': [s3seats[0]['id']]})
            oid3 = json.loads(resp)['order_id']
            db_exec('UPDATE orders SET created_at=DATE_SUB(NOW(), INTERVAL 1000 SECOND) WHERE id=%s', (oid3,))
            u.get('/my_orders')  # 触发 release_timeout_orders
            od3 = db_one('SELECT status s FROM orders WHERE id=%s', (oid3,))
            free3 = db_one('SELECT COUNT(*) c FROM seats WHERE id=%s AND status=0', (s3seats[0]['id'],))['c']
            check('超时待支付订单自动取消(4)', od3['s'] == 4, str(od3['s']))
            check('超时后座位释放可售', free3 == 1, str(free3))

# 待支付订单超时（选座前触发）不单独测，已在上面覆盖

print('\n===== 汇总 =====')
fails = [r for r in RESULTS if not r[1]]
print(f'总计 {len(RESULTS)} 项，通过 {len(RESULTS)-len(fails)} 项，失败 {len(fails)} 项')
for name, _, extra in fails:
    print('  FAIL:', name, extra)
